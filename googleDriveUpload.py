from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import os

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join("/home/a/Documents/Deployment/service_account.json")

# Put the folder ID here, or set DRIVE_FOLDER_ID in the environment
DEFAULT_FOLDER_ID = "18wAzRACHu5is24Ffog21nCS1BirP30-G"

def get_drive_service():
    """
    Authenticate with a service account and return a Google Drive service object.
    """
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(
            f"Service account key file not found: {SERVICE_ACCOUNT_FILE}"
        )

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    service = build("drive", "v3", credentials=creds)
    return service

def upload_to_drive(file_path):
    """
    Upload a file to Google Drive using a service account.
    The target folder must be shared with the service account email.
    Returns the uploaded file ID.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File does not exist: {file_path}")

    service = get_drive_service()

    folder_id = DEFAULT_FOLDER_ID

    file_metadata = {
        "name": os.path.basename(file_path),
        "parents": [folder_id],
    }

    media = MediaFileUpload(
        file_path,
        mimetype="video/x-msvideo",
        resumable=True,
    )

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, parents",
        supportsAllDrives=True,
    ).execute()

    file_id = file["id"]
    print(f"Uploaded to Drive. File ID: {file_id}")
    return file_id
