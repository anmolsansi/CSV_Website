from datetime import datetime


def weekly_digest(subject: str, data: dict) -> str:
    """Return a full HTML email string for the weekly digest."""
    uploaded = data.get("uploaded", 0)
    opened = data.get("opened", 0)
    applied = data.get("applied", 0)
    interviews = data.get("interviews", 0)
    followups_completed = data.get("followups_completed", 0)
    top_companies = data.get("top_companies", [])
    upcoming_followups = data.get("upcoming_followups", [])
    goal_progress = data.get("goal_progress", {})

    goals = goal_progress.get("goals", {})
    today = goal_progress.get("today", {})

    def _pct(current, target):
        if not target:
            return 0
        return min(round(current / target * 100), 100)

    companies_html = ""
    for c in top_companies:
        companies_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:500;">{c['name']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;color:#6366f1;">{c['count']}</td>
        </tr>"""

    if not companies_html:
        companies_html = '<tr><td colspan="2" style="padding:8px 12px;color:#94a3b8;">No activity this week</td></tr>'

    followups_html = ""
    for f in upcoming_followups:
        try:
            dt = datetime.fromisoformat(f["follow_up_at"].replace("Z", "+00:00"))
            dt_str = dt.strftime("%b %d, %I:%M %p")
        except Exception:
            dt_str = f["follow_up_at"]
        followups_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">{f.get('company', 'N/A')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">{f.get('title', '')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#6366f1;">{dt_str}</td>
        </tr>"""

    if not followups_html:
        followups_html = '<tr><td colspan="3" style="padding:8px 12px;color:#94a3b8;">No upcoming follow-ups scheduled</td></tr>'

    def _goal_row(label, current, target):
        pct = _pct(current, target)
        bar_color = "#22c55e" if pct >= 100 else "#6366f1" if pct >= 50 else "#f59e0b"
        return f"""
        <div style="margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
            <span style="font-size:14px;color:#334155;">{label}</span>
            <span style="font-size:14px;color:#64748b;">{current} / {target}</span>
          </div>
          <div style="background:#e2e8f0;border-radius:4px;height:8px;overflow:hidden;">
            <div style="background:{bar_color};height:100%;width:{pct}%;border-radius:4px;"></div>
          </div>
        </div>"""

    goals_html = ""
    if goals:
        goals_html = _goal_row("Jobs Opened", today.get("opened", 0), goals.get("open_per_day", 30))
        goals_html += _goal_row("Applications", today.get("applied", 0), goals.get("apply_per_day", 10))
        goals_html += _goal_row("Follow-ups", today.get("followups", 0), goals.get("followup_per_day", 5))

    now_str = datetime.utcnow().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
    <tr>
      <td style="padding:32px 16px;text-align:center;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);margin:0 auto;">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px 40px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;">{subject}</h1>
              <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">JobGrid Weekly Job Search Digest</p>
            </td>
          </tr>

          <!-- Date -->
          <tr>
            <td style="padding:24px 40px 0;text-align:center;">
              <p style="margin:0;color:#94a3b8;font-size:13px;">Week ending {now_str}</p>
            </td>
          </tr>

          <!-- Stats Grid -->
          <tr>
            <td style="padding:24px 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="25%" style="text-align:center;padding:16px 8px;background:#f8fafc;border-radius:8px;">
                    <div style="font-size:28px;font-weight:700;color:#6366f1;">{uploaded}</div>
                    <div style="font-size:12px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">Uploaded</div>
                  </td>
                  <td width="4%"></td>
                  <td width="25%" style="text-align:center;padding:16px 8px;background:#f8fafc;border-radius:8px;">
                    <div style="font-size:28px;font-weight:700;color:#6366f1;">{opened}</div>
                    <div style="font-size:12px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">Opened</div>
                  </td>
                  <td width="4%"></td>
                  <td width="25%" style="text-align:center;padding:16px 8px;background:#f8fafc;border-radius:8px;">
                    <div style="font-size:28px;font-weight:700;color:#6366f1;">{applied}</div>
                    <div style="font-size:12px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">Applied</div>
                  </td>
                  <td width="4%"></td>
                  <td width="25%" style="text-align:center;padding:16px 8px;background:#f8fafc;border-radius:8px;">
                    <div style="font-size:28px;font-weight:700;color:#6366f1;">{interviews}</div>
                    <div style="font-size:12px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">Interviews</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Follow-ups Completed -->
          <tr>
            <td style="padding:0 40px 24px;text-align:center;">
              <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;">
                <span style="font-size:20px;font-weight:700;color:#16a34a;">{followups_completed}</span>
                <span style="font-size:14px;color:#15803d;margin-left:8px;">follow-ups completed this week</span>
              </div>
            </td>
          </tr>

          <!-- Goal Progress -->
          {"<tr><td style='padding:0 40px 24px;'><h2 style='margin:0 0 16px;font-size:18px;color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px;'>Today's Goal Progress</h2><div style='padding:16px;background:#f8fafc;border-radius:8px;'>" + goals_html + "</div></td></tr>" if goals_html else ""}

          <!-- Top Companies -->
          <tr>
            <td style="padding:0 40px 24px;">
              <h2 style="margin:0 0 16px;font-size:18px;color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">Top Companies</h2>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 12px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Company</td>
                  <td style="padding:10px 12px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;text-align:center;">Jobs</td>
                </tr>
                {companies_html}
              </table>
            </td>
          </tr>

          <!-- Upcoming Follow-ups -->
          <tr>
            <td style="padding:0 40px 32px;">
              <h2 style="margin:0 0 16px;font-size:18px;color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">Upcoming Follow-ups</h2>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                <tr style="background:#f8fafc;">
                  <td style="padding:10px 12px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Company</td>
                  <td style="padding:10px 12px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Title</td>
                  <td style="padding:10px 12px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">When</td>
                </tr>
                {followups_html}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;padding:24px 40px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:13px;color:#94a3b8;">Sent from JobGrid &mdash; Your job search command center</p>
              <p style="margin:8px 0 0;font-size:12px;color:#cbd5e1;">This is an automated weekly digest.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
