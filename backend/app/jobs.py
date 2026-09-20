import logging


logger = logging.getLogger(__name__)


def cleanup_clicked_rows() -> int:
    """Compatibility shim for the retired implicit cleanup policy.

    JG-012 intentionally disables the old DELETE_AFTER_DAYS behavior because it
    mixed automatic archive with hard deletion and could not represent when a
    row was archived. JG-013 owns the replacement bounded archive worker.

    Returning zero preserves the existing callable contract without mutating
    user data.
    """
    logger.info(
        "cleanup_clicked_rows outcome=disabled reason=retired_legacy_policy"
    )
    return 0
