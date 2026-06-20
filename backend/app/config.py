import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/csvapp",
    )
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    # Use 'common' for multi-tenant + personal accounts, or a specific tenant id.
    MICROSOFT_TENANT = os.getenv("MICROSOFT_TENANT", "common")

    # Apple: client secret is a signed JWT generated from the .p8 key below.
    APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")  # Services ID
    APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
    APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
    # Path to the .p8 private key file downloaded from Apple Developer.
    APPLE_PRIVATE_KEY_PATH = os.getenv("APPLE_PRIVATE_KEY_PATH", "")

    OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))
    DELETE_AFTER_DAYS = int(os.getenv("DELETE_AFTER_DAYS", "2"))
    TEST_AUTH = os.getenv("TEST_AUTH", "false").lower() == "true"


settings = Settings()
