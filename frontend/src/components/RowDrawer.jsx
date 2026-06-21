import { useEffect, useState } from 'react'
import { api } from '../api/client'

const CSV_FIELD_LABELS = {
  ats_group: 'ATS Group', location_group: 'Location Group', search_bucket: 'Search Bucket',
  title: 'Title', title_match_status: 'Title Match', title_reject_reason: 'Title Reject Reason',
  url: 'URL', display_domain: 'Display Domain', company_guess: 'Company',
  job_id_guess: 'Job ID', canonical_company_job_key: 'Canonical Key', page_number: 'Page',
  decision: 'Decision', rejection_reasons: 'Rejection Reasons', posted_status: 'Posted Status',
  posted_value: 'Posted Value', posted_source: 'Posted Source', posted_age_days: 'Posted Age (days)',
  location_status: 'Location Status', location_evidence: 'Location Evidence',
  sponsorship_status: 'Sponsorship', positive_sponsorship_matches: 'Positive Sponsorship',
  negative_sponsorship_matches: 'Negative Sponsorship', sponsorship_evidence_snippet: 'Sponsorship Evidence',
  positive_sponsorship_evidence_snippet: 'Positive Sponsorship Evidence',
  clearance_matches: 'Clearance', clearance_evidence_snippet: 'Clearance Evidence',
  jd_text_length: 'JD Text Length', jd_text: 'JD Text', extraction_method: 'Extraction Method',
  retry_attempted: 'Retry Attempted', error: 'Error', resume_match_score: 'Resume Score',
  application_url: 'Application URL', application_dedupe_key: 'App Dedupe Key',
  source_file: 'Source File', is_usa_role: 'USA Role',
  location_country: 'Country', location_city: 'City', location_state: 'State',
  location_raw_extracted: 'Raw Location', location_confidence: 'Location Confidence', location_source: 'Location Source',
  work_model_extracted: 'Work Model', salary_min_extracted: 'Salary Min', salary_max_extracted: 'Salary Max', salary_currency_extracted: 'Currency',
  posted_status_extracted: 'Posted Status (ext)', posted_value_extracted: 'Posted Value (ext)',
  posted_source_extracted: 'Posted Source (ext)', posted_age_days_extracted: 'Posted Age (ext)',
  sponsorship_status_extracted: 'Sponsorship (ext)', positive_sponsorship_matches_extracted: 'Positive Sponsorship (ext)',
  negative_sponsorship_matches_extracted: 'Negative Sponsorship (ext)',
  positive_sponsorship_evidence_extracted: 'Positive Sponsorship Evidence (ext)',
  negative_sponsorship_evidence_extracted: 'Negative Sponsorship Evidence (ext)',
  clearance_or_citizenship_extracted: 'Clearance (ext)', clearance_or_citizenship_evidence_extracted: 'Clearance Evidence (ext)',
  education_requirement_extracted: 'Education', employment_type_extracted: 'Employment Type',
  resume_score: 'Resume Score (alt)', fit_category: 'Fit Category', score_confidence: 'Score Confidence',
  role_family: 'Role Family', seniority_level: 'Seniority', required_years_min: 'Min Years Required',
  core_languages_extracted: 'Core Languages', core_frameworks_extracted: 'Core Frameworks',
  core_cloud_devops_extracted: 'Cloud/DevOps', database_requirements_extracted: 'Database Requirements',
  ai_ml_requirements_extracted: 'AI/ML Requirements', matched_resume_skills: 'Matched Skills',
  missing_or_weaker_skills: 'Missing Skills', score_reason: 'Score Reason',
  closed_or_unusable_jd: 'Closed/Unusable JD', closed_or_unusable_reason: 'JD Unusable Reason',
  jd_quality_status: 'JD Quality', jd_quality_reasons: 'JD Quality Reasons',
}

function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
}

const TRIAGE_COLORS = {
  apply_now: { bg: '#d1fae5', color: '#065f46', label: 'Apply First' },
  maybe: { bg: '#fef3c7', color: '#92400e', label: 'Review Later' },
  skip: { bg: '#fee2e2', color: '#991b1b', label: 'Skip' },
  needs_review: { bg: '#e0e7ff', color: '#3730a3', label: 'Needs Review' },
}

