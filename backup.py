#!/usr/bin/env python3
"""Google Drive (shared drive) -> Notion backup agent.

Single-shot script meant to run periodically via cron (e.g. hourly or
nightly - see README.md for tradeoffs):
  1. scan the shared drive for files that are new or have a new revision
  2. back up each such version as its own page in a Notion database
  3. archive Notion pages older than RETENTION_DAYS

State between runs lives only in a local SQLite file (backed_up_versions
table) - there is no long-running process. See README.md for setup.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from backup_agent.config import load_settings
from backup_agent.db import connect, forget_page, is_backed_up, record_backup
from backup_agent.drive_client import DriveClient, UnsupportedFileError
from backup_agent.logging_setup import configure_logging
from backup_agent.notion_client import NotionClient

logger = logging.getLogger("backup")


def run_backup(drive: DriveClient, notion: NotionClient, conn, max_file_size_bytes: int):
    backed_up = 0
    skipped = 0
    failed = 0

    for file in drive.list_files():
        file_id = file["id"]
        name = file.get("name", file_id)
        try:
            revision_id = DriveClient.revision_id_of(file)
            if is_backed_up(conn, file_id, revision_id):
                continue

            size = DriveClient.size_of(file)
            if size is not None and size > max_file_size_bytes:
                logger.warning(
                    "Skipping %s (%s): size %d bytes exceeds MAX_FILE_SIZE_BYTES=%d",
                    name, file_id, size, max_file_size_bytes,
                )
                skipped += 1
                continue

            logger.info("New version detected: %s (%s) rev=%s", name, file_id, revision_id)
            tmp_path, filename, mime_type = drive.download_content(file)
            try:
                file_upload_id = notion.upload_file(tmp_path, filename, mime_type)
            finally:
                os.remove(tmp_path)

            now = datetime.now(timezone.utc).isoformat()
            page_id = notion.create_page(
                file_upload_id=file_upload_id,
                file_name=name,
                source_file_id=file_id,
                drive_link=file.get("webViewLink", ""),
                revision_id=revision_id,
                original_modified_at=file.get("modifiedTime", now),
                backed_up_at=now,
            )
            record_backup(conn, file_id, revision_id, page_id, name, now)
            backed_up += 1
            logger.info("Backed up %s -> Notion page %s", name, page_id)
        except UnsupportedFileError as exc:
            logger.info("Skipping %s (%s): %s", name, file_id, exc)
            skipped += 1
        except Exception:
            failed += 1
            logger.exception("Failed to back up file %s (%s)", name, file_id)

    return backed_up, skipped, failed


def run_retention(notion: NotionClient, conn, retention_days: int):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    archived = 0
    failed = 0

    for page in notion.iter_pages_older_than(cutoff):
        page_id = page["id"]
        try:
            notion.archive_page(page_id)
            forget_page(conn, page_id)
            archived += 1
            logger.info("Archived (retention, older than %d days): page %s", retention_days, page_id)
        except Exception:
            failed += 1
            logger.exception("Failed to archive page %s", page_id)

    return archived, failed


def main() -> int:
    try:
        settings = load_settings()
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(settings.log_file)
    logger.info("=== Backup run started ===")

    conn = notion = drive = None
    try:
        conn = connect(settings.sqlite_path)
        drive = DriveClient(settings.google_service_account_json_path, settings.google_shared_drive_id)
        notion = NotionClient(settings.notion_api_key, settings.notion_database_id, settings.notion_version)

        backed_up, skipped, backup_failed = run_backup(
            drive, notion, conn, settings.max_file_size_bytes
        )
        archived, retention_failed = run_retention(notion, conn, settings.retention_days)

        logger.info(
            "=== Backup run finished: backed_up=%d skipped=%d backup_failed=%d "
            "archived=%d retention_failed=%d ===",
            backed_up, skipped, backup_failed, archived, retention_failed,
        )
        return 1 if (backup_failed or retention_failed) else 0
    except Exception:
        logger.exception("Backup run aborted due to an unexpected error")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
