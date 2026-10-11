// Group the server-ordered page without changing row identities or selection scope.
export function groupKey(value, field) {
  const key = String(value ?? '').trim().toLowerCase()
  if (field === 'is_usa_role') {
    if (['true', 'yes', '1'].includes(key)) return 'usa'
    if (['false', 'no', '0'].includes(key)) return 'not usa'
    return ''
  }
  return key
}

export function groupLabel(value, field) {
  if (field === 'is_usa_role') {
    const key = groupKey(value, field)
    return key === 'usa' ? 'USA' : key === 'not usa' ? 'Not USA' : 'Unknown'
  }
  return String(value ?? '').trim() || 'Unknown'
}

export function groupTableRows(tableRows, field) {
  if (!field) return [{ key: '', label: '', rows: tableRows }]
  const groups = new Map()
  for (const row of tableRows) {
    const value = row.original.data?.[field]
    const key = groupKey(value, field)
    if (!groups.has(key)) groups.set(key, { key, label: groupLabel(value, field), rows: [] })
    groups.get(key).rows.push(row)
  }
  return [...groups.values()]
}
