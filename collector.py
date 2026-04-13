"""
collector.py — Upwork job collector using Playwright + your existing Chrome session.

Usage:
    python collector.py                  # run all active search themes
    python collector.py --theme 3        # run a single theme by ID
    python collector.py --pages 3        # collect up to N pages per theme (default: 2)
    python collector.py --dry-run        # parse + print, don't save to DB

Setup (one-time):
    pip install playwright
    playwright install chromium

How it works:
    1. Launches a Chromium browser using your existing Chrome user profile
       so Upwork sees you as already logged in.
    2. For each active search theme, constructs an Upwork search URL from
       the theme's query_text and filters.
    3. Scrolls and extracts job cards from search results.
    4. Normalises each card through the ingestion pipeline.
    5. Scores each job and generates a proposal draft.
    6. Saves new jobs to the database (duplicates are silently ignored).

Requirements:
    - You must be logged into Upwork in your default Chrome browser.
    - Run this script locally — it is NOT meant to run on Streamlit Cloud.
    - Chrome must be closed (or use a separate profile) before running,
      as Playwright needs exclusive access to the profile.
"""

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlencode

from playwright.async_api import async_playwright

import db
import ingestion
import scorer
import hypothesis
import proposal as proposal_mod


# ── Constants ─────────────────────────────────────────────────────────────────

# Chrome profile path — set CHROME_PROFILE_PATH in your .env or environment.
# Windows example: C:\Users\YourName\AppData\Local\Google\Chrome\User Data
# macOS example:   /Users/yourname/Library/Application Support/Google/Chrome
# Linux example:   /home/yourname/.config/google-chrome
_DEFAULT_PROFILE = os.path.join(os.path.expanduser("~"), ".config", "google-chrome")
CHROME_PROFILE = os.getenv("CHROME_PROFILE_PATH", _DEFAULT_PROFILE)

UPWORK_SEARCH_BASE = "https://www.upwork.com/nx/search/jobs/"
SCROLL_PAUSE = 1.5        # seconds between scrolls
PAGE_LOAD_TIMEOUT = 15000 # ms


# ── URL builder ───────────────────────────────────────────────────────────────

def build_search_url(theme, page=1):
    query = theme.get("query_text") or theme.get("name") or ""
    params = {
        "q": query,
        "sort": "recency",
        "page": page,
    }
    contract_type = theme.get("contract_type", "any")
    if contract_type == "fixed":
        params["job_type"] = "fixed"
    elif contract_type == "hourly":
        params["job_type"] = "hourly"

    min_budget = theme.get("min_budget") or 0
    if min_budget and contract_type in ("fixed", "any"):
        params["budget_min"] = int(min_budget)

    return UPWORK_SEARCH_BASE + "?" + urlencode(params)


# ── Job card extractor ────────────────────────────────────────────────────────

async def extract_job_cards(page):
    """
    Extract raw text and URL from each job card on the current search results page.
    Upwork uses React so we target aria roles and data attributes rather than
    brittle class names.
    """
    await page.wait_for_timeout(2000)

    # Scroll to load lazy content
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

    jobs = await page.evaluate("""
        () => {
            const results = [];

            // Try common Upwork job card selectors (may change with platform updates)
            const selectors = [
                'article[data-test="JobTile"]',
                'article[data-ev-label="search_results_impression"]',
                'div[data-test="job-tile"]',
                'article',
            ];

            let cards = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 2) { cards = Array.from(found); break; }
            }

            for (const card of cards.slice(0, 30)) {
                // Try to find the job URL
                const link = card.querySelector('a[href*="/jobs/"]') ||
                             card.querySelector('a[href*="freelance-jobs"]');
                const url = link ? (link.href.startsWith('http')
                    ? link.href
                    : 'https://www.upwork.com' + link.getAttribute('href'))
                    : null;

                const text = card.innerText || card.textContent || '';
                if (text.trim().length > 40) {
                    results.push({ url, text: text.trim() });
                }
            }

            // Fallback: grab all /jobs/ links with surrounding text
            if (results.length === 0) {
                const links = document.querySelectorAll('a[href*="/jobs/~"]');
                for (const link of Array.from(links).slice(0, 20)) {
                    const parent = link.closest('li') || link.closest('div') || link.parentElement;
                    const text = parent ? parent.innerText : link.innerText;
                    if (text && text.trim().length > 20) {
                        results.push({
                            url: link.href.startsWith('http')
                                ? link.href
                                : 'https://www.upwork.com' + link.getAttribute('href'),
                            text: text.trim()
                        });
                    }
                }
            }

            return results;
        }
    """)

    return jobs


