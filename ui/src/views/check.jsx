import { useEffect, useState } from 'react'
import { api } from '../platform.js'
import { Viewer3D, Timeline, usePlayer, frameAt, traceDuration } from '../viewer.jsx'
import { Bar, Button, Chip, ErrorBox, useApi, useTrace } from '../ui.jsx'

const VERDICT = {
  pass: { word: 'PASS', tone: 'green', line: 'Approved for exactly this move, speed and robot spec.' },
  fail: { word: 'BLOCKED', tone: 'red', line: 'robot_play will refuse this move until a changed version passes.' },
  inconclusive: { word: 'INCONCLUSIVE', tone: 'grey', line: 'No tips, but too few worlds to bound the chance under 10%.' },
}

function Interval({ tip, limit }) {
  const L = (x) => `${Math.min(100, x * 100)}%`
  return (
    <div className="tb-interval">
      <div className="tb-interval-track">
        <div className="tb-interval-limit" style={{ left: L(limit) }}><span>limit {Math.round(limit * 100)}%</span></div>
        <div className="tb-interval-range" style={{ left: L(tip.low), width: `calc(${L(tip.high)} - ${L(tip.low)})` }} />
        <div className="tb-interval-point" style={{ left: L(tip.rate) }} />
      </div>
      <div className="tb-interval-scale"><span>0%</span><span>50%</span><span>100%</span></div>
    </div>
  )
}

function Result({ res, robot, move, speed }) {
  const v = VERDICT[res.verdict] || VERDICT.inconclusive
  const seed = res.tip_seeds && res.tip_seeds.length ? res.tip_seeds[0] : null
  const [trace, tl] = useTrace({ robot, move, speed, seed: seed ?? undefined })
  const tr = trace && trace.ok ? trace.trace : null
  const player = usePlayer(traceDuration(tr))
  const [play, setPlay] = useState(null)
  const [busy, setBusy] = useState(null)
  useEffect(() => setPlay(null), [res])
  const joints = Object.entries(res.joints).sort((a, b) => b[1].peak_pct_p90 - a[1].peak_pct_p90)
  const doPlay = async (target) => {
    setBusy(target)
    setPlay(await api('/play', { method: 'POST', body: { robot, move, speed, target } }))
    setBusy(null)
  }
  return (
    <>
      <div className={'tb-verdict tb-verdict-' + v.tone}>
        <div className="tb-verdict-word">{v.word}</div>
        <div className="tb-verdict-body">
          <div className="tb-verdict-title">{robot} / {move}{speed !== 1 ? ` at speed ${speed}` : ''}</div>
          <div>{v.line}</div>
          <div className="tb-small tb-muted-on">{res.label}</div>
        </div>
        <div className="tb-verdict-stat">
          <div className="tb-big">{(res.tip.rate * 100).toFixed(0)}%</div>
          <div>tipped in {res.tip.falls}/{res.worlds} worlds</div>
          <div className="tb-small">95% interval {(res.tip.low * 100).toFixed(0)}–{(res.tip.high * 100).toFixed(0)}%</div>
        </div>
      </div>
      <div className="tb-two">
        <div className="tb-card">
          <div className="tb-card-head"><h3>Tip chance</h3>
            <div className="tb-row tb-gap-sm">
              {res.extended ? <Chip tone="accent">extended 30 → 60 worlds</Chip> : null}
              {res.stopped_early ? <Chip tone="accent">stopped early: failure already clear</Chip> : null}
            </div>
          </div>
          <Interval tip={res.tip} limit={0.1} />
          <p className="tb-small tb-muted">A move passes when the upper end of the 95% Wilson interval is at most 10% and
            no servo peaks above 90% of stall torque (90th percentile across worlds).</p>
          {res.tip.fall_frame ? <p>Most tips start during <b>frame {res.tip.fall_frame}</b>.</p> : null}
          <h4>Servo load <Chip>estimate</Chip></h4>
          {joints.map(([j, l]) => <Bar key={j} label={j} value={l.peak_pct_p90} mark={90} right={`${l.peak_pct_p90.toFixed(0)}%`} />)}
        </div>
        <div className="tb-card tb-card-flush">
          {tr ? (
            <>
              <Viewer3D parts={tr.parts} frames={tr.frames} meta={trace.meta} frameIndex={frameAt(tr, player.t)} time={player.t}
                height={360} label={seed != null ? `a world where it tipped (${seed})` : 'nominal world'}
                sublabel={trace.result.fell ? `tips at ${trace.result.fell_at_s?.toFixed(2)} s` : 'stays up'}
                tone={trace.result.fell ? 'red' : 'green'} />
              <Timeline player={player} />
            </>
          ) : <div className="tb-viewer tb-viewer-wait" style={{ height: 360 }}>{tl ? <><span className="tb-spinner" /> recording replay…</> : null}</div>}
        </div>
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
      <div className="tb-card">
        <div className="tb-card-head"><h3>Play it</h3><span className="tb-muted">through the same approval gate as the robot_play tool</span></div>
        <div className="tb-row tb-gap">
          <Button kind={res.verdict === 'pass' ? 'primary' : 'default'} busy={busy === 'virtual'} onClick={() => doPlay('virtual')}>Play on virtual robot</Button>
          <Button busy={busy === 'real'} onClick={() => doPlay('real')}>Play on real robot</Button>
        </div>
        {play ? (
          play.ok ? <div className="tb-callout tb-tone-green">Playing {play.move} on the {play.target} robot ({play.duration_s.toFixed(1)} s).</div>
            : <div className={'tb-callout ' + (play.blocked ? 'tb-tone-red' : 'tb-tone-amber')}>{play.blocked ? <strong>Gate: </strong> : null}{play.error}</div>
        ) : null}
      </div>
    </>
  )
}

export function CheckPage({ robot, initialMove }) {
  const [moves] = useApi(robot ? `/robots/${robot}/moves` : null)
  const [move, setMove] = useState(initialMove || '')
  const [speed, setSpeed] = useState(1)
  const [quick, setQuick] = useState(true)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  useEffect(() => { setRes(null); setMove(initialMove || '') }, [robot, initialMove])
  const list = moves && moves.ok ? moves.moves : []
  useEffect(() => { if (!move && list.length) setMove(list[0].name) }, [list.length])
  const run = async () => {
    setBusy(true)
    setRes(null)
    setRes(await api('/check', { method: 'POST', body: { robot, move, speed, quick } }))
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
        <div className="tb-row tb-gap tb-wrap">
          <label className="tb-field">Move
            <select className="tb-select" value={move} onChange={(e) => { setMove(e.target.value); setRes(null) }}>
              {list.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
            </select>
          </label>
          <label className="tb-field">Speed {speed.toFixed(2)}×
            <input type="range" min={0.25} max={1.5} step={0.05} value={speed}
              onChange={(e) => { setSpeed(parseFloat(e.target.value)); setRes(null) }} />
          </label>
          <label className="tb-toggle"><input type="checkbox" checked={quick} onChange={(e) => setQuick(e.target.checked)} /> quick (30 worlds, extends to 60 when clean)</label>
          <Button kind="primary" busy={busy} disabled={!move} onClick={run}>Run preflight</Button>
        </div>
        {busy ? <p className="tb-muted"><span className="tb-spinner" /> simulating {move} in randomized worlds…</p> : null}
      </div>
      {res && res.ok ? <Result key={`${move}-${speed}-${res.worlds}`} res={res} robot={robot} move={move} speed={speed} /> : <ErrorBox data={res} />}
    </div>
  )
}
