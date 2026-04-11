-- Upwork Opportunity Scanner — Supabase schema
-- Paste this into: Supabase Dashboard → SQL Editor → New query → Run

CREATE TABLE IF NOT EXISTS search_themes (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    query_text TEXT,
    include_keywords_json TEXT DEFAULT '[]',
    exclude_keywords_json TEXT DEFAULT '[]',
    desired_skills_json TEXT DEFAULT '[]',
    min_budget REAL DEFAULT 0,
    contract_type TEXT DEFAULT 'any',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT NOW()::TEXT,
    updated_at TEXT DEFAULT NOW()::TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    external_url TEXT UNIQUE,
    source_method TEXT DEFAULT 'browser_manual',
    search_theme_id BIGINT REFERENCES search_themes(id),
    title TEXT,
    description_raw TEXT,
    description_clean TEXT,
    posted_at TEXT,
    budget_type TEXT,
    budget_min REAL,
    budget_max REAL,
    hourly_min REAL,
    hourly_max REAL,
    skills_json TEXT DEFAULT '[]',
    client_name_if_visible TEXT,
    client_country TEXT,
    client_payment_verified INTEGER DEFAULT 0,
    client_spend_text TEXT,
    client_hire_rate_text TEXT,
    proposal_activity_text TEXT,
    raw_snapshot_path TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    updated_at TEXT DEFAULT NOW()::TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id),
    relevance_score REAL DEFAULT 0,
    automation_score REAL DEFAULT 0,
    win_likelihood_score REAL DEFAULT 0,
    combined_score REAL DEFAULT 0,
    explanation_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT NOW()::TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id),
    diagnosis_text TEXT,
    positioning_text TEXT,
    opening_paragraph TEXT,
    upsell_text TEXT,
    caution_text TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    updated_at TEXT DEFAULT NOW()::TEXT
);

CREATE TABLE IF NOT EXISTS workflow_status (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id),
    status TEXT DEFAULT 'new',
    notes TEXT,
    applied_at TEXT,
    outcome TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    updated_at TEXT DEFAULT NOW()::TEXT
);