# ── Per-job processing ────────────────────────────────────────────────────────

def process_raw_job(raw, theme, dry_run=False):
    """Parse, score, and save one raw {url, text} dict. Returns True if saved."""
    url = raw.get("url")
    text = raw.get("text", "")

    job_dict = ingestion.parse_text_block(text, source_url=url, source_method="browser_agent")
    if not job_dict:
        return False

    job_dict["search_theme_id"] = theme["id"]

    if dry_run:
        print(f"  [dry-run] {job_dict.get('title', '?')[:70]}  |  budget={job_dict.get('budget_min')}  |  url={url}")
        return True

    job_id = db.insert_job(job_dict)
    if not job_id:
        return False  # duplicate, already in DB

    job_full = db.get_job(job_id)
    scores = scorer.compute_scores(job_full, theme)
    db.upsert_score(job_id, scores)

    hyp = hypothesis.generate_hypothesis(job_full, scores)
    offer = hypothesis.generate_offer_angle(job_full, scores)
    prop = proposal_mod.generate_proposal(job_full, scores, hyp)
    prop["diagnosis_text"] = hyp + "\n\n" + offer
    db.upsert_proposal(job_id, prop)
    db.set_status(job_id, "new")
    return True


# ── Theme collector ───────────────────────────────────────────────────────────

async def collect_theme(browser, theme, max_pages=2, dry_run=False):
    print(f"\n── Theme: {theme['name']} ──")
    total_new = 0

    context = await browser.new_context()
    page = await context.new_page()

    try:
        for page_num in range(1, max_pages + 1):
            url = build_search_url(theme, page=page_num)
            print(f"  Fetching page {page_num}: {url}")

            try:
                await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            except Exception as e:
                print(f"  Navigation error: {e}")
                break

            # Check for login wall
            current_url = page.url
            if "login" in current_url or "signup" in current_url:
                print("  ⚠ Redirected to login page — Upwork session not active in this profile.")
                print("  Make sure you are logged into Upwork in Chrome and Chrome is fully closed.")
                break

            raw_jobs = await extract_job_cards(page)
            print(f"  Found {len(raw_jobs)} card(s) on page {page_num}")

            if not raw_jobs:
                print("  No job cards found — stopping pagination for this theme.")
                break

            saved = 0
            for raw in raw_jobs:
                if process_raw_job(raw, theme, dry_run=dry_run):
                    saved += 1

            print(f"  Saved {saved} new job(s)")
            total_new += saved

            # If we got fewer than 5 cards, no point going to next page
            if len(raw_jobs) < 5:
                break

    finally:
        await context.close()

    return total_new


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(theme_id=None, max_pages=2, dry_run=False):
    if not dry_run:
        db.init_db()

    themes = db.get_themes(active_only=True)
    if theme_id:
        themes = [t for t in themes if t["id"] == theme_id]
        if not themes:
            print(f"No active theme with ID {theme_id}")
            return

    if not themes:
        print("No active search themes found. Add themes in the Streamlit dashboard.")
        return

    print(f"Collecting jobs for {len(themes)} theme(s), up to {max_pages} page(s) each.")
    print(f"Using Chrome profile: {CHROME_PROFILE}")
    if dry_run:
        print("DRY RUN — jobs will be parsed and printed but not saved.\n")

    total = 0
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir=CHROME_PROFILE,
                headless=False,        # visible so you can see what's happening
                slow_mo=300,           # slight delay to avoid bot detection
                channel="chrome",      # use installed Chrome, not Chromium
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            print(f"Failed to launch Chrome: {e}")
            print("Tip: make sure Chrome is fully closed before running this script.")
            return

        for theme in themes:
            n = await collect_theme(browser, theme, max_pages=max_pages, dry_run=dry_run)
            total += n

        await browser.close()

    print(f"\n✓ Done. {total} new job(s) added across all themes.")


def main():
    parser = argparse.ArgumentParser(description="Collect Upwork jobs for all active search themes.")
    parser.add_argument("--theme", type=int, default=None, help="Only collect for this theme ID")
    parser.add_argument("--pages", type=int, default=2, help="Pages to fetch per theme (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print jobs without saving")
    args = parser.parse_args()

    asyncio.run(run(theme_id=args.theme, max_pages=args.pages, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
