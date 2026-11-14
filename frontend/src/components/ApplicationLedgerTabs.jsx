import { APPLICATION_TABS } from '../utils/applicationLedgerViews'

export default function ApplicationLedgerTabs({ activeTab, onChange }) {
  const onTabKeyDown = (event, index) => {
    let next = index
    if (event.key === 'ArrowRight') next = (index + 1) % APPLICATION_TABS.length
    else if (event.key === 'ArrowLeft') next = (index - 1 + APPLICATION_TABS.length) % APPLICATION_TABS.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = APPLICATION_TABS.length - 1
    else return
    event.preventDefault()
    const target = event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next]
    target?.focus()
    onChange(APPLICATION_TABS[next].id)
  }
  return (
    <div className="application-view-tabs" role="tablist" aria-label="Application views">
      {APPLICATION_TABS.map(({ id, label, description }, index) => (
        <button
          key={id}
          type="button"
          role="tab"
          className={activeTab === id ? 'application-view-tab active' : 'application-view-tab'}
          aria-selected={activeTab === id}
          tabIndex={activeTab === id ? 0 : -1}
          onKeyDown={(event) => onTabKeyDown(event, index)}
          aria-controls="application-ledger-results"
          title={description}
          onClick={() => onChange(id)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
