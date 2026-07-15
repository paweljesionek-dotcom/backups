"""Google Drive access: list a shared drive's files and fetch their content.

Auth is a plain service account (no domain-wide delegation) that has been
added as a member of the target shared drive - see README.md.
"""

import io
import logging
from typing import Iterator, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

# Google-native document types that have no binary content of their own and
# must be exported to a downloadable format instead.
GOOGLE_NATIVE_EXPORTS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}

FIELDS = (
    "nextPageToken, files(id,name,mimeType,modifiedTime,headRevisionId,"
    "version,webViewLink,md5Checksum,size)"
)


class UnsupportedFileError(Exception):
    """Raised for Drive items that have no content we can back up (e.g. Google Forms)."""


class DriveClient:
    def __init__(self, service_account_path: str, shared_drive_id: str):
        credentials = service_account.Credentials.from_service_account_file(
            service_account_path, scopes=SCOPES
        )
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._drive_id = shared_drive_id

    def list_files(self) -> Iterator[dict]:
        """Yields every non-folder file on the shared drive, paginating as needed."""
        page_token = None
        while True:
            response = (
                self._service.files()
                .list(
                    corpora="drive",
                    driveId=self._drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    q="trashed = false",
                    fields=FIELDS,
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            for file in response.get("files", []):
                if file.get("mimeType") == FOLDER_MIME:
                    continue
                yield file
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    @staticmethod
    def revision_id_of(file: dict) -> str:
        """Best-available version marker: headRevisionId (binary files), then
        version (Google-native docs), then modifiedTime as a last resort."""
        return file.get("headRevisionId") or file.get("version") or file["modifiedTime"]

    def download_content(self, file: dict) -> Tuple[bytes, str, str]:
        """Returns (content_bytes, filename_with_extension, mime_type).

        Raises UnsupportedFileError for Drive items with no exportable content.
        """
        mime_type = file["mimeType"]
        file_id = file["id"]
        name = file["name"]

        if mime_type == SHORTCUT_MIME:
            raise UnsupportedFileError("shortcuts have no content of their own")

        if mime_type in GOOGLE_NATIVE_EXPORTS:
            export_mime, extension = GOOGLE_NATIVE_EXPORTS[mime_type]
            request = self._service.files().export_media(fileId=file_id, mimeType=export_mime)
            filename = f"{name}{extension}"
            out_mime = export_mime
        elif mime_type.startswith("application/vnd.google-apps."):
            raise UnsupportedFileError(f"no export available for {mime_type}")
        else:
            request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
            filename = name
            out_mime = mime_type

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue(), filename, out_mime

    @staticmethod
    def size_of(file: dict) -> Optional[int]:
        size = file.get("size")
        return int(size) if size is not None else None
