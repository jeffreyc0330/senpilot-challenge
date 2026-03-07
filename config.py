import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")
AGENT_EMAIL = os.getenv("AGENT_EMAIL", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/senpilot")
MAX_DOCS = int(os.getenv("MAX_DOCS", "10"))

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

UARB_URL = "https://uarb.novascotia.ca/fmi/webd/UARB15"

VALID_DOC_TYPES = ["Exhibits", "Key Documents", "Other Documents", "Transcripts", "Recordings"]
