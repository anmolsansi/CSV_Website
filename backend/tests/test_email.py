from app.email_templates import weekly_digest


class TestEmailTemplates:
    def test_weekly_digest(self):
        html = weekly_digest(
            subject="Weekly Digest",
            data={
                "total_opened": 25,
                "total_applied": 10,
                "interviews": 3,
                "offers": 1,
                "goal_progress": {"open_per_day": 30, "apply_per_day": 10},
            },
        )
        assert "Weekly Digest" in html
        assert "<html" in html

    def test_weekly_digest_empty(self):
        html = weekly_digest(
            subject="Empty Digest",
            data={},
        )
        assert "<html" in html
