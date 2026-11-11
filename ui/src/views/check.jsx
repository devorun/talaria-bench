import { useEffect, useState } from 'react'
import { api } from '../platform.js'
import { Viewer3D, Timeline, usePlayer, tipLabel, tipMarks, tipTime, traceDuration } from '../viewer.jsx'
import { Bar, Button, Chip, ErrorBox, useApi, useTrace } from '../ui.jsx'

const VERDICT = {
  pass: { word: 'PASS', tone: 'green', line: 'Approved for exactly this move, speed and robot spec.' },
  fail: { word: 'BLOCKED', tone: 'red', line: 'robot_play will refuse this move until a changed version passes.' },
  inconclusive: { word: 'INCONCLUSIVE', tone: 'grey', line: 'No tips, but too few worlds to bound the chance under 10%.' },
}
const LOAD_LIMIT = 90 // % of stall torque, 90th percentile across worlds (the preflight's own limit)

function Interval({ tip, limit }) {
  const L = (x) => `${Math.min(100, x * 100)}%`
  return (
    <div className="tb-interval" role="img"
      aria-label={`Tip chance ${(tip.rate * 100).toFixed(0)}%, 95% interval ${(tip.low * 100).toFixed(0)} to ${(tip.high * 100).toFixed(0)}%, limit ${Math.round(limit * 100)}%`}>
      <div className="tb-interval-track">
        <div className="tb-interval-ok" style={{ width: L(limit) }} />
        <div className="tb-interval-limit" style={{ left: L(limit) }}><span>limit {Math.round(limit * 100)}%</span></div>
        <div className={'tb-interval-range' + (tip.high <= limit ? ' tb-ok' : '')}
          style={{ left: L(tip.low), width: `calc(${L(tip.high)} - ${L(tip.low)})` }} />
        <div className="tb-interval-point" style={{ left: L(tip.rate) }} />
      </div>
      <div className="tb-interval-scale"><span>0%</span><span>50%</span><span>100%</span></div>
    </div>
  )
}

const CUSTOM = '__custom__'

// "Go to this pose, hold it, come back": the quickest way to ask "is a 40 degree arm raise safe?".
function customFrames(c, joints) {
  const to = {}
  const back = {}
  for (const j of joints) {
    const v = Number(c.angles[j.name] || 0)
    if (v) { to[j.name] = v; back[j.name] = j.home }
  }
  return Object.keys(to).length ? [{ ms: c.ms, hold: c.hold, joints: to }, { ms: c.ms, joints: back }] : null
}

function customLabel(c, joints) {
  const bits = joints.filter((j) => Number(c.angles[j.name] || 0)).map((j) => `${j.name} ${Number(c.angles[j.name])}°`)
  return `custom pose: ${bits.join(', ')}`
}

