"""Shared numeric parsing and SQL adapters for text-backed JobGrid fields."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import sqlite3

from sqlalchemy import Numeric, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


MAX_NUMERIC_TEXT_LENGTH = 128

# Numeric source columns are intentionally stored as text. The parser accepts
# only the separators defined by the R6 contract and never rewrites source data.
_SEPARATOR_RE = re.compile(r"[%,$\s]")
_NORMALIZED_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")

_POSTGRES_SEPARATOR_PATTERN = r"[[:space:]%,$]"
_POSTGRES_NUMBER_PATTERN = r"^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$"


def parse_numeric_text(value: object) -> Decimal | None:
    """Return one finite Decimal for accepted text, otherwise None.

    The 128-character cap is applied to the original text before separator
    removal. Invalid, empty, overlong, or non-finite input is never coerced to
    zero.
    """

    if value is None:
        return None

    text = str(value)
    if len(text) > MAX_NUMERIC_TEXT_LENGTH:
        return None

    cleaned = _SEPARATOR_RE.sub("", text)
    if not cleaned or _NORMALIZED_NUMBER_RE.fullmatch(cleaned) is None:
        return None

    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None

    return parsed if parsed.is_finite() else None


def _sqlite_numeric(value: object) -> float | None:
    parsed = parse_numeric_text(value)
    return float(parsed) if parsed is not None else None


def _register_sqlite_numeric(
    dbapi_connection: object,
    _connection_record: object,
) -> None:
    """Register the deterministic SQLite scalar on each SQLite connection."""

    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "jobgrid_numeric",
            1,
            _sqlite_numeric,
            deterministic=True,
        )


def install_sqlite_numeric_adapter() -> None:
    """Install the SQLite connection listener once for all SQLAlchemy engines."""

    if not event.contains(Engine, "connect", _register_sqlite_numeric):
        event.listen(Engine, "connect", _register_sqlite_numeric)


class NumericTextExpression(FunctionElement):
    """Dialect-compiled numeric view of one text-backed SQL expression."""

    type = Numeric()
    inherit_cache = True
    name = "jobgrid_numeric_value"


def numeric_text_expression(column: object) -> NumericTextExpression:
    """Build the shared dialect-aware numeric SQL expression."""

    return NumericTextExpression(column)


@compiles(NumericTextExpression, "sqlite")
def _compile_sqlite_numeric(element, compiler, **kw):
    column_sql = compiler.process(list(element.clauses)[0], **kw)
    return f"jobgrid_numeric({column_sql})"


@compiles(NumericTextExpression, "postgresql")
def _compile_postgresql_numeric(element, compiler, **kw):
    column_sql = compiler.process(list(element.clauses)[0], **kw)
    cleaned_sql = (
        f"regexp_replace({column_sql}, "
        f"'{_POSTGRES_SEPARATOR_PATTERN}', '', 'g')"
    )
    return (
        "CASE "
        f"WHEN char_length({column_sql}) > {MAX_NUMERIC_TEXT_LENGTH} THEN NULL "
        f"WHEN {cleaned_sql} ~ '{_POSTGRES_NUMBER_PATTERN}' "
        f"THEN CAST({cleaned_sql} AS NUMERIC) "
        "ELSE NULL END"
    )
