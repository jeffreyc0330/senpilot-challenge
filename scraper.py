"""
scraper.py — Playwright-based scraper for the UARB Nova Scotia FileMaker Web Direct portal.

Usage (standalone test):
    python scraper.py

This will run against M12205 / "Other Documents" and print results.
"""

import asyncio
import logging
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from config import UARB_URL, DOWNLOAD_DIR, MAX_DOCS

logger = logging.getLogger(__name__)


async def fetch_documents(matter_number: str, doc_type: str, max_docs: int = MAX_DOCS) -> dict:
    """
    Navigate the UARB portal, extract metadata, and download up to max_docs documents.

    Args:
        matter_number: e.g. "M12205"
        doc_type: one of "Exhibits", "Key Documents", "Other Documents",
                  "Transcripts", "Recordings"
        max_docs: maximum number of documents to download (default MAX_DOCS from config)

    Returns:
        dict with keys:
            metadata   - dict of matter header fields
            counts     - dict of doc_type -> count for each tab
            file_paths - list of absolute paths to downloaded files
    """
    download_dir = Path(DOWNLOAD_DIR) / matter_number
    download_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Download directory: %s", download_dir)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # ── Page 1: Landing page ──────────────────────────────────────────────
        logger.info("Navigating to %s ...", UARB_URL)
        await page.goto(UARB_URL, wait_until="networkidle", timeout=60_000)
        logger.info("Landing page loaded.")

        # Wait for the "Go Directly to Matter" input
        matter_input = page.locator('input[placeholder*="M01234"], input[placeholder*="eg M"]').first
        await matter_input.wait_for(state="visible", timeout=30_000)
        logger.info("Typing matter number: %s", matter_number)
        await matter_input.click()
        await matter_input.fill(matter_number)

        # Click the Search button next to the input
        search_btn = page.get_by_role("button", name=re.compile(r"search", re.IGNORECASE)).first
        await search_btn.click()
        logger.info("Clicked Search — waiting for matter detail page...")

        await page.wait_for_load_state("networkidle", timeout=60_000)
        logger.info("Matter detail page loaded.")

        # ── Page 2: Matter Detail — extract header metadata ───────────────────
        metadata = await _extract_metadata(page)
        logger.info("Metadata extracted: %s", metadata)

        # ── Parse tab counts ──────────────────────────────────────────────────
        counts = await _extract_tab_counts(page)
        logger.info("Tab counts: %s", counts)

        # ── Click the requested tab ───────────────────────────────────────────
        await _click_tab(page, doc_type)
        logger.info("Clicked tab: %s", doc_type)
        await page.wait_for_load_state("networkidle", timeout=30_000)

        # ── Download documents ────────────────────────────────────────────────
        file_paths = await _download_documents(page, context, download_dir, max_docs)
        logger.info("Downloaded %d file(s).", len(file_paths))

        await browser.close()

    return {
        "metadata": metadata,
        "counts": counts,
        "file_paths": [str(p) for p in file_paths],
    }


async def _extract_metadata(page) -> dict:
    """Extract header fields from the matter detail page."""
    metadata = {}

    # Helper: get text by label
    async def get_field(label_text: str) -> str:
        try:
            # Try to find a cell/div that follows a label containing the text
            locator = page.locator(f'text="{label_text}"').first
            # The value is typically in the adjacent sibling or next element
            parent = locator.locator("xpath=..").first
            full_text = await parent.inner_text(timeout=5_000)
            # Strip the label prefix
            value = full_text.replace(label_text, "").strip().lstrip(":").strip()
            return value
        except Exception:
            return ""

    # Matter No
    try:
        # Matter No is often a clickable link — grab its text
        matter_link = page.get_by_role("link", name=re.compile(r"M\d{5}")).first
        metadata["matter_no"] = (await matter_link.inner_text(timeout=5_000)).strip()
    except Exception:
        metadata["matter_no"] = ""

    # Title/Description — usually a prominent heading near the matter number
    try:
        # Look for a label "Title" or "Description" and take the adjacent value
        title_label = page.locator('text="Title"').first
        title_parent = title_label.locator("xpath=..").first
        full = await title_parent.inner_text(timeout=5_000)
        metadata["title"] = full.replace("Title", "").strip().lstrip(":").strip()
    except Exception:
        metadata["title"] = ""

    # If title is empty, try a broader approach — grab the page heading
    if not metadata["title"]:
        try:
            heading = page.locator("h1, h2, h3").first
            metadata["title"] = (await heading.inner_text(timeout=5_000)).strip()
        except Exception:
            pass

    for field, key in [
        ("Type", "type"),
        ("Category", "category"),
        ("Date Received", "date_received"),
        ("Date Final Submissions", "date_final_submissions"),
        ("Outcome", "outcome"),
        ("Status", "status"),
    ]:
        metadata[key] = await get_field(field)

    return metadata


