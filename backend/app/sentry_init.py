import logging

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {"password", "secret", "token", "authorization", "session_token", "smtp_pass", "access_token"}


def _sanitize(event, hint):
    """Strip sensitive data from Sentry events before sending."""
    if "request" in event:
        headers = event["request"].get("headers", {})
        event["request"]["headers"] = {
            k: v if k.lower() not in _SENSITIVE_KEYS else "[Filtered]"
            for k, v in headers.items()
        }
    if "extra" in event:
        event["extra"] = {
            k: v if k.lower() not in _SENSITIVE_KEYS else "[Filtered]"
            for k, v in event["extra"].items()
        }
    return event


def init_sentry(dsn: str, environment: str = "development"):
    """Initialize Sentry SDK if a DSN is configured."""
    if not dsn:
        logger.info("Sentry DSN not configured, skipping Sentry initialization")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=0.2,
            integrations=[FastApiIntegration()],
            before_send=_sanitize,
            send_default_pii=False,
        )
        logger.info("Sentry initialized for environment=%s", environment)
    except Exception as exc:
        logger.warning("Failed to initialize Sentry: %s", exc)
