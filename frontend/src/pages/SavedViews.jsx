export default function SavedViews() {
  return (
    <div className="container">
      <h2>Saved Views</h2>
      <p>Save and recall filter combinations for quick access.</p>
      <div className="empty-state">
        <p>No saved views yet.</p>
        <p style={{ color: '#9ca3af', fontSize: 13 }}>Create saved views from the Job Links or Applications filters.</p>
      </div>
    </div>
  )
}
