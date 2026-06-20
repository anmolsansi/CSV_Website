import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/', label: 'Job Links' },
  { to: '/applications', label: 'Applications' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/sessions', label: 'Sessions' },
  { to: '/saved-views', label: 'Saved Views' },
  { to: '/applypilot', label: 'ApplyPilot' },
  { to: '/duplicates', label: 'Duplicates' },
  { to: '/companies', label: 'Companies' },
  { to: '/import', label: 'Import' },
]

export default function Navigation() {
  return (
    <nav className="main-nav" role="navigation" aria-label="Main navigation">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          className={({ isActive }) => `nav-tab${isActive ? ' nav-tab-active' : ''}`}
          aria-current={({ isActive }) => isActive ? 'page' : undefined}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
