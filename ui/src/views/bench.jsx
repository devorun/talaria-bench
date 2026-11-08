import { useEffect, useMemo, useState } from 'react'
import { Viewer3D, Timeline, usePlayer, frameAt, traceDuration } from '../viewer.jsx'
import { Bar, Button, Chip, Empty, ErrorBox, Loading, Progress, STATUS, human, pct, useApi, useJob, useTrace } from '../ui.jsx'
import { tipTime } from '../viewer.jsx'

function Tile({ card, active, onClick, quick }) {
  const st = STATUS[card.status] || STATUS['n/a']
  const m = card.metric || {}
  const scoped = card.applicable && card.status !== 'out_of_scope'
  const isMove = card.id.startsWith('move:')
  if (scoped && isMove) {
    const falls = card.runs - card.passed
    return (
      <button type="button" className={`tb-tile tb-tile-${st.tone}${active ? ' tb-active' : ''}`} onClick={onClick}>
        <div className="tb-tile-top">
          <span className="tb-tile-title">{card.title}</span>
          <span className={'tb-dot tb-fill-' + st.tone} />
        </div>
        <div className="tb-tile-big">{pct(falls / card.runs)}</div>
        <div className="tb-tile-sub">tipped in {falls}/{card.runs} {quick ? 'quick ' : ''}preflight worlds</div>
        <div className="tb-tile-metric">median {human(card.id, m.median)}</div>
        <div className="tb-tile-worst">{m.worst && m.worst.reason ? `worst: ${m.worst.reason}` : 'never tipped'}</div>
      </button>
    )
  }
  return (
    <button type="button" className={`tb-tile tb-tile-${st.tone}${active ? ' tb-active' : ''}`} onClick={onClick}
      disabled={!scoped}>
      <div className="tb-tile-top">
        <span className="tb-tile-title">{card.title}</span>
        <span className={'tb-dot tb-fill-' + st.tone} />
      </div>
      {scoped ? (
        <>
          <div className="tb-tile-big">{pct(card.pass_rate)}</div>
          <div className="tb-tile-sub">pass · {card.runs} worlds</div>
          <div className="tb-tile-metric">median: <b>{human(card.id, m.median, m.unit)}</b></div>
          <div className="tb-tile-worst">worst: {m.worst && m.worst.value != null ? human(card.id, m.worst.value, m.unit) : (m.worst && m.worst.reason) || '–'}</div>
        </>
      ) : (
        <>
          <div className="tb-tile-scope">{st.label}</div>
          <div className="tb-tile-note">{card.status === 'out_of_scope' ? 'not scored' : (card.note || 'does not apply')}</div>
        </>
      )}
    </button>
  )
}

function Replays({ robot, card }) {
  const m = card.metric || {}
  const median = useTrace({ robot, scene: card.id, seed: m.median_seed ?? 0 })
  const worst = useTrace({ robot, scene: card.id, seed: (m.worst && m.worst.seed) ?? 0 })
  const a = median[0] && median[0].ok ? median[0] : null
  const b = worst[0] && worst[0].ok ? worst[0] : null
  const player = usePlayer(traceDuration(a && a.trace, b && b.trace))
  const view = (d, title, loading) => {
    if (loading || !d) return <div className="tb-viewer tb-viewer-wait" style={{ height: 320 }}><span className="tb-spinner" /> recording {title}…</div>
    const r = d.result || {}
    return (
      <Viewer3D parts={d.trace.parts} frames={d.trace.frames} meta={d.meta} look={d.look}
        tipAt={tipTime(d.trace, r)} frameIndex={frameAt(d.trace, player.t)}
        time={player.t} height={320} label={`${title} · world ${d.seed}`}
        sublabel={(r.passed ? 'passed' : (r.reason || 'failed')) + (d.note ? ` · ${d.note}` : '')}
        tone={r.passed ? 'green' : 'red'} />
    )
  }
  return (
    <div className="tb-card">
      <div className="tb-card-head">
        <h3>{card.title}: median world vs worst world</h3>
        <span className="tb-muted">{card.conditions}</span>
      </div>
      <div className="tb-two tb-two-tight">
        {view(a, 'median', median[1])}
        {view(b, 'worst', worst[1])}
      </div>
      <Timeline player={player} marks={a && a.meta && a.meta.push ? [{ t: a.meta.push.at_s, label: 'push' }] : []} />
      <div className="tb-row tb-wrap tb-gap-sm">
        {Object.entries(card.failure_reasons || {}).map(([k, v]) => <Chip key={k} tone="red">{k} × {v}</Chip>)}
      </div>
      <ErrorBox data={median[0]} />
    </div>
  )
}

