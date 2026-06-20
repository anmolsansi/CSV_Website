from app.scoring import priority_score, improved_triage, skills_extraction


class TestPriorityScore:
    def test_high_match_low_age(self):
        row = {"resume_match_score": "90", "posted_age_days": "2"}
        score = priority_score(row)
        assert score >= 50

    def test_low_match_high_age(self):
        row = {"resume_match_score": "20", "posted_age_days": "60"}
        score = priority_score(row)
        assert score < 80

    def test_missing_fields(self):
        row = {}
        score = priority_score(row)
        assert isinstance(score, (int, float))


class TestTriage:
    def test_greenhouse_positive(self):
        row = {"ats_group": "greenhouse", "sponsorship_status": "positive"}
        score = priority_score(row)
        status = improved_triage(row, score=score)
        assert isinstance(status, str)

    def test_unknown_ats(self):
        row = {"ats_group": "unknown", "sponsorship_status": "unknown"}
        score = priority_score(row)
        status = improved_triage(row, score=score)
        assert isinstance(status, str)


class TestSkills:
    def test_extract_skills(self):
        text = "We need Python, JavaScript, and React experience"
        skills = skills_extraction(text)
        assert isinstance(skills, list)

    def test_empty_text(self):
        skills = skills_extraction("")
        assert isinstance(skills, list)
