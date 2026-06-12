export default function Sessions() {
  return (
    <div className="container">
      <h2>Sessions</h2>
      <p>Track job-search sessions: dates, CSVs uploaded, URLs opened, applications submitted.</p>
      <div className="empty-state">
        <p>No sessions recorded yet.</p>
        <p style={{ color: '#9ca3af', fontSize: 13 }}>Sessions will appear here as you upload CSVs and open URLs.</p>
      </div>
    </div>
  )
}
