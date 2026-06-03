import { useRef, useState } from 'react'
import { api } from '../api/client'

export default function CsvUpload({ onUploaded }) {
  const inputRef = useRef()
  const [status, setStatus] = useState('')

  const handleChange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setStatus('Uploading...')
    try {
      const res = await api.uploadCsv(file)
      setStatus(
        `Inserted ${res.inserted}, skipped ${res.skipped_duplicates} duplicate(s).`
      )
      onUploaded()
    } catch (err) {
      setStatus(err.response?.data?.detail || 'Upload failed')
    } finally {
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div style={{ margin: '1rem 0' }}>
      <input ref={inputRef} type="file" accept=".csv" onChange={handleChange} />
      {status && <span style={{ marginLeft: 12 }}>{status}</span>}
    </div>
  )
}
