// Reserve windows before awaiting the network so the click's activation is retained.
export function reserveTabs(count, browser = window) {
  const tabs = []
  for (let i = 0; i < count; i++) {
    try {
      const tab = browser.open('about:blank', '_blank')
      if (!tab) break
      tabs.push(tab)
      tab.opener = null
    } catch {
      tabs.forEach((tab) => tab.close())
      throw new Error('Could not reserve browser tabs')
    }
  }
  return tabs
}

export function webUrl(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

export async function openJobs(tabs, rows, recordVisit) {
  tabs = tabs.filter((tab) => !tab.closed)
  const visits = []
  let invalid = 0
  let opened = 0
  for (const row of rows) {
    const url = webUrl(row.data?.url)
    if (!url) { invalid++; continue }
    const tab = tabs[opened]
    if (!tab) break
    try {
      if (tab.closed) continue
      tab.location.replace(url)
      opened++
      visits.push(Promise.resolve().then(() => recordVisit(row.id)))
    } catch { invalid++ }
  }
  tabs.slice(opened).forEach((tab) => tab.close())
  const results = await Promise.allSettled(visits)
  return { opened, invalid, failed: results.filter((r) => r.status === 'rejected').length }
}
