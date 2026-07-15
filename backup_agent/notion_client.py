"""Notion API access: upload file content and manage database pages.

Uses the File Upload API (POST /v1/file_uploads, /send, /complete) followed
by attaching the resulting file_upload to a "files" property when creating
the page (POST /v1/pages). Size limits and the multi-part threshold are
documented at https://developers.notion.com/docs/working-with-files-and-media
- re-check them if Notion changes their limits, then adjust SINGLE_PART_LIMIT
/ PART_SIZE below.
"""

import logging
import math
import os
import time
from typing import Iterator, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.notion.com/v1"

# Files at or below this size can be uploaded in a single request; larger
# files must be split into parts (5-20 MiB each) and sent as mode=multi_part.
SINGLE_PART_LIMIT = 20 * 1024 * 1024
PART_SIZE = 10 * 1024 * 1024

MAX_RETRIES = 5


class NotionClient:
    def __init__(self, api_key: str, database_id: str, notion_version: str):
        self._database_id = database_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": notion_version,
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            response = self._session.request(method, url, timeout=60, **kwargs)
            if response.status_code == 429 and attempt < MAX_RETRIES:
                wait = float(response.headers.get("Retry-After", "1"))
                logger.warning("Notion API rate limited, retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                wait = 2**attempt
                logger.warning(
                    "Notion API server error %s, retrying in %ds", response.status_code, wait
                )
                time.sleep(wait)
                continue
            if not response.ok:
                raise RuntimeError(
                    f"Notion API {method} {path} failed: {response.status_code} {response.text}"
                )
            return response.json()
        raise RuntimeError(f"Notion API {method} {path} failed after {MAX_RETRIES} retries")

    def _send_part(
        self,
        upload_id: str,
        data: bytes,
        filename: str,
        mime_type: str,
        part_number: Optional[int] = None,
    ) -> None:
        files = {"file": (filename, data, mime_type or "application/octet-stream")}
        form_data = {"part_number": str(part_number)} if part_number is not None else {}
        url = f"{API_BASE}/file_uploads/{upload_id}/send"
        for attempt in range(1, MAX_RETRIES + 1):
            response = self._session.post(url, files=files, data=form_data, timeout=120)
            if response.status_code == 429 and attempt < MAX_RETRIES:
                wait = float(response.headers.get("Retry-After", "1"))
                logger.warning("Notion file upload rate limited, retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            if not response.ok:
                raise RuntimeError(
                    f"Notion file upload send failed: {response.status_code} {response.text}"
                )
            return
        raise RuntimeError(f"Notion file upload send failed after {MAX_RETRIES} retries")

    def upload_file(self, file_path: str, filename: str, mime_type: str) -> str:
        """Uploads a file from disk via the File Upload API, returns the
        file_upload id. Reads the file in bounded PART_SIZE chunks rather
        than loading it whole into memory, so a 500 MB file costs ~PART_SIZE
        of RAM, not 500 MB (+ another 500 MB for the split copies)."""
        size = os.path.getsize(file_path)
        if size <= SINGLE_PART_LIMIT:
            upload = self._request(
                "POST",
                "/file_uploads",
                json={"mode": "single_part", "filename": filename, "content_type": mime_type},
            )
            upload_id = upload["id"]
            with open(file_path, "rb") as f:
                self._send_part(upload_id, f.read(), filename, mime_type)
            return upload_id

        number_of_parts = math.ceil(size / PART_SIZE)
        upload = self._request(
            "POST",
            "/file_uploads",
            json={
                "mode": "multi_part",
                "number_of_parts": number_of_parts,
                "filename": filename,
                "content_type": mime_type,
            },
        )
        upload_id = upload["id"]
        with open(file_path, "rb") as f:
            part_number = 1
            while True:
                chunk = f.read(PART_SIZE)
                if not chunk:
                    break
                self._send_part(upload_id, chunk, filename, mime_type, part_number=part_number)
                part_number += 1
        self._request("POST", f"/file_uploads/{upload_id}/complete", json={})
        return upload_id

    def create_page(
        self,
        *,
        file_upload_id: str,
        file_name: str,
        source_file_id: str,
        drive_link: str,
        revision_id: str,
        original_modified_at: str,
        backed_up_at: str,
    ) -> str:
        payload = {
            "parent": {"database_id": self._database_id},
            "properties": {
                "Name": {"title": [{"text": {"content": file_name[:2000]}}]},
                "Source File ID": {"rich_text": [{"text": {"content": source_file_id}}]},
                "Drive Link": {"url": drive_link or None},
                "Version/Revision ID": {"rich_text": [{"text": {"content": revision_id}}]},
                "Backed Up At": {"date": {"start": backed_up_at}},
                "Original Modified At": {"date": {"start": original_modified_at}},
                "Attachment": {
                    "files": [
                        {
                            "type": "file_upload",
                            "file_upload": {"id": file_upload_id},
                            "name": file_name[:900],
                        }
                    ]
                },
            },
        }
        page = self._request("POST", "/pages", json=payload)
        return page["id"]

    def iter_pages_older_than(self, cutoff_iso: str) -> Iterator[dict]:
        """Yields pages whose 'Backed Up At' date is before cutoff_iso (retention scan)."""
        cursor = None
        while True:
            body = {
                "filter": {"property": "Backed Up At", "date": {"before": cutoff_iso}},
                "page_size": 100,
            }
            if cursor:
                body["start_cursor"] = cursor
            result = self._request("POST", f"/databases/{self._database_id}/query", json=body)
            for page in result.get("results", []):
                yield page
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")

    def archive_page(self, page_id: str) -> None:
        self._request("PATCH", f"/pages/{page_id}", json={"archived": True})
