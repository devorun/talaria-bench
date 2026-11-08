import { useEffect, useMemo, useState } from 'react'
import { Viewer3D, Timeline, usePlayer, frameAt, traceDuration } from '../viewer.jsx'
import { Button, Chip, ErrorBox, Progress, STATUS, fmt, pct, useApi, useJob, useTrace } from '../ui.jsx'

function parseCustom(text) {
  // "name: path=value, path=value" per line
  const out = []
  for (const line of text.split('\n')) {
    const [name, rest] = line.split(':')
    if (!name || !rest || !name.trim()) continue
    const set = {}
    for (const kv of rest.split(',')) {
      const [k, v] = kv.split('=')
      if (k && v != null && k.trim()) set[k.trim()] = /^[-+*]/.test(v.trim()) || isNaN(Number(v)) ? v.trim() : Number(v)
    }
    if (Object.keys(set).length) out.push({ name: name.trim(), set })
  }
  return out
}

function Delta({ d }) {
  if (d == null) return null
  const pts = Math.round(d * 100)
  if (!pts) return <span className="tb-delta">±0</span>
  return <span className={'tb-delta ' + (pts > 0 ? 'tb-up' : 'tb-down')}>{pts > 0 ? '+' : ''}{pts} pts</span>
}

function Synced({ robot, jobId, row, names, result }) {
  const seed = useMemo(() => {
    const card = result.reports.base.scenes.find((c) => c.id === row.scene)
    return card && card.metric ? card.metric.median_seed : 0
  }, [row, result])
  const traces = names.map((n) => useTrace({ robot, scene: row.scene, seed, job_id: jobId, variant: n }))
  const ok = traces.map(([d]) => (d && d.ok ? d : null))
  const player = usePlayer(traceDuration(...ok.map((d) => d && d.trace)))
  return (
    <div className="tb-card">
      <div className="tb-card-head">
        <h3>{row.title}: same world ({seed}), every design</h3>
        <span className="tb-muted">one timeline drives all views</span>
      </div>
      <div className={'tb-grid-views tb-views-' + Math.min(names.length, 3)}>
        {names.map((n, i) => {
          const d = ok[i]
          if (!d) return <div key={n} className="tb-viewer tb-viewer-wait" style={{ height: 300 }}><span className="tb-spinner" /> {n}…</div>
          const r = d.result || {}
          return (
            <Viewer3D key={n} parts={d.trace.parts} frames={d.trace.frames} meta={d.meta}
              frameIndex={frameAt(d.trace, player.t)} time={player.t} height={300} label={n}
              sublabel={r.passed ? `passed · ${fmt(r.metric)}` : (r.reason || 'failed')} tone={r.passed ? 'green' : 'red'} />
          )
        })}
      </div>
      <Timeline player={player} />
    </div>
  )
}

export function ComparePage({ robot }) {
  const [presets] = useApi(robot ? `/robots/${robot}/variants` : null)
  const [picked, setPicked] = useState({})
  const [custom, setCustom] = useState('')
  const [quick, setQuick] = useState(true)
  const [row, setRow] = useState(null)
  const [job, start] = useJob()
  useEffect(() => { setPicked({}); setRow(null); setCustom('') }, [robot])
  useEffect(() => {
    const list = presets && presets.ok ? presets.variants : []
    if (list.length && !Object.keys(picked).length) setPicked({ [list[list.length - 1].name]: true })
  }, [presets])
  const list = presets && presets.ok ? presets.variants : []
  const variants = [...list.filter((v) => picked[v.name]), ...parseCustom(custom)]
  const result = job && job.status === 'done' ? job.result : null
  const names = result ? result.variants.map((v) => v.name) : []
  const running = job && (job.status === 'running' || job.status === 'starting')
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Compare designs</h2>
          <p>The robot and its variants on exactly the same randomized worlds, side by side. Deltas are in
            percentage points of pass rate against the base design.</p>
        </div>
      </div>
      <div className="tb-card">
        <div className="tb-card-head"><h3>Variants</h3><span className="tb-muted">presets from examples/variants, or your own overrides</span></div>
        <div className="tb-checks">
          {list.map((v) => (
            <label key={v.name} className={'tb-check' + (picked[v.name] ? ' tb-active' : '')}>
              <input type="checkbox" checked={!!picked[v.name]} onChange={(e) => setPicked({ ...picked, [v.name]: e.target.checked })} />
              <span>{v.name}</span>
              <small>{v.set ? Object.entries(v.set).map(([k, x]) => `${k} = ${x}`).join(', ') : `robot ${v.robot}`}</small>
            </label>
          ))}
        </div>
        <textarea className="tb-input tb-textarea" rows={2} value={custom} onChange={(e) => setCustom(e.target.value)}
          placeholder={'legs +1.5 cm: parts.left_leg.size.2=+1.5, parts.right_leg.size.2=+1.5'} />
        <div className="tb-row tb-gap">
          <label className="tb-toggle"><input type="checkbox" checked={quick} onChange={(e) => setQuick(e.target.checked)} /> quick (10 worlds)</label>
          <Button kind="primary" busy={running} disabled={!variants.length}
            onClick={() => { setRow(null); start('/compare', { robot, variants, quick }) }}>
            Compare {variants.length} variant{variants.length === 1 ? '' : 's'}
          </Button>
        </div>
      </div>
      <Progress job={job} label="Comparing" />
      {result ? (
        <div className="tb-card">
          <div className="tb-card-head"><h3>Results</h3><Chip>{result.settings.worlds} worlds per scene · same seeds</Chip></div>
          <div className="tb-table-wrap">
            <table className="tb-table tb-table-compare">
              <thead><tr><th>Scene</th>{names.map((n) => <th key={n}>{n}</th>)}</tr></thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.scene} className={(row && row.scene === r.scene ? 'tb-active ' : '') + 'tb-clickable'}
                    onClick={() => setRow(r)}>
                    <td>{r.title}</td>
                    {names.map((n) => {
                      const c = r.cells[n]
                      const st = STATUS[c.status] || STATUS['n/a']
                      if (c.pass_rate == null || c.status === 'out_of_scope') return <td key={n}><Chip tone={st.tone}>{st.label}</Chip></td>
                      return (
                        <td key={n}>
                          <span className={'tb-dot tb-fill-' + st.tone} /> <b>{pct(c.pass_rate)}</b>
                          <span className="tb-muted"> · {fmt(c.median, c.unit)} {c.unit}</span> <Delta d={c.delta_pass} />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tb-hint">Click a row to replay that scene for every design in the same world.</p>
        </div>
      ) : null}
      {result && row ? <Synced key={row.scene} robot={robot} jobId={job.id} row={row} names={names} result={result} /> : null}
      <ErrorBox data={presets} />
    </div>
  )
}
