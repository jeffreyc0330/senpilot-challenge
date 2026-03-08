import base64
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH, GMAIL_SCOPES

logger = logging.getLogger(__name__)


def get_gmail_service():
    """Authenticate and return a Gmail API service object."""
    creds = None

    if os.path.exists(GMAIL_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth2 flow — a browser window will open...")
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_PATH, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(GMAIL_TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Token saved to %s", GMAIL_TOKEN_PATH)

    service = build("gmail", "v1", credentials=creds)
    logger.info("Gmail service authenticated successfully.")
    return service


def get_unread_emails(service):
    """
    Fetch all unread emails from the inbox.

    Returns a list of message dicts with keys:
        id, thread_id, sender, sender_name, subject, body, raw_message
    """
    logger.info("Checking for unread emails...")
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=10,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        logger.info("No unread emails found.")
        return []

    logger.info("Found %d unread email(s).", len(messages))
    emails = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        sender_full = headers.get("From", "")
        subject = headers.get("Subject", "(no subject)")

        # Parse sender name and email address
        # e.g. "John Doe <john@example.com>" or just "john@example.com"
        sender_name = ""
        sender_email = sender_full
        if "<" in sender_full:
            parts = sender_full.split("<")
            sender_name = parts[0].strip().strip('"')
            sender_email = parts[1].rstrip(">").strip()

        body = _extract_body(msg["payload"])

        emails.append({
            "id": msg_id,
            "thread_id": msg["threadId"],
            "sender": sender_email,
            "sender_name": sender_name,
            "subject": subject,
            "body": body,
        })

    return emails


def _extract_body(payload) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    if "parts" in payload:
        for part in payload["parts"]:
            text = _extract_body(part)
            if text:
                return text

    return ""


def mark_as_read(service, msg_id: str):
    """Remove the UNREAD label from a message."""
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    logger.info("Marked message %s as read.", msg_id)


def send_reply(service, to: str, subject: str, body: str, zip_path: str = None):
    """
    Send a reply email, optionally attaching a ZIP file.

    Args:
        service: authenticated Gmail API service
        to: recipient email address
        subject: email subject (will prepend "Re: " if not already)
        body: plain text body of the reply
        zip_path: optional path to a ZIP file to attach
    """
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))

    if zip_path and os.path.exists(zip_path):
        filename = os.path.basename(zip_path)
        logger.info("Attaching ZIP: %s (%d bytes)", filename, os.path.getsize(zip_path))
        with open(zip_path, "rb") as f:
            part = MIMEBase("application", "zip")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()
    logger.info("Reply sent to %s with subject '%s'.", to, subject)
