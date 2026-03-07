"""
auth.py — Run this ONCE locally before deploying.

It opens a browser window to authorise the agent's Gmail account and
saves the resulting token.json so the container never needs to do
interactive auth.

Usage:
    python auth.py

Then copy credentials.json and token.json to your server / include them
when deploying (see deployment notes in README).
"""

from google_auth_oauthlib.flow import InstalledAppFlow
from config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH, GMAIL_SCOPES

print(f"Opening browser to authorise Gmail access...")
print(f"Credentials file: {GMAIL_CREDENTIALS_PATH}")

flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_PATH, GMAIL_SCOPES)
creds = flow.run_local_server(port=0)

with open(GMAIL_TOKEN_PATH, "w") as f:
    f.write(creds.to_json())

print(f"\nDone! Token saved to: {GMAIL_TOKEN_PATH}")
print("You can now build and deploy the Docker container.")
print("Make sure both credentials.json and token.json are present before building.")
