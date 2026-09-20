import pytest
from sqlalchemy.exc import IntegrityError


def test_new_connection_has_function(sqlite_acceptance_engine):
    with sqlite_acceptance_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql(
            "SELECT jobgrid_numeric(?)",
            ("$1,000.50",),
        ).scalar_one() == pytest.approx(1000.5)
        assert connection.exec_driver_sql(
            "SELECT jobgrid_numeric(?)",
            ("invalid",),
        ).scalar_one() is None


def test_foreign_key_fixture_enforced(sqlite_acceptance_engine):
    with pytest.raises(IntegrityError):
        with sqlite_acceptance_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO oauth_identities (user_id, provider, provider_id)
                VALUES (?, ?, ?)
                """,
                (999999, "test", "missing-user"),
            )
