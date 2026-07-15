"""Environment-based configuration for the Drive -> Notion backup agent."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    google_shared_drive_id: str
    google_service_account_json_path: str
    notion_api_key: str
    notion_database_id: str
    notion_version: str
    retention_days: int
    sqlite_path: str
    log_file: str
    export_mime_type: str
    max_file_size_bytes: int


def _resolve_service_account_path(raw_value: str) -> str:
    """GOOGLE_SERVICE_ACCOUNT_JSON may be a filesystem path, or the raw JSON
    content of the key itself (some hosts only let you inject secrets as
    env vars, not files)."""
    stripped = raw_value.strip()
    if stripped.startswith("{"):
        json.loads(stripped)  # fail fast on malformed secrets
        fd, path = tempfile.mkstemp(prefix="gcp-sa-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(stripped)
        os.chmod(path, 0o600)
        return path

    path = Path(stripped).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"GOOGLE_SERVICE_ACCOUNT_JSON does not point to an existing file: {path}"
        )
    return str(path)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    return Settings(
        google_shared_drive_id=_require("GOOGLE_SHARED_DRIVE_ID"),
        google_service_account_json_path=_resolve_service_account_path(
            _require("GOOGLE_SERVICE_ACCOUNT_JSON")
        ),
        notion_api_key=_require("NOTION_API_KEY"),
        notion_database_id=_require("NOTION_DATABASE_ID"),
        notion_version=os.environ.get("NOTION_VERSION", "2025-09-03").strip(),
        retention_days=int(os.environ.get("RETENTION_DAYS", "30")),
        sqlite_path=os.environ.get("SQLITE_PATH", str(_BASE_DIR / "backup_state.sqlite3")),
        log_file=os.environ.get("LOG_FILE", str(_BASE_DIR / "backup.log")),
        export_mime_type=os.environ.get("GOOGLE_EXPORT_MIME_TYPE", "application/pdf"),
        max_file_size_bytes=int(
            os.environ.get("MAX_FILE_SIZE_BYTES", str(200 * 1024 * 1024))
        ),
    )