function Result({ res, robot, move, speed, payload, label }) {
  const v = VERDICT[res.verdict] || VERDICT.inconclusive
  const seed = res.tip_seeds && res.tip_seeds.length ? res.tip_seeds[0] : null
  const [trace, tl] = useTrace({ robot, ...payload, speed, seed: seed ?? undefined })
  const tr = trace && trace.ok ? trace.trace : null
  const player = usePlayer(traceDuration(tr))
  const [play, setPlay] = useState(null)
  const [busy, setBusy] = useState(null)
  useEffect(() => setPlay(null), [res])
  const joints = Object.entries(res.joints).sort((a, b) => b[1].peak_pct_p90 - a[1].peak_pct_p90)
  const loaded = joints.filter(([, l]) => l.peak_pct_p90 >= LOAD_LIMIT)
  const doPlay = async (target) => {
    setBusy(target)
    setPlay(await api('/play', { method: 'POST', body: { robot, ...payload, speed, target } }))
    setBusy(null)
  }
  return (
    <>
      <div className={'tb-verdict tb-verdict-' + v.tone} role="status">
        <div className="tb-verdict-word">{v.word}</div>
        <div className="tb-verdict-body">
          <div className="tb-verdict-title">{robot} / {label || move}{speed !== 1 ? ` at speed ${speed}` : ''}</div>
          <div>{v.line}</div>
          {loaded.length ? (
            <div>Servo load over {LOAD_LIMIT}% of stall (estimate): {loaded.map(([j, l]) => `${j} ${l.peak_pct_p90.toFixed(0)}%`).join(', ')}</div>
          ) : null}
          <div className="tb-small tb-muted-on">{res.label}</div>
        </div>
        <div className="tb-verdict-stat">
          <div className="tb-big">{(res.tip.rate * 100).toFixed(0)}%<small>tip chance</small></div>
          <div className="tb-verdict-worlds">tipped in <b>{res.tip.falls} of {res.worlds}</b> simulated worlds{res.official ? '' : ' (quick)'}</div>
          <div className="tb-small">95% interval {(res.tip.low * 100).toFixed(0)}–{(res.tip.high * 100).toFixed(0)}%</div>
        </div>
      </div>
      <div className="tb-two">
        <div className="tb-stack">
          <div className="tb-card">
            <div className="tb-card-head"><h3>Tip chance</h3>
              <div className="tb-row tb-gap-sm tb-wrap">
                {res.official ? <Chip tone="accent" title="the same 60 fixed-seed worlds the report card and gallery use">official · 60 fixed worlds</Chip>
                  : <Chip tone="amber">quick · {res.worlds} worlds</Chip>}
                {res.extended ? <Chip>clean at 30, extended to 60</Chip> : null}
              </div>
            </div>
            <Interval tip={res.tip} limit={0.1} />
            <p className="tb-small tb-muted">A move passes when the upper end of the 95% Wilson interval is at most 10% and
              no servo peaks above 90% of stall torque (90th percentile across worlds).</p>
            {res.tip.fall_frame ? <p>Most tips start during <b>frame {res.tip.fall_frame}</b>.</p> : null}
            <h4>Servo load <Chip>estimate</Chip></h4>
            {joints.map(([j, l]) => <Bar key={j} label={j} value={l.peak_pct_p90} mark={LOAD_LIMIT} right={`${l.peak_pct_p90.toFixed(0)}%`} />)}
            <p className="tb-small tb-muted">Peak torque as a share of datasheet stall torque; the mark is the {LOAD_LIMIT}% limit.</p>
          </div>
          {res.suggestions && res.suggestions.length ? (
            <div className="tb-card tb-suggest">
              <div className="tb-card-head"><h3>What to change</h3><span className="tb-muted">derived from the move and the numbers</span></div>
              <ol>{res.suggestions.map((s) => <li key={s}>{s}</li>)}</ol>
            </div>
          ) : null}
          {res.speed_limit_stretches && res.speed_limit_stretches.length ? (
            <div className="tb-callout tb-tone-amber">{res.speed_limit_stretches.map((w) => <div key={w}>{w}</div>)}</div>
          ) : null}
        </div>
        <div className="tb-stack">
          <div className="tb-card tb-card-flush">
            {tr ? (
              <>
                <Viewer3D parts={tr.parts} frames={tr.frames} fps={tr.fps} meta={trace.meta} look={trace.look}
                  tipAt={tipTime(tr, trace.result)} tipWhy={trace.result.fall_reason} time={player.t}
                  height={400} label={seed != null ? `a world where it tipped (${seed})` : 'nominal world'}
                  sublabel={trace.result.fell ? tipLabel(trace.result, 'tips') : 'stays up'}
                  tone={trace.result.fell ? 'red' : 'green'} />
                <Timeline player={player} marks={tipMarks([tr, trace.result])} />
              </>
            ) : <div className="tb-viewer tb-viewer-wait" style={{ height: 400 }}>{tl ? <><span className="tb-spinner" /> recording replay…</> : null}</div>}
          </div>
          <div className="tb-card">
            <div className="tb-card-head"><h3>Play it</h3><span className="tb-muted">through the same approval gate as the robot_play tool</span></div>
            <p className="tb-small tb-muted">The robot first eases back to its home pose at half speed, then plays the move, so it
              starts where the preflight started. A real robot also needs its token (from <code>hermes talaria firmware</code>).</p>
            <div className="tb-row tb-gap tb-wrap">
              <Button kind={res.verdict === 'pass' ? 'primary' : 'default'} busy={busy === 'virtual'} onClick={() => doPlay('virtual')}>Play on virtual robot</Button>
              <Button busy={busy === 'real'} onClick={() => doPlay('real')}>Play on real robot</Button>
            </div>
            {play ? (
              play.ok ? <div className="tb-callout tb-tone-green">Playing {label || play.move} on the {play.target} robot ({play.duration_s.toFixed(1)} s
                {play.homing_ms ? `, after ${(play.homing_ms / 1000).toFixed(1)} s back to home` : ', from home'}).</div>
                : <div className={'tb-callout ' + (play.blocked ? 'tb-tone-red' : 'tb-tone-amber')}>{play.blocked ? <strong>Gate: </strong> : null}{play.error}</div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  )
}

export function CheckPage({ robot, initialMove }) {
  const [moves] = useApi(robot ? `/robots/${robot}/moves` : null)
  const [detail] = useApi(robot ? `/robots/${robot}` : null)
  const joints = detail && detail.ok ? detail.joints : []
  const [custom, setCustom] = useState({ angles: {}, ms: 800, hold: 1000 })
  const [move, setMove] = useState(initialMove || '')
  const [speed, setSpeed] = useState(1)
  const [quick, setQuick] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  useEffect(() => { setRes(null); setMove(initialMove || ''); setCustom({ angles: {}, ms: 800, hold: 1000 }) }, [robot, initialMove])
  const list = moves && moves.ok ? moves.moves : []
  useEffect(() => { if (!move && list.length) setMove(list[0].name) }, [list.length])
  const frames = move === CUSTOM ? customFrames(custom, joints) : null
  const payload = move === CUSTOM ? { frames } : { move }
  const label = move === CUSTOM ? customLabel(custom, joints) : null
  const run = async () => {
    setBusy(true)
    setRes(null)
    setRes(await api('/check', { method: 'POST', body: { robot, ...payload, speed, quick } }))
    setBusy(false)
  }
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Move check</h2>
          <p>Preflight before anything moves: the move runs in randomized simulated worlds on flat ground. A pass
            records an approval for exactly this move, speed and spec; anything else is refused at play time.</p>
        </div>
      </div>
      <div className="tb-card">
        <div className="tb-row tb-gap tb-wrap tb-end">
          <label className="tb-field">Move
            <select className="tb-select" value={move} onChange={(e) => { setMove(e.target.value); setRes(null) }}>
              {list.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
              {joints.length ? <option value={CUSTOM}>custom pose…</option> : null}
            </select>
          </label>
          <label className="tb-field">Speed {speed.toFixed(2)}×
            <input type="range" min={0.25} max={1.5} step={0.05} value={speed}
              onChange={(e) => { setSpeed(parseFloat(e.target.value)); setRes(null) }} />
          </label>
          <label className="tb-toggle"><input type="checkbox" checked={quick} onChange={(e) => setQuick(e.target.checked)} /> quick (30 worlds; clean moves extend to 60)</label>
          <Button kind="primary" busy={busy} disabled={!move || (move === CUSTOM && !frames)} onClick={run}>Run preflight</Button>
        </div>
        {move === CUSTOM ? (
          <div className="tb-custom-pose">
            <p className="tb-small tb-muted">Go to this pose, hold it, and come back to home. Angles in degrees from home; positive swings
              the part forward.</p>
            <div className="tb-row tb-gap tb-wrap">
              {joints.map((j) => (
                <label key={j.name} className="tb-field">{j.name} <span className="tb-muted tb-small">({j.min}…{j.max})</span>
                  <input className="tb-input tb-input-xs" type="number" step="5" min={j.min} max={j.max} value={custom.angles[j.name] ?? 0}
                    onChange={(e) => { setCustom({ ...custom, angles: { ...custom.angles, [j.name]: e.target.value } }); setRes(null) }} />
                </label>
              ))}
              <label className="tb-field">reach it in (ms)
                <input className="tb-input tb-input-xs" type="number" step="100" min="100" value={custom.ms}
                  onChange={(e) => { setCustom({ ...custom, ms: Number(e.target.value) }); setRes(null) }} />
              </label>
              <label className="tb-field">hold (ms)
                <input className="tb-input tb-input-xs" type="number" step="100" min="0" value={custom.hold}
                  onChange={(e) => { setCustom({ ...custom, hold: Number(e.target.value) }); setRes(null) }} />
              </label>
            </div>
          </div>
        ) : null}
        {busy ? <p className="tb-muted"><span className="tb-spinner" /> simulating {label || move} in randomized worlds…</p> : null}
      </div>
      {res && res.ok ? <Result key={`${label || move}-${speed}-${res.worlds}`} res={res} robot={robot} move={move} speed={speed} payload={payload} label={label} /> : <ErrorBox data={res} />}
    </div>
  )
}
