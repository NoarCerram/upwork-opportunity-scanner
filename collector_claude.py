"""
collector_claude.py — Upwork job collector using requests + Claude API.

No browser required. Fetches Upwork search result pages with plain HTTP requests,
then uses Claude (claude-haiku-4-5) to intelligently extract structured job data.

Usage:
    python collector_claude.py                  # run all active search themes
    python collector_claude.py --theme 3        # run a single theme by ID
    python collector_claude.py --pages 3        # collect N pages per theme (default: 2)
    python collector_claude.py --dry-run        # parse + print, don't save to DB

Setup (one-time):
    pip install anthropic
    Set ANTHROPIC_API_KEY in your .env

Optional — authenticated results (recommended):
    Set UPWORK_COOKIES in your .env to pass your logged-in Upwork session.

    How to get your cookies (takes ~60 seconds):
      1. Open Chrome and log into upwork.com
      2. Press F12 → Application tab → Cookies → https://www.upwork.com
      3. Copy the values of these cookies (comma-separated name=value pairs):
            oauth2_global_js_token, visitor_id, master_access_token
      4. Add to .env:
            UPWORK_COOKIES=oauth2_global_js_token=xxx; visitor_id=yyy; master_access_token=zzz

    Without cookies, Upwork may show fewer results or require CAPTCHA on some pages.
    The collector will still work on public search results without cookies.
"""

import argparse
import json
import os
import time
from urllib.parse import urlencode

import anthropic
import requests
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

import db
import ingestion
import scorer
import hypothesis
import proposal as proposal_mod

# ── Constants ─────────────────────────────────────────────────────────────────

UPWORK_SEARCH_BASE = "https://www.upwork.com/nx/search/jobs/"
REQUEST_DELAY = 2.0        # seconds between page fetches (be polite)
MAX_TEXT_CHARS = 12000     # max chars sent to Claude per page

# Claude model to use for extraction (haiku = fast + cheap for high-volume parsing)
CLAUDE_MODEL = "claude-haiku-4-5"

