import os
from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    """
    Reads DATABASE_URL from environment or Streamlit secrets.
    On Streamlit Community Cloud, set this in App Settings → Secrets:
        DATABASE_URL = "postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
    Locally, set it in .env.
    """
    # Try Streamlit secrets first (available in Cloud deployments)
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL")
        if url:
            return url
    except Exception:
        pass
    return os.getenv("DATABASE_URL")


DATABASE_URL = get_database_url()

# Combined score weights (must sum to 1.0)
WEIGHTS = {
    "relevance": 0.40,
    "automation": 0.35,
    "win_likelihood": 0.25,
}

# Score display thresholds
SCORE_HIGH = 75
SCORE_MODERATE = 50

# ── Automation signal dictionaries ───────────────────────────────────────────

AUTOMATION_SIGNALS = {
    "repetitive_task": [
        "daily", "weekly", "monthly", "recurring", "ongoing", "regularly",
        "routine", "every day", "every week", "each week", "each month",
        "repeated", "repetitive", "on a regular basis", "on an ongoing basis",
        "data entry", "copy paste", "copy and paste", "manual entry",
        "update records", "maintain records", "keep updated",
        "enter data", "input data", "upload", "log entries",
    ],
    "structured_input": [
        "hubspot", "salesforce", "pipedrive", "zoho crm", "crm",
        "excel", "google sheets", "spreadsheet", "airtable", "notion",
        "asana", "monday.com", "trello", "jira", "clickup",
        "shopify", "woocommerce", "bigcommerce", "magento",
        "ats", "applicant tracking", "linkedin", "indeed",
        "database", "sql", "csv", "api",
        "mailchimp", "klaviyo", "activecampaign",
        "quickbooks", "xero", "freshbooks",
        "google drive", "dropbox", "sharepoint",
    ],
    "recurring_output": [
        "report", "reports", "reporting", "summary", "summaries",
        "lead list", "prospect list", "contact list",
        "weekly update", "daily update", "monthly report",
        "dashboard", "tracker", "tracking",
        "extract", "extraction", "scrape", "compile",
        "monitor", "monitoring", "alert", "digest",
        "invoice", "invoicing", "reconcile",
    ],
    "operations_role": [
        "virtual assistant", "va ", "executive assistant",
        "data entry", "data operator", "data analyst",
        "operations", "ops", "coordinator", "admin", "administrative",
        "researcher", "research assistant",
        "lead generation", "lead gen",
        "outreach", "sourcing",
        "customer support", "customer service",
        "email management", "inbox management",
        "scheduling", "calendar management",
        "catalog", "product data", "product listing",
        "ecommerce", "e-commerce",
        "order management", "fulfillment",
    ],
    "scale_volume": [
        "large volume", "high volume", "bulk",
        "hundreds", "thousands", "many records",
        "at scale", "scalable",
        "ongoing basis", "long term", "long-term",
        "part time", "part-time", "full time", "full-time",
        "hours per week", "hrs/week", "hrs per week",
    ],
}

AUTOMATION_PENALTIES = [
    "strategic advisory", "executive coaching", "therapy",
    "legal advice", "legal counsel", "medical advice",
    "creative direction", "art direction", "brand strategy",
    "high-level strategy", "investor relations",
    "business development", "c-suite", "ceo ", "cto ", "cfo ",
    "bespoke design", "custom artwork", "illustration",
    "relationship manager", "account executive",
]

# ── Win-likelihood thresholds ─────────────────────────────────────────────────

WIN_THRESHOLDS = {
    "fresh_hours_great": 6,
    "fresh_hours_good": 24,
    "fresh_hours_ok": 72,
    "good_budget_fixed_min": 150,
    "good_budget_hourly_min": 18,
}

# ── Default search themes seeded on first run ────────────────────────────────

DEFAULT_THEMES = [
    {
        "name": "CRM cleanup + lead generation",
        "query_text": "CRM cleanup lead generation",
        "include_keywords_json": '["crm", "lead", "cleanup", "database", "salesforce", "hubspot"]',
        "exclude_keywords_json": '["senior director", "vp ", "c-suite"]',
        "desired_skills_json": '["CRM", "Data Entry", "Lead Generation"]',
        "min_budget": 50,
        "contract_type": "any",
    },
    {
        "name": "VA + reporting + spreadsheet",
        "query_text": "virtual assistant reporting spreadsheet",
        "include_keywords_json": '["virtual assistant", "report", "spreadsheet", "excel", "google sheets"]',
        "exclude_keywords_json": '[]',
        "desired_skills_json": '["Virtual Assistance", "Microsoft Excel", "Google Sheets"]',
        "min_budget": 30,
        "contract_type": "any",
    },
    {
        "name": "Research + extraction + monitoring",
        "query_text": "research extraction data monitoring",
        "include_keywords_json": '["research", "extract", "monitor", "compile", "data"]',
        "exclude_keywords_json": '[]',
        "desired_skills_json": '["Research", "Data Entry", "Web Scraping"]',
        "min_budget": 50,
        "contract_type": "any",
    },
    {
        "name": "Recruiting coordination + sourcing",
        "query_text": "recruiting coordinator sourcing",
        "include_keywords_json": '["recruiting", "sourcing", "ats", "linkedin", "candidates", "coordinator"]',
        "exclude_keywords_json": '[]',
        "desired_skills_json": '["Recruiting", "Sourcing", "LinkedIn Recruiting"]',
        "min_budget": 50,
        "contract_type": "any",
    },
    {
        "name": "Ecommerce ops + catalog updates",
        "query_text": "ecommerce operations catalog product data",
        "include_keywords_json": '["ecommerce", "shopify", "product", "catalog", "listing", "inventory"]',
        "exclude_keywords_json": '[]',
        "desired_skills_json": '["Shopify", "Product Listings", "Data Entry"]',
        "min_budget": 50,
        "contract_type": "any",
    },
]