export default function RowDrawer({ row, onClose }) {
  const [intelligence, setIntelligence] = useState(null)
  const [summary, setSummary] = useState(null)
  const [checklist, setChecklist] = useState(null)
  const [loadingIntel, setLoadingIntel] = useState(false)

  useEffect(() => {
    if (!row?.id) return
    setLoadingIntel(true)
    Promise.all([
      api.getPriorityScore(row.id).catch(() => null),
      api.getJobSummary(row.id).catch(() => null),
      api.getResumeChecklist(row.id).catch(() => null),
    ]).then(([intel, sum, check]) => {
      setIntelligence(intel)
      setSummary(sum?.summary || null)
      setChecklist(check?.checklist || null)
    }).finally(() => setLoadingIntel(false))
  }, [row?.id])

  if (!row) return null
  const data = row.data || {}
  const triageStyle = intelligence?.triage ? TRIAGE_COLORS[intelligence.triage] : null

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer-panel">
        <div className="drawer-header">
          <div>
            <h3>{data.company_guess || 'Unknown Company'}</h3>
            <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: 14 }}>{data.title || 'Untitled Position'}</p>
          </div>
          <button className="drawer-close" onClick={onClose}>×</button>
        </div>

        {intelligence && (
          <div className="drawer-section" style={{ background: '#f9fafb', borderRadius: 8, padding: 12, marginBottom: 16 }}>
            <h4>Triage</h4>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: 12, color: '#6b7280' }}>Priority Score</span>
                <strong style={{ display: 'block', fontSize: 24 }}>{intelligence.priority_score}</strong>
              </div>
              {triageStyle && (
                <span style={{ padding: '4px 12px', borderRadius: 6, fontSize: 13, fontWeight: 600, background: triageStyle.bg, color: triageStyle.color }}>
                  {triageStyle.label}
                </span>
              )}
            </div>
          </div>
        )}

        {loadingIntel && <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>Loading intelligence...</div>}

        <div className="drawer-section">
          <h4>Job Details</h4>
          <div className="drawer-field"><span className="drawer-field-label">URL</span><a className="drawer-field-value" href={data.url} target="_blank" rel="noopener noreferrer">{data.url || '-'}</a></div>
          <div className="drawer-field"><span className="drawer-field-label">ATS Group</span><span className="drawer-field-value">{data.ats_group || '-'}</span></div>
          <div className="drawer-field"><span className="drawer-field-label">Search Bucket</span><span className="drawer-field-value">{data.search_bucket || '-'}</span></div>
          <div className="drawer-field"><span className="drawer-field-label">Resume Score</span><span className="drawer-field-value">{data.resume_match_score || '-'}</span></div>
          <div className="drawer-field"><span className="drawer-field-label">Decision</span><span className="drawer-field-value">{data.decision || '-'}</span></div>
        </div>

        <div className="drawer-section">
          <h4>Application Status</h4>
          {row.app_status && <span className={`app-status-badge ${row.app_status}`}>{row.app_status}</span>}
          {row.applied_at && <div className="drawer-field"><span className="drawer-field-label">Applied</span><span className="drawer-field-value">{formatDate(row.applied_at)}</span></div>}
          {row.follow_up_at && <div className="drawer-field"><span className="drawer-field-label">Follow-up</span><span className="drawer-field-value">{formatDate(row.follow_up_at)}</span></div>}
          {row.app_notes && <div className="drawer-field"><span className="drawer-field-label">Notes</span><span className="drawer-field-value">{row.app_notes}</span></div>}
        </div>

        {summary && (
          <div className="drawer-section">
            <h4>AI Summary</h4>
            <p style={{ fontSize: 13, lineHeight: 1.5 }}>{summary.summary}</p>
            {summary.matched_skills?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: 12 }}>Matched skills:</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {summary.matched_skills.map((s) => <span key={s} style={{ padding: '2px 6px', background: '#dbeafe', color: '#1e40af', borderRadius: 4, fontSize: 11 }}>{s}</span>)}
                </div>
              </div>
            )}
            {summary.risks?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: 12, color: '#dc2626' }}>Risks:</strong>
                {summary.risks.map((r, i) => <div key={i} style={{ fontSize: 12, color: '#991b1b' }}>{r}</div>)}
              </div>
            )}
          </div>
        )}

        {checklist && (
          <div className="drawer-section">
            <h4>Resume Checklist</h4>
            {checklist.required_skills?.length > 0 && (
              <div>
                <strong style={{ fontSize: 12 }}>Required skills:</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {checklist.required_skills.map((s) => <span key={s} style={{ padding: '2px 6px', background: '#f3f4f6', color: '#374151', borderRadius: 4, fontSize: 11 }}>{s}</span>)}
                </div>
              </div>
            )}
            {checklist.suggested_bullets?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: 12 }}>Suggested bullets:</strong>
                {checklist.suggested_bullets.map((b, i) => <div key={i} style={{ fontSize: 12, color: '#374151' }}>• {b}</div>)}
              </div>
            )}
            {checklist.suggested_project && <div style={{ marginTop: 8, fontSize: 12, color: '#374151' }}><strong>Project:</strong> {checklist.suggested_project}</div>}
          </div>
        )}

        <div className="drawer-section">
          <h4>Sponsorship</h4>
          <div className="drawer-field"><span className="drawer-field-label">Status</span><span className="drawer-field-value">{data.sponsorship_status || '-'}</span></div>
          {data.sponsorship_evidence_snippet && <div className="drawer-field"><span className="drawer-field-label">Evidence</span><span className="drawer-field-value">{data.sponsorship_evidence_snippet}</span></div>}
        </div>

        <div className="drawer-section">
          <h4>Location</h4>
          <div className="drawer-field"><span className="drawer-field-label">Group</span><span className="drawer-field-value">{data.location_group || '-'}</span></div>
          {data.location_evidence && <div className="drawer-field"><span className="drawer-field-label">Evidence</span><span className="drawer-field-value">{data.location_evidence}</span></div>}
        </div>

        {data.jd_text && (
          <div className="drawer-section">
            <h4>Job Description</h4>
            <div className="drawer-jd">{data.jd_text}</div>
          </div>
        )}

        <div className="drawer-section">
          <h4>All CSV Fields</h4>
          {Object.entries(CSV_FIELD_LABELS).map(([key, label]) => (
            data[key] ? (
              <div className="drawer-field" key={key}>
                <span className="drawer-field-label">{label}</span>
                <span className="drawer-field-value" style={{ fontSize: 12 }}>{data[key]}</span>
              </div>
            ) : null
          ))}
        </div>
      </div>
    </>
  )
}
