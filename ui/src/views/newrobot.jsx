// "New robot from template": the same code path as the robot_define tool (template + params).
import { useEffect, useState } from 'react'
import { api, notify } from '../platform.js'
import { Button, ErrorBox, Loading, MODEL_NOTE, useApi } from '../ui.jsx'

export function NewRobot({ go, refresh }) {
  const [data] = useApi('/templates')
  const list = data && data.ok ? data.templates : []
  const [tpl, setTpl] = useState('block_robot')
  const [vals, setVals] = useState({})
  const [name, setName] = useState('my_robot')
  const [mass, setMass] = useState('')
  const [servo, setServo] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const cur = list.find((t) => t.name === tpl)
  useEffect(() => {
    if (!cur) return
    setVals(Object.fromEntries(cur.fields.map((f) => [f.key, f.default])))
    setServo('')
  }, [tpl, cur && cur.name])
  if (!data) return <Loading what="Loading templates" />
  const create = async () => {
    const params = { name }
    if (servo) params.servo = servo          // otherwise the template picks the servo that suits its size
    for (const f of cur.fields) params[f.key] = Number(vals[f.key])
    if (mass !== '') params.mass_g = Number(mass)
    setBusy(true)
    const r = await api('/robots/new', { method: 'POST', body: { template: tpl, params } })
    setBusy(false)
    setRes(r)
    if (r.ok) {
      notify(r.warnings && r.warnings.length ? `Created ${r.robot}. ${r.warnings[r.warnings.length - 1]}` : `Created ${r.robot}`)
      if (refresh) refresh()
      go('robot', r.robot)
    }
  }
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>New robot from a template</h2>
          <p>A few numbers give a valid model that stands in simulation. Leave the mass empty if you do not know
            it: it is estimated from the part sizes and the bench varies it by ±30%.</p>
        </div>
      </div>
      <div className="tb-card">
        <div className="tb-row tb-gap tb-wrap">
          <label className="tb-field">Template
            <select className="tb-select" value={tpl} onChange={(e) => { setTpl(e.target.value); setRes(null) }}>
              {list.map((t) => <option key={t.name} value={t.name}>{t.name.replace('_', ' ')}</option>)}
            </select>
          </label>
          <label className="tb-field">Name
            <input className="tb-input" value={name} onChange={(e) => setName(e.target.value.toLowerCase())} />
          </label>
          {cur ? cur.fields.map((f) => (
            <label key={f.key} className="tb-field">{f.label}{f.unit ? ` (${f.unit})` : ''}
              {f.options ? (
                <select className="tb-select" value={vals[f.key] ?? f.default}
                  onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}>
                  {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input className="tb-input tb-input-xs" type="number" step="0.5" value={vals[f.key] ?? f.default}
                  onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} />
              )}
            </label>
          )) : null}
          <label className="tb-field">Servo
            <select className="tb-select" value={servo} onChange={(e) => setServo(e.target.value)}>
              <option value="">{cur ? `template default (${cur.servo}${cur.name === 'quadruped' || cur.name === 'hexapod' ? ', by size' : ''})` : 'template default'}</option>
              {data.servos.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="tb-field">Total mass (g, optional)
            <input className="tb-input tb-input-xs" type="number" value={mass} placeholder="auto"
              onChange={(e) => setMass(e.target.value)} />
          </label>
        </div>
        {cur ? <p className="tb-muted tb-small">{cur.help}</p> : null}
        <p className="tb-muted tb-small tb-model-note">{MODEL_NOTE}</p>
        <div className="tb-row tb-gap">
          <Button kind="primary" busy={busy} onClick={create}>Create robot</Button>
        </div>
        <ErrorBox data={res} />
      </div>
    </div>
  )
}
