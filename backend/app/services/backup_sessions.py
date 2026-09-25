"""Transaction ownership shared by the versioned backup sections."""

from contextlib import contextmanager
from functools import wraps

from sqlalchemy.orm import Session


@contextmanager
def restore_session(db: Session):
    if db.info.get("backup_restore"):
        yield db
        return
    # Never commit or roll back unrelated pending work in the request session.
    bind = db.get_bind()
    with Session(bind=getattr(bind, "engine", bind), autoflush=False,
                 expire_on_commit=False, info={"backup_restore": True}) as session:
        with session.begin():
            # Ensure nested replay savepoints cannot become the outer SQLite
            # transaction under sqlite3's legacy transaction control.
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN")
            yield session


def atomic_restore(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        with restore_session(db) as session:
            from ..models import User

            user_id = args[0] if args else kwargs["user_id"]
            session.query(User).filter(User.id == user_id).with_for_update().one()
            return function(session, *args, **kwargs)
    return wrapped


def snapshot_export(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        if db.info.get("backup_snapshot"):
            return function(db, *args, **kwargs)
        bind = db.get_bind()
        engine = getattr(bind, "engine", bind)
        isolation = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"
        with engine.connect().execution_options(isolation_level=isolation) as connection:
            with Session(bind=connection, autoflush=False, expire_on_commit=False,
                         info={"backup_snapshot": True}) as session:
                with session.begin():
                    # sqlite3 legacy transaction mode does not BEGIN on SELECT.
                    if engine.dialect.name == "sqlite":
                        session.connection().exec_driver_sql("BEGIN")
                    return function(session, *args, **kwargs)
    return wrapped
