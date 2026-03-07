"""
main.py — entry point for the Senpilot regulatory document agent.

Polls a Gmail inbox every POLL_INTERVAL seconds, parses incoming requests,
scrapes the UARB Nova Scotia portal, compresses downloaded documents into a ZIP,
and replies to the sender with the ZIP attached.
"""

import asyncio
import time
from datetime import datetime

from config import AGENT_EMAIL, POLL_INTERVAL
from email_handler import get_gmail_service, get_unread_emails, mark_as_read, send_reply
from parser import parse_request
from scraper import fetch_documents
from zipper import compress_files, make_zip_path


def _format_date(date_str: str) -> str:
    """Convert MM/DD/YYYY to 'Month D, YYYY' (e.g. '04/07/2025' -> 'April 7, 2025')."""
    if not date_str:
        return "unknown"
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return dt.strftime("%B %-d, %Y")
    except ValueError:
        return date_str


def _format_count(n: int, label: str) -> str:
    """Return e.g. '13 Exhibits' or 'no Transcripts'."""
    if n == 0:
        return f"no {label}"
    return f"{n} {label}"


def _build_reply(sender_name: str, matter_number: str, doc_type: str,
                 metadata: dict, counts: dict, n_downloaded: int) -> str:
    """
    Compose the reply body from metadata and download results.

    Template:
        Hi [sender first name],
        [matter_number] is about [title]. It relates to [category] within the [type]
        category. The matter had an initial filing on [date_received] and a final filing
        on [date_final_submissions]. I found [N] Exhibits, [N] Key Documents,
        [N] Other Documents, [N] Transcripts, and [N] Recordings.
        I downloaded [n] out of the [total] [doc_type] and am attaching them as a ZIP here.
    """
    first_name = (sender_name.split()[0] if sender_name else "there")

    title = metadata.get("title") or "unknown"
    category = metadata.get("category") or "unknown"
    mat_type = metadata.get("type") or "unknown"
    date_received = _format_date(metadata.get("date_received", ""))
    date_final = _format_date(metadata.get("date_final_submissions", ""))

    # Build counts sentence
    exhibits = counts.get("Exhibits", 0)
    key_docs = counts.get("Key Documents", 0)
    other_docs = counts.get("Other Documents", 0)
    transcripts = counts.get("Transcripts", 0)
    recordings = counts.get("Recordings", 0)

    total_for_type = counts.get(doc_type, 0)

    # Condense zero-count doc types at the end: "no Transcripts or Recordings"
    non_zero = []
    zero_labels = []
    for label, count in [
        ("Exhibits", exhibits),
        ("Key Documents", key_docs),
        ("Other Documents", other_docs),
        ("Transcripts", transcripts),
        ("Recordings", recordings),
    ]:
        if count > 0:
            non_zero.append(f"{count} {label}")
        else:
            zero_labels.append(label)

    counts_parts = non_zero[:]
    if zero_labels:
        counts_parts.append("no " + " or ".join(zero_labels))

    if counts_parts:
        counts_sentence = "I found " + ", ".join(counts_parts) + "."
    else:
        counts_sentence = "I found no documents in any category."

    body = (
        f"Hi {first_name},\n\n"
        f"{matter_number} is about the {title}. "
        f"It relates to {category} within the {mat_type} category. "
        f"The matter had an initial filing on {date_received} and a final filing on {date_final}. "
        f"{counts_sentence} "
        f"I downloaded {n_downloaded} out of the {total_for_type} {doc_type} and am attaching them as a ZIP here."
    )
    return body


async def process_email(service, email: dict) -> None:
    """Process a single email: parse -> scrape -> zip -> reply."""
    sender = email["sender"]
    sender_name = email["sender_name"]
    subject = email["subject"]
    body = email["body"]
    msg_id = email["id"]

    print(f"\n[main] Processing email from {sender} | Subject: {subject}")
    print(f"[main] Body preview: {body[:200]!r}")

    # Step 1: Parse the request
    try:
        request = parse_request(body)
    except ValueError as e:
        print(f"[main] Parse error: {e}")
        send_reply(service, sender, subject, str(e))
        mark_as_read(service, msg_id)
        return

    matter_number = request["matter_number"]
    doc_type = request["doc_type"]

    # Step 2: Scrape UARB portal
    try:
        result = await fetch_documents(matter_number, doc_type)
    except Exception as e:
        error_msg = f"Sorry, I encountered an error while scraping the UARB portal: {e}"
        print(f"[main] Scraper error: {e}")
        send_reply(service, sender, subject, error_msg)
        mark_as_read(service, msg_id)
        return

    metadata = result["metadata"]
    counts = result["counts"]
    file_paths = result["file_paths"]

    if not file_paths:
        msg = (
            f"Hi {sender_name.split()[0] if sender_name else 'there'},\n\n"
            f"I found the matter {matter_number} but could not download any {doc_type}. "
            "They may not be available or the count may be zero."
        )
        send_reply(service, sender, subject, msg)
        mark_as_read(service, msg_id)
        return

    # Step 3: Compress to ZIP
    try:
        zip_path = make_zip_path(matter_number)
        compress_files(file_paths, zip_path)
    except Exception as e:
        error_msg = f"Sorry, I encountered an error while creating the ZIP archive: {e}"
        print(f"[main] ZIP error: {e}")
        send_reply(service, sender, subject, error_msg)
        mark_as_read(service, msg_id)
        return

    # Step 4: Compose and send reply
    reply_body = _build_reply(
        sender_name=sender_name,
        matter_number=matter_number,
        doc_type=doc_type,
        metadata=metadata,
        counts=counts,
        n_downloaded=len(file_paths),
    )
    print(f"[main] Reply body:\n{reply_body}")

    try:
        send_reply(service, sender, subject, reply_body, zip_path=zip_path)
    except Exception as e:
        print(f"[main] Error sending reply: {e}")

    # Step 5: Mark as read
    mark_as_read(service, msg_id)
    print(f"[main] Done processing email from {sender}.")


async def poll_loop():
    """Main polling loop — runs forever, checking inbox every POLL_INTERVAL seconds."""
    print(f"[main] Agent running, monitoring {AGENT_EMAIL}...")
    print(f"[main] Poll interval: {POLL_INTERVAL}s")

    service = get_gmail_service()

    while True:
        try:
            emails = get_unread_emails(service)
            for email in emails:
                try:
                    await process_email(service, email)
                except Exception as e:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{ts}] [main] Unhandled error processing email {email['id']}: {e}")
                    # Attempt to send an error reply
                    try:
                        send_reply(
                            service,
                            email["sender"],
                            email["subject"],
                            f"Sorry, I encountered an error processing your request: {e}",
                        )
                        mark_as_read(service, email["id"])
                    except Exception as reply_err:
                        print(f"[main] Could not send error reply: {reply_err}")

        except Exception as poll_err:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] [main] Error during poll: {poll_err}")

        print(f"[main] Sleeping {POLL_INTERVAL}s before next poll...")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(poll_loop())
