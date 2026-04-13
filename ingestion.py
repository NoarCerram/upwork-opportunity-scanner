import re
import json
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


UPWORK_URL_RE = re.compile(
    r"https?://(?:www\.)?upwork\.com/(?:jobs|freelance-jobs)/[^\s\"'<>]+"
)


# ── URL helpers ───────────────────────────────────────────────────────────────

def extract_urls(text):
    return UPWORK_URL_RE.findall(text)


def normalize_url(url):
    url = url.strip().rstrip("/")
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def parse_url_list(text):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    urls = []
    for line in lines:
        if "upwork.com/jobs" in line or "upwork.com/freelance-jobs" in line:
            urls.append(normalize_url(line))
        else:
            found = extract_urls(line)
            urls.extend(normalize_url(u) for u in found)
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


# ── Time helpers ──────────────────────────────────────────────────────────────

def _resolve_relative_time(text):
    """Convert '2 hours ago', '3 days ago' etc. to an ISO timestamp."""
    lower = text.lower()
    now = datetime.now(timezone.utc)
    patterns = [
        (r"(\d+)\s*minute", "minutes"),
        (r"(\d+)\s*hour",   "hours"),
        (r"(\d+)\s*day",    "days"),
        (r"(\d+)\s*week",   "weeks"),
        (r"(\d+)\s*month",  "months"),
    ]
    for pat, unit in patterns:
        m = re.search(pat, lower)
        if m:
            n = int(m.group(1))
            delta = {
                "minutes": timedelta(minutes=n),
                "hours":   timedelta(hours=n),
                "days":    timedelta(days=n),
                "weeks":   timedelta(weeks=n),
                "months":  timedelta(days=n * 30),
            }[unit]
            return (now - delta).isoformat()
    return None


# ── Field extractors ──────────────────────────────────────────────────────────

def _extract_budget(text):
    result = {
        "budget_type": None,
        "budget_min": None,
        "budget_max": None,
        "hourly_min": None,
        "hourly_max": None,
    }

    # Hourly range: $X – $Y /hr
    m = re.search(r"\$(\d+(?:\.\d+)?)\s*[-\u2013]\s*\$(\d+(?:\.\d+)?)\s*/hr", text, re.I)
    if m:
        result.update(budget_type="hourly", hourly_min=float(m.group(1)), hourly_max=float(m.group(2)))
        return result

    # Single hourly
    m = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:/hr|per hour|/hour)", text, re.I)
    if m:
        result.update(budget_type="hourly", hourly_min=float(m.group(1)))
        return result

    # Fixed range: $X – $Y
    m = re.search(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*[-\u2013]\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)", text)
    if m:
        result.update(
            budget_type="fixed",
            budget_min=float(m.group(1).replace(",", "")),
            budget_max=float(m.group(2).replace(",", "")),
        )
        return result

    # Fixed single: "Budget: $X" or "$X fixed"
    m = re.search(r"(?:budget|fixed)[:\s]+\$(\d{1,3}(?:,\d{3})*)", text, re.I)
    if m:
        result.update(budget_type="fixed", budget_min=float(m.group(1).replace(",", "")))
        return result

    # Fallback: lone dollar amount
    m = re.search(r"\$(\d{1,3}(?:,\d{3})*)", text)
    if m:
        result.update(budget_type="fixed", budget_min=float(m.group(1).replace(",", "")))
    return result


_SKILL_VOCAB = [
    # ── 3D & Product Visual (primary niche) ──────────────────────────────────
    "3D Rendering", "3D Modeling", "Product Visualization", "Product Mockup",
    "3D Product Mockup", "3D Product Render", "Lifestyle Render",
    "Blender", "Cinema 4D", "Keyshot", "Octane Render", "V-Ray",
    "Adobe Dimension", "Substance Painter", "Marvelous Designer",
    "Midjourney", "AI Rendering", "AI Image Generation", "Stable Diffusion",
    "Product Photography", "Product Photography Replacement",
    "360 Product Render", "Packaging Design", "3D Packaging Mockup",
    "Amazon Listing Optimization", "Amazon A+ Content", "A+ Content",
    "Shopify Product Images", "Ecommerce Product Images",
    "Listing Image Design", "Product Visual Design",
    "Infographic Design", "Product Infographic",
    # ── Design tools ─────────────────────────────────────────────────────────
    "Adobe Photoshop", "Adobe Illustrator", "Adobe After Effects",
    "Canva", "Figma", "Adobe Creative Suite",
    "PowerPoint", "Google Slides",
    # ── Ecommerce / platforms ─────────────────────────────────────────────────
    "Shopify", "Amazon FBA", "WooCommerce", "BigCommerce", "Magento",
    # ── General (kept for fallback parsing) ──────────────────────────────────
    "Python", "JavaScript", "WordPress",
    "Excel", "Google Sheets", "Airtable", "Notion",
    "SEO", "Content Writing", "Copywriting", "Social Media",
    "Email Marketing",
]


def _extract_skills(text):
    lower = text.lower()
    return [s for s in _SKILL_VOCAB if s.lower() in lower]


