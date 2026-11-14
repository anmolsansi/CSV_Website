import { APPLICATION_TABS } from '../utils/applicationLedgerViews'

export default function ApplicationLedgerTabs({ activeTab, onChange }) {
  return (
    <div className="application-view-tabs" role="tablist" aria-label="Application views">
      {APPLICATION_TABS.map(({ id, label, description }) => (
        <button
          key={id}
          type="button"
          role="tab"
          className={activeTab === id ? 'application-view-tab active' : 'application-view-tab'}
          aria-selected={activeTab === id}
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
