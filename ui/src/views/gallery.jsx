import { useEffect, useState } from 'react'
import { api } from '../platform.js'
import { Chip, Loading, Empty } from '../ui.jsx'

function Thumb({ robot }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    let live = true
    if (robot.has_thumb) {
      api(`/robots/${robot.name}/thumb.json`).then((r) => { if (live && r.ok) setSrc(r.data_url) })
    }
    return () => { live = false }
  }, [robot.name, robot.has_thumb])
  return (
    <div className="tb-thumb">
      {src ? <img src={src} alt={robot.title} /> : <div className="tb-thumb-ph">{(robot.family || 'robot').slice(0, 1).toUpperCase()}</div>}
      <span className="tb-thumb-tag">SIM</span>
    </div>
  )
}

export function Gallery({ robots, loading, open }) {
  if (loading && !robots) return <Loading what="Loading robots" />
  if (!robots || !robots.length) return <Empty>No robots yet.</Empty>
  const bundled = robots.filter((r) => r.source === 'bundled')
  const mine = robots.filter((r) => r.source !== 'bundled')
  const card = (r) => (
    <button type="button" key={r.name} className="tb-card tb-robot-card" onClick={() => open(r.name)}>
      <Thumb robot={r} />
      <div className="tb-robot-card-body">
        <div className="tb-robot-card-title">
          <span>{r.title || r.name}</span>
          {r.source !== 'bundled' ? <Chip tone="accent">yours</Chip> : null}
        </div>
        <div className="tb-meta-row">
          {r.family ? <Chip>{r.family}</Chip> : null}
          <Chip>{r.servos} servos</Chip>
          <Chip>{r.mass_g} g</Chip>
          {r.base === 'fixed' ? <Chip>fixed base</Chip> : null}
          {r.has_photo ? <Chip tone="accent">photo</Chip> : null}
        </div>
        {r.role ? <p className="tb-robot-card-role">{r.role}</p> : null}
        {r.headline ? <p className="tb-robot-card-headline">{r.headline}</p> : null}
      </div>
    </button>
  )
  return (
    <div className="tb-page">
      <div className="tb-hero">
        <div>
          <h2>Robot gallery</h2>
          <p>Hobby servo robots described in a YAML spec and tested in MuJoCo across many randomized worlds.
            Every number on these cards is a simulation result.</p>
        </div>
      </div>
      <div className="tb-grid-cards">{bundled.map(card)}</div>
      {mine.length ? (
        <>
          <h3 className="tb-section-title">Your robots</h3>
          <div className="tb-grid-cards">{mine.map(card)}</div>
        </>
      ) : null}
    </div>
  )
}