# System prompt — cached on first call (stable across all requests)
EXTRACTION_SYSTEM_PROMPT = """You are a precise job listing data extractor for Upwork search results.

Given raw text scraped from an Upwork search results page, identify and extract every job listing present.

For each job listing, extract:
- title: The job title / heading line
- url: The Upwork job URL if present (pattern: /jobs/~... or full https://www.upwork.com/jobs/...)
- budget: Budget as shown on the page (e.g. "$500", "$25-50/hr", "$200–$400 Fixed")
- posted: When the job was posted (e.g. "2 hours ago", "3 days ago", "Posted 5 minutes ago")
- description: The job description snippet visible on the card (first 300 chars max)
- skills: Array of skill tags / required skills listed
- payment_verified: true if "Payment verified" appears near this job, false otherwise
- client_spend: Client total spend if shown (e.g. "$10K+ spent", "$1K spent")
- proposals: Proposal / bid count if shown (e.g. "5 proposals", "10-15 bids", "Less than 5")

Rules:
- Return ONLY a valid JSON object — no markdown, no explanation, no preamble.
- Use null for any field you cannot determine from the text.
- If no jobs are found at all, return {"jobs": []}.
- Do not invent data. Only extract what is explicitly present in the text.

Required output format:
{"jobs": [{"title": "...", "url": "...", "budget": "...", "posted": "...", "description": "...", "skills": [...], "payment_verified": false, "client_spend": null, "proposals": null}, ...]}"""


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _build_session():
    """Build a requests.Session with Upwork-friendly headers + optional cookies."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.upwork.com/",
    })
    cookie_str = os.getenv("UPWORK_COOKIES", "")
    if cookie_str:
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                s.cookies.set(name.strip(), value.strip(), domain=".upwork.com")
        print("  Using Upwork session cookies from UPWORK_COOKIES env var.")
    else:
        print("  No UPWORK_COOKIES set — fetching public search results only.")
    return s


def build_search_url(theme, page=1):
    """Construct an Upwork search URL from a theme dict."""
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


def fetch_page_text(http_session, url):
    """Fetch a URL and return clean plain text (stripped HTML tags)."""
    try:
        resp = http_session.get(url, timeout=20)
        if resp.status_code == 200:
            if BS4_AVAILABLE:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove script/style noise
                for tag in soup(["script", "style", "noscript", "nav", "footer"]):
                    tag.decompose()
                return soup.get_text(" ", strip=True)
            return resp.text
        print(f"  HTTP {resp.status_code} for {url}")
        return None
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None


# ── Claude extraction ─────────────────────────────────────────────────────────

def extract_jobs_with_claude(client, page_text, theme_name):
    """
    Send page text to Claude and get back a list of structured job dicts.
    Uses prompt caching on the stable system prompt to reduce API costs.
    """
    # Trim to avoid hitting max_tokens
    trimmed = page_text[:MAX_TEXT_CHARS]

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": EXTRACTION_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},   # cache the stable system prompt
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Extract all job listings from this Upwork search page "
                    f"(search theme: {theme_name}):\n\n{trimmed}"
                ),
            }],
        )

        raw = next((b.text for b in response.content if b.type == "text"), "")
        # Strip any accidental markdown fences
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

        data = json.loads(raw)
        jobs = data.get("jobs", [])

        # Log cache stats (so you can see cost savings)
        usage = response.usage
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        if cached:
            print(f"  Claude: extracted {len(jobs)} job(s) "
                  f"[{usage.input_tokens} in / {usage.output_tokens} out / {cached} cached]")
        else:
            print(f"  Claude: extracted {len(jobs)} job(s) "
                  f"[{usage.input_tokens} in / {usage.output_tokens} out]")

        return jobs

    except json.JSONDecodeError as e:
        print(f"  Claude returned invalid JSON: {e}")
        return []
    except anthropic.RateLimitError:
        print("  Claude rate limited — waiting 30s before retry...")
        time.sleep(30)
        return []
    except Exception as e:
        print(f"  Claude extraction error: {e}")
        return []


# ── Job mapping ───────────────────────────────────────────────────────────────

def claude_job_to_dict(raw_job, theme_id):
    """
    Convert a Claude-extracted job dict into the format expected by
    ingestion.parse_text_block(), then run it through that parser to
    normalise budget, dates, skills, etc.
    """
    # Build a synthetic text block from Claude's structured output so we can
    # reuse the existing ingestion pipeline for field normalisation.
    lines = []
    if raw_job.get("title"):
        lines.append(raw_job["title"])
    if raw_job.get("budget"):
        lines.append(raw_job["budget"])
    if raw_job.get("posted"):
        lines.append(raw_job["posted"])
    if raw_job.get("description"):
        lines.append(raw_job["description"])
    if raw_job.get("skills"):
        lines.append(", ".join(raw_job["skills"]))
    if raw_job.get("payment_verified"):
        lines.append("Payment verified")
    if raw_job.get("client_spend"):
        lines.append(f"Total spent: {raw_job['client_spend']}")
    if raw_job.get("proposals"):
        lines.append(raw_job["proposals"])

    synthetic_text = "\n".join(lines)
    url = raw_job.get("url") or None
    if url and url.startswith("/"):
        url = "https://www.upwork.com" + url

    job_dict = ingestion.parse_text_block(
        synthetic_text, source_url=url, source_method="claude_api"
    )
    if job_dict:
        job_dict["search_theme_id"] = theme_id
    return job_dict


# ── Per-job processing ────────────────────────────────────────────────────────

def process_job(job_dict, theme, dry_run=False):
    """Score and save one job dict. Returns True if saved (not duplicate)."""
    if not job_dict:
        return False

    if dry_run:
        print(f"    [dry-run] {job_dict.get('title', '?')[:70]}  "
              f"budget={job_dict.get('budget_min')}  url={job_dict.get('external_url', '')[:60]}")
        return True

    job_id = db.insert_job(job_dict)
    if not job_id:
        return False   # duplicate

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

def collect_theme(claude_client, http_session, theme, max_pages=2, dry_run=False):
    """Collect jobs for one search theme across multiple pages."""
    print(f"\n── Theme: {theme['name']} ──")
    total_new = 0

    for page_num in range(1, max_pages + 1):
        url = build_search_url(theme, page=page_num)
        print(f"  Fetching page {page_num}: {url}")

        page_text = fetch_page_text(http_session, url)
        if not page_text:
            print("  Could not fetch page — stopping pagination for this theme.")
            break

        # Detect login wall
        if "Sign In" in page_text[:2000] and "join" in page_text[:2000].lower():
            print("  Possible login wall detected. Set UPWORK_COOKIES for authenticated results.")

        raw_jobs = extract_jobs_with_claude(claude_client, page_text, theme["name"])

        if not raw_jobs:
            print("  No jobs extracted — stopping pagination for this theme.")
            break

        saved = 0
        for raw_job in raw_jobs:
            job_dict = claude_job_to_dict(raw_job, theme["id"])
            if process_job(job_dict, theme, dry_run=dry_run):
                saved += 1

        print(f"  Saved {saved} new job(s)")
        total_new += saved

        if len(raw_jobs) < 5:
            break   # sparse page → no point fetching more

        if page_num < max_pages:
            time.sleep(REQUEST_DELAY)   # be polite between pages

    return total_new


# ── Main ──────────────────────────────────────────────────────────────────────

def run(theme_id=None, max_pages=2, dry_run=False):
    if not dry_run:
        db.init_db()
        db.seed_default_themes()

    themes = db.get_themes(active_only=True)
    if theme_id:
        themes = [t for t in themes if t["id"] == theme_id]
        if not themes:
            print(f"No active theme with ID {theme_id}")
            return

    if not themes:
        print("No active search themes found. Add themes via the Streamlit dashboard.")
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to your .env file.")
        return

    print(f"Collecting jobs for {len(themes)} theme(s), up to {max_pages} page(s) each.")
    print(f"Using Claude model: {CLAUDE_MODEL}")
    if dry_run:
        print("DRY RUN — jobs will be extracted and printed but not saved.\n")

    claude_client = anthropic.Anthropic(api_key=api_key)
    http_session = _build_session()

    total = 0
    for theme in themes:
        n = collect_theme(claude_client, http_session, theme, max_pages=max_pages, dry_run=dry_run)
        total += n

    print(f"\n✓ Done. {total} new job(s) added across all themes.")


def main():
    parser = argparse.ArgumentParser(
        description="Collect Upwork jobs using Claude API (no browser required)."
    )
    parser.add_argument("--theme", type=int, default=None, help="Only collect for this theme ID")
    parser.add_argument("--pages", type=int, default=2, help="Pages per theme (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Extract and print without saving")
    args = parser.parse_args()

    run(theme_id=args.theme, max_pages=args.pages, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
