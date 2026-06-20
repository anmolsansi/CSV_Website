from app.scoring import compute_priority_score, triage_status, extract_skills


class TestPriorityScore:
    def test_high_match_low_age(self):
        row = {"resume_match_score": "90", "posted_age_days": "2"}
        score = compute_priority_score(row)
        assert score >= 80

    def test_low_match_high_age(self):
        row = {"resume_match_score": "20", "posted_age_days": "60"}
        score = compute_priority_score(row)
        assert score < 50

    def test_missing_fields(self):
        row = {}
        score = compute_priority_score(row)
        assert isinstance(score, (int, float))


class TestTriage:
    def test_greenhouse_positive(self):
        row = {"ats_group": "greenhouse", "sponsorship_status": "positive"}
        status = triage_status(row)
        assert status in ("green", "yellow")

    def test_unknown_ats(self):
        row = {"ats_group": "unknown", "sponsorship_status": "unknown"}
        status = triage_status(row)
        assert status in ("red", "yellow")


class TestSkills:
    def test_extract_skills(self):
        text = "We need Python, JavaScript, and React experience"
        skills = extract_skills(text)
        assert "python" in [s.lower() for s in skills]
        assert "javascript" in [s.lower() for s in skills]

    def test_empty_text(self):
        skills = extract_skills("")
        assert isinstance(skills, list)
