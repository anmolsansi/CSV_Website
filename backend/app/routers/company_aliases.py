"""Owner-scoped company alias routes for JG-031.

Aliases are explicit user decisions. They only affect company grouping and never
merge, delete, or rewrite JobTrack application history.
"""

from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import CompanyAlias, JobTrack, User
from ..services.job_identity import JobIdentityError, normalize_company_alias_key


router = APIRouter(prefix="/crm/company-aliases", tags=["company-aliases"])

MAX_ALIAS_LENGTH = 320
MAX_ALIAS_RESULTS = 100


def _alias_key(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(422, f"{field} must be a string.")
    if len(value) > MAX_ALIAS_LENGTH:
        raise HTTPException(422, f"{field} must be at most {MAX_ALIAS_LENGTH} characters.")
    try:
        return normalize_company_alias_key(value)
    except JobIdentityError as exc:
        raise HTTPException(422, str(exc)) from exc


def _history_counts(db: Session, user_id: int, display_names: list[str]) -> dict[str, int]:
    keys = sorted({name.strip().lower() for name in display_names if name and name.strip()})
    if not keys:
        return {}

    company_expr = func.lower(func.trim(JobTrack.company))
    rows = (
        db.query(company_expr.label("company_key"), func.count(JobTrack.id).label("count"))
        .filter(JobTrack.user_id == user_id, company_expr.in_(keys))
        .group_by(company_expr)
        .all()
    )
    return {row.company_key: int(row.count) for row in rows}


def _group_response(
    db: Session,
    *,
    user_id: int,
    company: str,
    company_key: str | None,
    aliases: list[CompanyAlias],
) -> dict:
    names = [alias.display_name for alias in aliases]
    if not names:
        names = [company]
    counts = _history_counts(db, user_id, names)

    items = [
        {
            "id": alias.id,
            "alias_key": alias.alias_key,
            "display_name": alias.display_name,
            "company_key": alias.company_key,
            "history_count": counts.get(alias.display_name.strip().lower(), 0),
            "created_at": alias.created_at,
        }
        for alias in aliases
    ]
    return {
        "company": company,
        "company_key": company_key,
        "aliases": items,
        "group_history_count": sum(counts.values()),
    }


@router.get("")
def list_company_aliases(
    company: str | None = Query(None, max_length=MAX_ALIAS_LENGTH),
    limit: int = Query(MAX_ALIAS_RESULTS, ge=1, le=MAX_ALIAS_RESULTS),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(CompanyAlias).filter(CompanyAlias.user_id == user.id)

    if company is None:
        aliases = query.order_by(CompanyAlias.alias_key.asc()).limit(limit).all()
        counts = _history_counts(db, user.id, [alias.display_name for alias in aliases])
        return {
            "company": None,
            "company_key": None,
            "aliases": [
                {
                    "id": alias.id,
                    "alias_key": alias.alias_key,
                    "display_name": alias.display_name,
                    "company_key": alias.company_key,
                    "history_count": counts.get(alias.display_name.strip().lower(), 0),
                    "created_at": alias.created_at,
                }
                for alias in aliases
            ],
            "group_history_count": sum(counts.values()),
        }

    key = _alias_key(company, field="company")
    anchor = query.filter(CompanyAlias.alias_key == key).first()
    if anchor is None:
        return _group_response(
            db,
            user_id=user.id,
            company=company,
            company_key=None,
            aliases=[],
        )

    aliases = (
        query.filter(CompanyAlias.company_key == anchor.company_key)
        .order_by(CompanyAlias.alias_key.asc())
        .limit(limit)
        .all()
    )
    return _group_response(
        db,
        user_id=user.id,
        company=company,
        company_key=anchor.company_key,
        aliases=aliases,
    )


@router.post("")
def create_company_alias(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if set(payload) != {"company", "alias"}:
        raise HTTPException(422, "Request body must contain exactly company and alias.")

    company = payload.get("company")
    alias = payload.get("alias")
    company_key = _alias_key(company, field="company")
    alias_key = _alias_key(alias, field="alias")
    if company_key == alias_key:
        raise HTTPException(422, "Alias must be different from the selected company.")

    existing = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user.id,
            CompanyAlias.alias_key.in_([company_key, alias_key]),
        )
        .all()
    )
    by_key = {item.alias_key: item for item in existing}
    company_record = by_key.get(company_key)
    alias_record = by_key.get(alias_key)

    if alias_record is not None:
        if company_record is not None and alias_record.company_key == company_record.company_key:
            aliases = (
                db.query(CompanyAlias)
                .filter(
                    CompanyAlias.user_id == user.id,
                    CompanyAlias.company_key == company_record.company_key,
                )
                .order_by(CompanyAlias.alias_key.asc())
                .limit(MAX_ALIAS_RESULTS)
                .all()
            )
            response = _group_response(
                db,
                user_id=user.id,
                company=company,
                company_key=company_record.company_key,
                aliases=aliases,
            )
            response["created"] = False
            return response

        raise HTTPException(
            409,
            detail={
                "code": "alias_conflict",
                "fields": [
                    {
                        "field": "alias",
                        "message": "That company label already belongs to another alias group. Refresh and retry.",
                    }
                ],
                "proposed_label": alias,
            },
        )

    stable_company_key = company_record.company_key if company_record is not None else str(uuid4())
    if company_record is None:
        company_record = CompanyAlias(
            user_id=user.id,
            alias_key=company_key,
            display_name=company.strip(),
            company_key=stable_company_key,
        )
        db.add(company_record)

    new_alias = CompanyAlias(
        user_id=user.id,
        alias_key=alias_key,
        display_name=alias.strip(),
        company_key=stable_company_key,
    )
    db.add(new_alias)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            detail={
                "code": "alias_conflict",
                "fields": [
                    {
                        "field": "alias",
                        "message": "Company aliases changed while you were editing. Refresh and retry.",
                    }
                ],
                "proposed_label": alias,
            },
        ) from exc

    aliases = (
        db.query(CompanyAlias)
        .filter(
            CompanyAlias.user_id == user.id,
            CompanyAlias.company_key == stable_company_key,
        )
        .order_by(CompanyAlias.alias_key.asc())
        .limit(MAX_ALIAS_RESULTS)
        .all()
    )
    response = _group_response(
        db,
        user_id=user.id,
        company=company,
        company_key=stable_company_key,
        aliases=aliases,
    )
    response["created"] = True
    return response


@router.delete("/{alias_id}")
def delete_company_alias(
    alias_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = (
        db.query(CompanyAlias)
        .filter(CompanyAlias.id == alias_id, CompanyAlias.user_id == user.id)
        .first()
    )
    if item is None:
        raise HTTPException(404, "Company alias not found")

    counts = _history_counts(db, user.id, [item.display_name])
    response = {
        "deleted": item.id,
        "display_name": item.display_name,
        "history_count": counts.get(item.display_name.strip().lower(), 0),
    }
    db.delete(item)
    db.commit()
    return response
