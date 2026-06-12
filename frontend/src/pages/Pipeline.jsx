export default function Pipeline() {
  return (
    <div className="container">
      <h2>Pipeline</h2>
      <p>CRM board view with jobs grouped by status.</p>
      <div className="pipeline-board">
        {['opened', 'applied', 'interview', 'rejected', 'offer', 'follow_up', 'not_applying'].map((status) => (
          <div className="pipeline-column" key={status}>
            <div className="pipeline-column-header">{status.replace('_', ' ')}</div>
            <div className="pipeline-column-body">
              <p style={{ color: '#9ca3af', fontSize: 13 }}>No items</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
