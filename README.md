# Senpilot Challenge — AI Regulatory Document Agent

An AI agent that monitors a Gmail inbox for requests about UARB Nova Scotia regulatory
documents, scrapes the public portal, compresses the downloads, and replies with a ZIP
attachment and a human-readable summary.

---

## Architecture

```
senpilot-challenge/
├── main.py           # Entry point — async polling loop
├── email_handler.py  # Gmail read/send via Gmail API (OAuth2)
├── scraper.py        # Playwright browser automation for UARB portal
├── zipper.py         # ZIP compression with zipfile
├── parser.py         # Extract matter number + doc type from email text
├── config.py         # Constants and environment variable loading
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright's Chromium browser

```bash
playwright install chromium
```

### 3. Configure environment variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
GMAIL_CREDENTIALS_PATH=credentials.json   # path to your OAuth2 client secret JSON
GMAIL_TOKEN_PATH=token.json               # will be created automatically on first run
AGENT_EMAIL=your-agent@gmail.com          # Gmail address the agent monitors
POLL_INTERVAL=60                          # seconds between inbox checks
DOWNLOAD_DIR=/tmp/senpilot               # where downloads are stored
MAX_DOCS=10                               # max documents to download per request
```

### 4. Set up Gmail API credentials (OAuth2)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Gmail API** under *APIs & Services → Library*
4. Go to *APIs & Services → Credentials* → **Create Credentials → OAuth client ID**
5. Choose **Desktop app** as the application type
6. Download the JSON file and save it as `credentials.json` in the project root
   (or set `GMAIL_CREDENTIALS_PATH` to its actual path)
7. Go to *APIs & Services → OAuth consent screen* and add your Gmail address as a
   test user (required while the app is in "Testing" mode)

On the **first run**, a browser window will open asking you to authorise the agent.
After approving, a `token.json` file is created and reused for subsequent runs.

**Required OAuth scopes** (configured automatically in `config.py`):
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.modify`

---

## Running the agent

```bash
python main.py
```

The agent will print:

```
[main] Agent running, monitoring your-agent@gmail.com...
[main] Poll interval: 60s
[email] Gmail service authenticated successfully.
[email] Checking for unread emails...
```

---

## Testing

### Test the scraper independently

Run against matter M12205 (Other Documents) without needing Gmail credentials:

```bash
python scraper.py
```

### Test the parser

```python
from parser import parse_request
result = parse_request("Hi Agent, Can you give me Other Documents files from M12205? Thanks!")
# {'matter_number': 'M12205', 'doc_type': 'Other Documents'}
```

### Send a test email

Send an email to your agent address formatted like:

```
Subject: Document request

Hi Agent, Can you give me Other Documents files from M12205? Thanks!
```

Supported doc type keywords:
| Email mention            | Canonical type    |
|--------------------------|-------------------|
| exhibits                 | Exhibits          |
| key documents / key docs | Key Documents     |
| other documents / other docs | Other Documents |
| transcripts              | Transcripts       |
| recordings               | Recordings        |

Matter numbers must match the pattern `M` followed by exactly 5 digits (e.g. `M12205`).

---

## Reply format

The agent replies with:

> Hi [first name],
>
> M12205 is about the Halifax Regional Water Commission — Windsor Street Exchange
> Redevelopment Project. It relates to Capital Expenditure within the Water category.
> The matter had an initial filing on April 7, 2025 and a final filing on
> October 23, 2025. I found 13 Exhibits, 5 Key Documents, 21 Other Documents, and
> no Transcripts or Recordings. I downloaded 10 out of the 21 Other Documents and
> am attaching them as a ZIP here.

The ZIP file is attached to the reply.

---

## Notes

- Downloads are saved to `DOWNLOAD_DIR/{matter_number}/` (default `/tmp/senpilot/M12205/`)
- ZIP archives are saved to `DOWNLOAD_DIR/zips/{matter_number}.zip`
- The scraper uses a **headless Chromium** browser via Playwright
- Set `headless=False` in `scraper.py` during development to watch the browser
- All credentials are loaded from environment variables — nothing is hardcoded
