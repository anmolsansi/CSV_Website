from app.email_templates import weekly_digest


class TestEmailTemplates:
    def test_weekly_digest(self):
        html = weekly_digest(
            total_applications=25,
            new_applications=10,
            interviews=3,
            offers=1,
            top_companies=["Acme", "TechCorp"],
            weekly_stats={"monday": 5, "tuesday": 3, "wednesday": 2},
        )
        assert "25" in html
        assert "Acme" in html
        assert "<html" in html

    def test_weekly_digest_empty(self):
        html = weekly_digest(
            total_applications=0,
            new_applications=0,
            interviews=0,
            offers=0,
            top_companies=[],
            weekly_stats={},
        )
        assert "<html" in html
