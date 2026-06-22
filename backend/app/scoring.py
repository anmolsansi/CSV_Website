"""Enhanced scoring and triage module for JobGrid."""
import re
from datetime import datetime, timedelta

# --- Keyword banks for skills extraction ---

LANGUAGES = {
    "python", "javascript", "typescript", "java", "go", "golang", "rust", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl", "haskell",
    "elixir", "clojure", "groovy", "sql", "html", "css", "sass", "scss",
}

FRAMEWORKS = {
    "react", "react.js", "reactjs", "next.js", "nextjs", "vue", "vue.js", "vuejs",
    "angular", "angularjs", "svelte", "node", "node.js", "nodejs", "express",
    "fastapi", "django", "flask", "spring", "spring boot", "rails", "ruby on rails",
    "laravel", "symfony", "dotnet", ".net", "asp.net", "graphql", "rest", "restful",
    "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn", "pandas", "numpy",
}

TOOLS = {
    "aws", "gcp", "google cloud", "azure", "docker", "kubernetes", "k8s", "terraform",
    "ansible", "jenkins", "github actions", "gitlab ci", "ci/cd", "git", "github",
    "bitbucket", "jira", "confluence", "slack", "postgresql", "postgres", "mysql",
    "mongodb", "redis", "elasticsearch", "kafka", "rabbitmq", "nginx", "apache",
    "linux", "bash", "powershell", "vim", "vscode",
}

SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "problem-solving", "analytical", "critical thinking", "time management",
    "mentoring", "agile", "scrum", "kanban", "cross-functional",
}

ALL_SKILLS = LANGUAGES | FRAMEWORKS | TOOLS | SOFT_SKILLS

SEARCH_BUCKET_BOOSTS = {
    "ai": 5, "ml": 5, "machine_learning": 5, "data": 3, "backend": 2,
    "fullstack": 2, "full_stack": 2, "devops": 3, "cloud": 2, "security": 2,
}

ATS_SUCCESS_ADJUSTMENTS = {
    "greenhouse": 3, "lever": 2, "workday": -2, "icims": -1,
    "taleo": -3, "successfactors": -2, "smartrecruiters": 1,
    "ashby": 2, "bamboohr": 1, "jazz": 1,
}


