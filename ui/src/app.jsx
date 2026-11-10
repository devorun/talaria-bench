import { useEffect, useState } from 'react'
import { STYLES } from './styles.js'
import { surface } from './platform.js'
import { RobotPicker, useApi } from './ui.jsx'
import { Gallery } from './views/gallery.jsx'
import { RobotPage } from './views/robot.jsx'
import { BenchPage } from './views/bench.jsx'
import { ComparePage } from './views/compare.jsx'
import { CheckPage } from './views/check.jsx'
import { NewRobot } from './views/newrobot.jsx'

const TABS = [
  ['gallery', 'Gallery'],
  ['robot', 'Robot'],
  ['bench', 'Report card'],
  ['compare', 'Compare'],
  ['check', 'Move check'],
]

export function App({ initial } = {}) {
  const [robots, loading, refresh] = useApi('/robots')
  const list = robots && robots.ok ? robots.robots : null
  const [nav, setNav] = useState(initial || { view: 'gallery', robot: 'caduceus', move: null })
  const go = (view, robot, move = null) => setNav({ view, robot: robot || nav.robot, move })
  const robot = nav.robot
  useEffect(() => { if (nav.view === 'gallery') refresh() }, [nav.view])
  return (
    <div className={'tb-root tb-surface-' + surface()}>
      <style>{STYLES}</style>
      <header className="tb-header">
        <div className="tb-brand">
          <div className="tb-logo" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="26" height="26" fill="none" strokeLinecap="round" strokeLinejoin="round">
              <path className="tb-logo-t" strokeWidth="3.8" d="M15.5 8.5 H29 M22.25 8.5 V27" />
              <path className="tb-logo-w" strokeWidth="3.2" d="M18.5 14.5 C12.5 15 7.5 12.5 3.8 6 M18.5 21.5 C14 21.5 10 19.5 6.8 15" />
            </svg>
          </div>
          <div>
            <div className="tb-title">Talaria Bench</div>
            <div className="tb-tagline">Test before it moves · simulation</div>
          </div>
        </div>
        <nav className="tb-tabs" role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={nav.view === id}
              className={'tb-tab' + (nav.view === id ? ' tb-active' : '')} onClick={() => go(id, robot)}>{label}</button>
          ))}
        </nav>
        {nav.view !== 'gallery' && nav.view !== 'new' ? (
          <div className="tb-picker"><RobotPicker robots={list} value={robot} onChange={(r) => go(nav.view, r)} /></div>
        ) : null}
      </header>
      <main className="tb-main">
        {nav.view === 'gallery' ? <Gallery robots={list} loading={loading} open={(r) => go('robot', r)}
          create={() => go('new', robot)} /> : null}
        {nav.view === 'new' ? <NewRobot go={go} refresh={refresh} /> : null}
        {nav.view === 'robot' ? <RobotPage robot={robot} go={go} refresh={refresh} /> : null}
        {nav.view === 'bench' ? <BenchPage robot={robot} /> : null}
        {nav.view === 'compare' ? <ComparePage robot={robot} /> : null}
        {nav.view === 'check' ? <CheckPage robot={robot} initialMove={nav.move} /> : null}
      </main>
    </div>
  )
}
