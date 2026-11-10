import { useEffect, useState } from 'react'
import { STYLES } from './styles.js'
import { LOGO } from './logo.js'
import { surface } from './platform.js'
import { RobotPicker, useApi } from './ui.jsx'
import { Gallery } from './views/gallery.jsx'
import { RobotPage } from './views/robot.jsx'
import { BenchPage } from './views/bench.jsx'
import { ComparePage } from './views/compare.jsx'
import { CheckPage } from './views/check.jsx'
import { ArenaPage } from './views/arena.jsx'
import { NewRobot } from './views/newrobot.jsx'

const TABS = [
  ['gallery', 'Gallery'],
  ['arena', 'Arena', true],
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
          <img className="tb-logo" src={LOGO} alt="" width="34" height="34" />
          <div>
            <div className="tb-title">Talaria Bench</div>
            <div className="tb-tagline">Test before it moves · simulation</div>
          </div>
        </div>
        <nav className="tb-tabs" role="tablist">
          {TABS.map(([id, label, feature]) => (
            <button key={id} type="button" role="tab" aria-selected={nav.view === id}
              className={'tb-tab' + (feature ? ' tb-tab-feature' : '') + (nav.view === id ? ' tb-active' : '')} onClick={() => go(id, robot)}>{label}</button>
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
        {nav.view === 'arena' ? <ArenaPage robot={robot} go={go} /> : null}
        {nav.view === 'robot' ? <RobotPage robot={robot} go={go} refresh={refresh} /> : null}
        {nav.view === 'bench' ? <BenchPage robot={robot} /> : null}
        {nav.view === 'compare' ? <ComparePage robot={robot} /> : null}
        {nav.view === 'check' ? <CheckPage robot={robot} initialMove={nav.move} /> : null}
      </main>
    </div>
  )
}