def _parse_score(value):
    try:
        return float(str(value or "0").replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_age(value):
    try:
        return float(str(value or "999").replace(",", "").strip())
    except (ValueError, TypeError):
        return 999.0


def _get_value(row, key, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _has_value(row, key):
    if isinstance(row, dict):
        return key in row
    return hasattr(row, key)


def priority_score(row, track=None, company_apply_rate=None):
    """Compute a 0-100 priority score for a job row.

    Args:
        row: CsvRow-like object with CSV column attributes.
        track: Optional JobTrack-like object for application state.
        company_apply_rate: Optional float 0-1 representing historical apply rate
            for this company. Used for company quality bonus.
    """
    score = 0.0

    # --- Resume match (0-40 points) ---
    resume_raw = _parse_score(_get_value(row, "resume_match_score") or "0")
    score += min(resume_raw * 0.4, 40)

    # --- Sponsorship (+15 / +5 / -10) ---
    sponsor = (_get_value(row, "sponsorship_status") or "").lower()
    if sponsor == "positive":
        score += 15
    elif sponsor == "unclear":
        score += 5
    elif sponsor == "negative":
        score -= 10

    # --- Location (+10 remote, +5 onsite/hybrid, -5 restricted) ---
    loc = (_get_value(row, "location_group") or "").lower()
    if "remote" in loc and "restricted" not in loc:
        score += 10
    elif "onsite" in loc or "hybrid" in loc:
        score += 5
    elif "restricted" in loc:
        score -= 5

    # --- Posted age (+15 <7d, +10 <14d, +5 <30d, -5 >30d) ---
    age = _parse_age(_get_value(row, "posted_age_days"))
    if age <= 7:
        score += 15
    elif age <= 14:
        score += 10
    elif age <= 30:
        score += 5
    else:
        score -= 5

    # --- Duplicate penalty (-20) ---
    if _get_value(row, "is_duplicate", False):
        score -= 20

    # --- JD completeness (+10 >500 chars, +5 >200 chars, -10 missing) ---
    jd_text = _get_value(row, "jd_text")
    jd_len_attr = _get_value(row, "jd_text_length")
    if _has_value(row, "jd_text") or _has_value(row, "jd_text_length"):
        jd_len = _parse_score(jd_len_attr) if jd_len_attr else (len(jd_text) if jd_text else 0)
        if jd_len > 500:
            score += 10
        elif jd_len > 200:
            score += 5
        elif jd_len == 0 or not jd_text:
            score -= 10

    # --- Track-based adjustments ---
    if track:
        # Rejection penalty (-25)
        if getattr(track, "status", None) == "rejected":
            score -= 25

        # Follow-up urgency (+5 if overdue)
        follow_up = getattr(track, "follow_up_at", None)
        if follow_up and isinstance(follow_up, datetime) and follow_up < datetime.utcnow():
            score += 5

    # --- Company quality bonus ---
    if company_apply_rate is not None and company_apply_rate > 0:
        score += min(round(company_apply_rate * 10, 1), 10)

    # --- ATS-specific adjustment ---
    ats = (_get_value(row, "ats_group") or "").lower()
    score += ATS_SUCCESS_ADJUSTMENTS.get(ats, 0)

    # --- Search bucket adjustment ---
    bucket = (_get_value(row, "search_bucket") or "").lower().replace(" ", "_")
    score += SEARCH_BUCKET_BOOSTS.get(bucket, 0)

    return max(0, min(100, round(score, 1)))


def improved_triage(row, track=None, score=0):
    """Classify a job into triage buckets.

    Returns one of: apply_now, maybe, skip, needs_review.
    """
    # Skip conditions first
    if _get_value(row, "is_duplicate", False):
        return "skip"
    if (_get_value(row, "sponsorship_status") or "").lower() == "negative":
        return "skip"
    if track and getattr(track, "status", None) == "rejected":
        return "skip"
    age = _parse_age(_get_value(row, "posted_age_days"))
    if age > 60:
        return "skip"

    # Needs review: missing JD, has error, or borderline score
    jd_text = _get_value(row, "jd_text")
    jd_len_attr = _get_value(row, "jd_text_length")
    jd_len = _parse_score(jd_len_attr) if jd_len_attr else (len(jd_text) if jd_text else 0)
    has_jd = jd_len > 0 and jd_text

    if not has_jd:
        return "needs_review"
    if _get_value(row, "error"):
        return "needs_review"

    # Apply now: high score + JD present + not duplicate + sponsorship positive
    sponsor = (_get_value(row, "sponsorship_status") or "").lower()
    if score >= 70 and has_jd and sponsor in ("positive", ""):
        return "apply_now"

    # Maybe: decent score or moderate score with JD
    if score >= 40:
        return "maybe"
    if score >= 30 and has_jd:
        return "maybe"

    return "skip"


def skills_extraction(jd_text):
    """Extract technical skills from job description text.

    Returns dict with categories: languages, frameworks, tools, soft_skills,
    and a combined 'all_matched' list.
    """
    if not jd_text:
        return {
            "languages": [], "frameworks": [], "tools": [], "soft_skills": [],
            "all_matched": [],
        }

    text_lower = jd_text.lower()

    matched_langs = sorted(skill for skill in LANGUAGES if skill in text_lower)
    matched_fw = sorted(skill for skill in FRAMEWORKS if skill in text_lower)
    matched_tools = sorted(skill for skill in TOOLS if skill in text_lower)
    matched_soft = sorted(skill for skill in SOFT_SKILLS if skill in text_lower)

    all_matched = sorted(set(matched_langs + matched_fw + matched_tools + matched_soft))

    return {
        "languages": matched_langs,
        "frameworks": matched_fw,
        "tools": matched_tools,
        "soft_skills": matched_soft,
        "all_matched": all_matched,
    }


def resume_match_improved(jd_text, resume_text):
    """Keyword-based resume-to-JD matching.

    Returns:
        dict with match_percentage, matched_skills, missing_skills, suggestions.
    """
    if not jd_text or not resume_text:
        return {
            "match_percentage": 0,
            "matched_skills": [],
            "missing_skills": [],
            "suggestions": ["Provide both JD and resume text for matching."],
        }

    jd_skills = skills_extraction(jd_text)
    resume_lower = resume_text.lower()

    matched = []
    missing = []
    for skill in jd_skills["all_matched"]:
        if skill in resume_lower:
            matched.append(skill)
        else:
            missing.append(skill)

    total = len(jd_skills["all_matched"])
    pct = round(len(matched) / total * 100, 1) if total > 0 else 0

    suggestions = []
    if missing:
        suggestions.append(f"Consider adding these skills to your resume: {', '.join(missing[:5])}")
    if pct < 50:
        suggestions.append("Low match - may not be a strong fit for this role.")
    elif pct >= 80:
        suggestions.append("Strong match - good fit for this role.")
    if not suggestions:
        suggestions.append("Resume is well-aligned with this job description.")

    return {
        "match_percentage": pct,
        "matched_skills": matched,
        "missing_skills": missing,
        "suggestions": suggestions,
    }
