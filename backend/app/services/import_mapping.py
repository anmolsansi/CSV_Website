from __future__ import annotations

from ..import_models import ImportMapping
from ..import_schemas import ImportContractError, header_fingerprint, validate_mapping


def mapping_for_headers(mapping: ImportMapping, headers: list[str]) -> dict[str, str]:
    """Return a reusable mapping only when the exact header sequence still matches.

    Saved mappings are positional. Reordering, adding, removing, or renaming a
    source column requires an explicit remap instead of silently applying a
    mapping to the wrong source values.
    """
    actual_fingerprint = header_fingerprint(headers)
    if mapping.header_fingerprint != actual_fingerprint:
        raise ImportContractError(
            "saved_mapping_header_mismatch",
            "Saved mapping does not match this file's exact column sequence. Remap the columns explicitly.",
            status_code=409,
            field="mapping",
        )
    return validate_mapping(mapping.mapping_json, column_count=len(headers))
