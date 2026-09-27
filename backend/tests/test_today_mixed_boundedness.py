from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import event

from app.models import User, WorkItem
from app.services.today_f8 import build_today_queue_with_interviews


SECRET = "c04-bounded-query-secret"
NOW = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)


def test_large_today_fixture_uses_bounded_candidate_query(db_session):
    user = User(
        email=f"c04-bounded-{uuid4()}@example.test",
        timezone="UTC",
    )
    db_session.add(user)
    db_session.flush()

    # Large enough to prove page retrieval does not materialize the full manual
    # population. Aggregate count queries may inspect all eligible rows, while
    # candidate object reads must remain LIMIT-bounded.
    for index in range(250):
        db_session.add(
            WorkItem(
                user_id=user.id,
                description=f"Bounded action {index}",
                due_at=NOW + timedelta(minutes=index + 1),
                priority=index % 4,
                state="pending",
                version=1,
            )
        )
    db_session.flush()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.split()).lower())

    event.listen(db_session.bind, "before_cursor_execute", record_statement)
    try:
        page = build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name="UTC",
            secret_key=SECRET,
            limit=2,
            now=NOW,
        )
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record_statement)

    assert page["counts"]["total"] == 250
    assert len(page["items"]) == 2
    assert page["next_cursor"] is not None

    candidate_reads = [
        statement
        for statement in statements
        if " from work_items " in f" {statement} "
        and "count(" not in statement
        and "sum(" not in statement
    ]
    assert candidate_reads
    assert all(" limit " in f" {statement} " for statement in candidate_reads)

    # Query count is fixed by source types plus count/override queries, not by
    # the 250-row fixture. This records the current measured ceiling without
    # inventing a latency SLA.
    assert len(statements) <= 12
