import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/', label: 'Job Links' },
  { to: '/applications', label: 'Applications' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/sessions', label: 'Sessions' },
  { to: '/saved-views', label: 'Saved Views' },
]

export default function Navigation() {
  return (
    <nav className="main-nav">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          className={({ isActive }) => `nav-tab${isActive ? ' nav-tab-active' : ''}`}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
