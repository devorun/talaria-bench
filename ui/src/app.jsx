import { useState } from 'react'
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
  const [robots, loading] = useApi('/robots')
  const list = robots && robots.ok ? robots.robots : null
  const [nav, setNav] = useState(initial || { view: 'gallery', robot: 'caduceus', move: null })
  const go = (view, robot, move = null) => setNav({ view, robot: robot || nav.robot, move })
  const robot = nav.robot
  return (
    <div className={'tb-root tb-surface-' + surface()}>
      <style>{STYLES}</style>
      <header className="tb-header">
        <div className="tb-brand">
          <div className="tb-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 18 L12 4 L20 18 M8 12 H16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
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
        {nav.view === 'new' ? <NewRobot go={go} /> : null}
        {nav.view === 'robot' ? <RobotPage robot={robot} go={go} /> : null}
        {nav.view === 'bench' ? <BenchPage robot={robot} /> : null}
        {nav.view === 'compare' ? <ComparePage robot={robot} /> : null}
        {nav.view === 'check' ? <CheckPage robot={robot} initialMove={nav.move} /> : null}
      </main>
    </div>
  )
}