async def _extract_tab_counts(page) -> dict:
    """
    Read all tab labels and parse the count suffix (e.g. "Exhibits - 13" -> {"Exhibits": 13}).
    """
    counts = {}
    tab_pattern = re.compile(r"^(.+?)\s*-\s*(\d+)$")

    try:
        # Tabs are typically rendered as buttons or list items
        tab_elements = await page.locator('[role="tab"], .tab, .tabitem, button').all()
        for el in tab_elements:
            try:
                text = (await el.inner_text(timeout=3_000)).strip()
                m = tab_pattern.match(text)
                if m:
                    tab_name = m.group(1).strip()
                    count = int(m.group(2))
                    counts[tab_name] = count
            except Exception:
                continue
    except Exception as e:
        logger.warning("Could not extract tab counts: %s", e)

    return counts


async def _click_tab(page, doc_type: str):
    """Click the tab matching doc_type (partial match on the tab label)."""
    # Try to find a tab button whose label starts with doc_type
    try:
        tab = page.locator(
            f'[role="tab"]:has-text("{doc_type}"), button:has-text("{doc_type}")'
        ).first
        await tab.click(timeout=10_000)
        return
    except Exception:
        pass

    # Fallback: look for any clickable element containing the doc_type text
    try:
        el = page.locator(f'text="{doc_type}"').first
        await el.click(timeout=10_000)
    except Exception as e:
        logger.warning("Could not click tab '%s': %s", doc_type, e)


async def _download_documents(page, context, download_dir: Path, max_docs: int) -> list:
    """
    Click each "GO GET IT" button and save the downloaded files.

    FileMaker re-renders the DOM after each download, so we re-query buttons
    before each click.
    """
    file_paths = []

    # First check how many "GO GET IT" buttons are present
    buttons = await page.locator('button:has-text("GO GET IT"), a:has-text("GO GET IT")').all()
    total_available = len(buttons)
    to_download = min(total_available, max_docs)
    logger.info("Found %d 'GO GET IT' button(s). Will download %d.", total_available, to_download)

    for i in range(to_download):
        logger.info("Downloading document %d of %d...", i + 1, to_download)
        try:
            # Re-query buttons each iteration because FileMaker re-renders the DOM
            current_buttons = await page.locator(
                'button:has-text("GO GET IT"), a:has-text("GO GET IT")'
            ).all()

            if i >= len(current_buttons):
                logger.warning("No button at index %d — stopping.", i)
                break

            btn = current_buttons[i]

            # Use expect_download context manager BEFORE clicking
            async with page.expect_download(timeout=30_000) as download_info:
                await btn.click()

            download = await download_info.value
            suggested_name = download.suggested_filename or f"document_{i + 1}.pdf"
            dest = download_dir / suggested_name

            await download.save_as(str(dest))
            file_paths.append(dest)
            logger.info("Saved: %s", dest)

        except PlaywrightTimeoutError:
            logger.warning("Download %d timed out — retrying once after 2s...", i + 1)
            await asyncio.sleep(2)
            try:
                current_buttons = await page.locator(
                    'button:has-text("GO GET IT"), a:has-text("GO GET IT")'
                ).all()
                if i < len(current_buttons):
                    async with page.expect_download(timeout=30_000) as download_info:
                        await current_buttons[i].click()
                    download = await download_info.value
                    suggested_name = download.suggested_filename or f"document_{i + 1}.pdf"
                    dest = download_dir / suggested_name
                    await download.save_as(str(dest))
                    file_paths.append(dest)
                    logger.info("Saved (retry): %s", dest)
                else:
                    logger.warning("No button at index %d after retry — skipping.", i)
            except Exception as retry_err:
                logger.error("Retry failed for document %d: %s", i + 1, retry_err)

        except Exception as e:
            logger.error("Error downloading document %d: %s", i + 1, e)

    return file_paths


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    async def main():
        matter = "M12205"
        dtype = "Other Documents"
        print(f"\n=== Standalone scraper test: {matter} / {dtype} ===\n")
        result = await fetch_documents(matter, dtype, max_docs=10)
        print("\n--- Result ---")
        print("Metadata:")
        print(json.dumps(result["metadata"], indent=2))
        print("\nCounts:")
        print(json.dumps(result["counts"], indent=2))
        print(f"\nFiles downloaded ({len(result['file_paths'])}):")
        for p in result["file_paths"]:
            print(f"  {p}")

    asyncio.run(main())
