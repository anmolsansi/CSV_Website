from types import SimpleNamespace

from app.services.imports import _acquire_account_import_lock


class _FakeSession:
    def __init__(self, dialect_name: str):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.calls: list[tuple[str, dict[str, int]]] = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))


def test_sqlite_import_lock_serializes_via_owner_row_write():
    db = _FakeSession("sqlite")

    _acquire_account_import_lock(db, user_id=17)

    assert db.calls == [
        ("UPDATE users SET id = id WHERE id = :user_id", {"user_id": 17})
    ]


def test_postgres_import_lock_uses_account_advisory_transaction_lock():
    db = _FakeSession("postgresql")

    _acquire_account_import_lock(db, user_id=17)

    assert len(db.calls) == 1
    statement, params = db.calls[0]
    assert statement == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert params["lock_key"] == 0x4A47000000000000 + 17