def _extract_posted_at(text):
    # Relative: "2 days ago", "Posted 3 hours ago"
    m = re.search(
        r"(?:posted\s+)?(\d+\s*(?:minute|hour|day|week|month)s?\s*ago)",
        text, re.I
    )
    if m:
        return _resolve_relative_time(m.group(1)) or m.group(1)

    # Absolute ISO-ish
    m = re.search(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?", text)
    if m:
        return m.group(0)
    return None


# ── Text block parser (main ingestion path) ───────────────────────────────────

def parse_text_block(text, source_url=None, source_method="browser_manual"):
    text = text.strip()
    if len(text) < 30:
        return None

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Title: first line that is reasonably short and descriptive
    title = "Untitled Job"
    for line in lines:
        if 8 < len(line) < 160 and not line.startswith("http"):
            title = line
            break

    budget_info = _extract_budget(text)
    skills = _extract_skills(text)
    posted_at = _extract_posted_at(text)

    payment_verified = bool(re.search(r"payment\s+verified", text, re.I))

    country_m = re.search(
        r"(?:from|country|location)[:\s]+([A-Z][a-zA-Z ]{2,30})(?:\n|,|\.)", text
    )
    client_country = country_m.group(1).strip() if country_m else None

    spend_m = re.search(r"(?:total\s+spent?|spent?)[:\s]+(\$[\d,]+[KkMm]?)", text, re.I)
    client_spend_text = spend_m.group(1) if spend_m else None

    hire_m = re.search(r"(\d+)%\s*hire\s*rate", text, re.I)
    client_hire_rate_text = f"{hire_m.group(1)}% hire rate" if hire_m else None

    prop_m = re.search(r"(\d+[-\u2013]?\d*)\s*(?:proposal|bid|applicant)s?", text, re.I)
    proposal_activity_text = prop_m.group(0) if prop_m else None

    # Resolve URL
    url = normalize_url(source_url) if source_url else None
    if not url:
        found = extract_urls(text)
        if found:
            url = normalize_url(found[0])
    if not url:
        fingerprint = hashlib.md5(f"{title}{text[:120]}".encode()).hexdigest()
        url = f"upwork://local/{fingerprint}"

    return {
        "external_url": url,
        "source_method": source_method,
        "title": title,
        "description_raw": text,
        "description_clean": text,
        "posted_at": posted_at,
        "skills_json": json.dumps(skills),
        "client_payment_verified": payment_verified,
        "client_country": client_country,
        "client_spend_text": client_spend_text,
        "client_hire_rate_text": client_hire_rate_text,
        "proposal_activity_text": proposal_activity_text,
        **budget_info,
    }


# ── HTML snapshot parser ──────────────────────────────────────────────────────

def parse_html_snapshot(html, source_method="browser_manual"):
    if not BS4_AVAILABLE:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Try structured job cards first
    job_cards = (
        soup.find_all("article")
        or soup.find_all("section", class_=re.compile(r"job|result", re.I))
        or soup.find_all("div", class_=re.compile(r"job-card|job-tile|job-result", re.I))
    )

    if job_cards:
        for card in job_cards[:50]:
            text = card.get_text(" ", strip=True)
            url_tag = card.find("a", href=re.compile(r"/jobs/"))
            url = None
            if url_tag:
                href = url_tag.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.upwork.com" + href
                url = normalize_url(href)
            job = parse_text_block(text, source_url=url, source_method=source_method)
            if job:
                jobs.append(job)
        return jobs

    # Fallback: harvest all /jobs/ links
    job_links = soup.find_all("a", href=re.compile(r"/jobs/"))
    for link in job_links[:30]:
        href = link.get("href", "")
        if not href.startswith("http"):
            href = "https://www.upwork.com" + href
        label = link.get_text(strip=True)
        if len(label) < 5:
            continue
        jobs.append({
            "external_url": normalize_url(href),
            "source_method": source_method,
            "title": label[:200],
            "description_raw": "",
            "description_clean": "",
            "skills_json": "[]",
        })
    return jobs


# ── URL fetcher ───────────────────────────────────────────────────────────────

def fetch_job_url(url, source_method="direct_source"):
    if not REQUESTS_AVAILABLE:
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True) if BS4_AVAILABLE else resp.text
        job = parse_text_block(text, source_url=url, source_method=source_method)
        return job
    except Exception:
        return None


# ── JSON import ───────────────────────────────────────────────────────────────

def parse_json_import(json_text, source_method="browser_agent"):
    try:
        data = json.loads(json_text)
        if isinstance(data, dict):
            data = [data]
    except Exception:
        return []

    jobs = []
    for item in data:
        url = item.get("url") or item.get("external_url") or item.get("link")
        if url:
            url = normalize_url(url)

        skills_raw = item.get("skills") or item.get("skills_json") or []
        if isinstance(skills_raw, list):
            skills_json = json.dumps(skills_raw)
        else:
            skills_json = skills_raw if isinstance(skills_raw, str) else "[]"

        job = {
            "external_url": url,
            "source_method": item.get("source_method", source_method),
            "title": item.get("title"),
            "description_raw": item.get("description") or item.get("description_raw"),
            "description_clean": item.get("description_clean") or item.get("description"),
            "posted_at": item.get("posted_at") or item.get("posted"),
            "budget_type": item.get("budget_type"),
            "budget_min": item.get("budget_min"),
            "budget_max": item.get("budget_max"),
            "hourly_min": item.get("hourly_min"),
            "hourly_max": item.get("hourly_max"),
            "skills_json": skills_json,
            "client_country": item.get("client_country"),
            "client_payment_verified": bool(item.get("client_payment_verified", False)),
            "client_spend_text": item.get("client_spend_text") or item.get("client_spend"),
            "client_hire_rate_text": item.get("client_hire_rate_text") or item.get("hire_rate"),
            "proposal_activity_text": item.get("proposal_activity_text") or item.get("proposals"),
        }

        # If no URL provided, generate a fingerprint
        if not job["external_url"] and job.get("title"):
            desc = job.get("description_raw") or ""
            fp = hashlib.md5(f"{job['title']}{desc[:120]}".encode()).hexdigest()
            job["external_url"] = f"upwork://local/{fp}"

        if job.get("title"):
            jobs.append(job)

    return jobs
