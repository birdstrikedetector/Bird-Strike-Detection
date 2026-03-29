from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import os
import mimetypes

SCOPES = ['https://www.googleapis.com/auth/drive.file']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
CREDS_PATH = os.path.join(BASE_DIR, "credentials.json")


def get_drive_service():
    """Authenticate and return a Google Drive service object."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If no (valid) credentials, go through OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # invalid_grant fix
                creds = None
                if os.path.exists(TOKEN_PATH):
                    os.remove(TOKEN_PATH)

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(
                host="localhost",
                port=8080,
                open_browser=False
            )

        # Save token
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    service = build('drive', 'v3', credentials=creds)
    return service


def upload_to_drive(file_path, folder_id=None):
    """
    Upload a file to Google Drive.
    Returns the file ID.
    """
    service = get_drive_service()

    file_metadata = {
        'name': os.path.basename(file_path)
    }
    if folder_id:
        file_metadata['parents'] = [folder_id]

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    file_id = file.get('id')
    print(f"Uploaded to Drive. File ID: {file_id}")
    return file_id