function Loads({ report }) {
  const joints = {}
  for (const c of report.scenes) {
    if (!c.applicable || c.status === 'out_of_scope') continue
    for (const [j, l] of Object.entries(c.loads || {})) {
      if (!joints[j] || l.peak_pct_max > joints[j].peak) joints[j] = { peak: l.peak_pct_max, where: c.title }
    }
  }
  const rows = Object.entries(joints).sort((x, y) => y[1].peak - x[1].peak)
  if (!rows.length) return null
  return (
    <div className="tb-card">
      <div className="tb-card-head"><h3>Servo load</h3><Chip>estimate</Chip></div>
      <p className="tb-muted tb-small">Highest peak per joint across in-scope scenes, as % of datasheet stall torque.
        Stall torque is not a safe continuous torque.</p>
      {rows.map(([j, v]) => <Bar key={j} label={j} value={v.peak} mark={90} right={`${v.peak.toFixed(0)}%`} note={v.where} />)}
    </div>
  )
}

export function BenchPage({ robot }) {
  const [data, loading, reload] = useApi(robot ? `/robots/${robot}/report` : null)
  const [job, start] = useJob(() => reload())
  const [sel, setSel] = useState(null)
  const report = data && data.ok ? data.report : null
  useEffect(() => setSel(null), [robot])
  const cards = report ? report.scenes : []
  const active = useMemo(() => cards.find((c) => c.id === sel), [cards, sel])
  const counts = cards.reduce((acc, c) => { acc[c.status] = (acc[c.status] || 0) + 1; return acc }, {})
  const running = job && (job.status === 'running' || job.status === 'starting')
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Report card</h2>
          <p>The test arena: flat floor, ramps, bars, pushes, a slippery floor, payload and every standing move,
            each in many randomized worlds (friction, masses, servo strength, backlash).</p>
        </div>
        <div className="tb-hero-actions">
          <Button busy={running} onClick={() => start('/bench', { robot, quick: true })}>Quick run · 10 worlds</Button>
          <Button kind="primary" busy={running} onClick={() => start('/bench', { robot, quick: false })}>Full run · 30 worlds</Button>
        </div>
      </div>
      <Progress job={job} label={`Benchmarking ${robot}`} />
      {loading && !report ? <Loading what="Loading report" /> : null}
      {data && !data.ok ? <Empty>No report for {robot} yet. Start a quick run.</Empty> : null}
      {report ? (
        <>
          <div className="tb-card tb-summary">
            <div className="tb-card-head">
              <h3>Summary</h3>
              <div className="tb-row tb-gap-sm">
                {['green', 'amber', 'red', 'out_of_scope', 'n/a'].filter((k) => counts[k]).map((k) => (
                  <Chip key={k} tone={STATUS[k].tone}>{counts[k]} {STATUS[k].label.toLowerCase()}</Chip>))}
                {report.settings.quick ? <Chip tone="amber">quick run</Chip> : null}
                <Chip>{report.settings.worlds} worlds/scene · moves {report.settings.move_worlds || 60}</Chip>
                <Chip>{report.origin}</Chip>
              </div>
            </div>
            <p className="tb-lead">{report.summary}</p>
            <p className="tb-muted tb-small">{report.label}</p>
          </div>
          <div className="tb-tiles">
            {cards.map((c) => <Tile key={c.id} card={c} active={c.id === sel} quick={report.settings.quick}
              onClick={() => setSel(c.id === sel ? null : c.id)} />)}
          </div>
          {!active ? <p className="tb-hint">Click a scene tile to replay its median and worst world side by side.</p> : null}
          {active ? <Replays key={active.id} robot={robot} card={active} /> : null}
          <div className="tb-two">
            <Loads report={report} />
            {report.limitations && report.limitations.length ? (
              <div className="tb-card">
                <div className="tb-card-head"><h3>Outside the model's scope</h3><Chip tone="grey">not scored</Chip></div>
                {report.limitations.map((l) => <p key={l.scope} className="tb-small">{l.scope}: {l.note}</p>)}
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
