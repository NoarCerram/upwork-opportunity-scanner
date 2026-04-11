import json
from datetime import datetime
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config import DATABASE_URL


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    # autocommit=True is required when using Supabase's PgBouncer pooler
    # (transaction mode). It also works fine with direct connections.
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def _rows_as_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _row_as_dict(cursor):
    cols = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    return dict(zip(cols, row)) if row else None


# ── Schema / migrations ───────────────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
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
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id BIGSERIAL PRIMARY KEY,
                external_url TEXT UNIQUE,
                source_method TEXT DEFAULT 'browser_manual',
                search_theme_id BIGINT,
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
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id BIGSERIAL PRIMARY KEY,
                job_id BIGINT NOT NULL UNIQUE,
                relevance_score REAL DEFAULT 0,
                automation_score REAL DEFAULT 0,
                win_likelihood_score REAL DEFAULT 0,
                combined_score REAL DEFAULT 0,
                explanation_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT NOW()::TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id BIGSERIAL PRIMARY KEY,
                job_id BIGINT NOT NULL UNIQUE,
                diagnosis_text TEXT,
                positioning_text TEXT,
                opening_paragraph TEXT,
                upsell_text TEXT,
                caution_text TEXT,
                created_at TEXT DEFAULT NOW()::TEXT,
                updated_at TEXT DEFAULT NOW()::TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS workflow_status (
                id BIGSERIAL PRIMARY KEY,
                job_id BIGINT NOT NULL UNIQUE,
                status TEXT DEFAULT 'new',
                notes TEXT,
                applied_at TEXT,
                outcome TEXT,
                created_at TEXT DEFAULT NOW()::TEXT,
                updated_at TEXT DEFAULT NOW()::TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)


# ── Search Themes ─────────────────────────────────────────────────────────────

def upsert_theme(theme):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        if theme.get("id"):
            c.execute("""
                UPDATE search_themes SET
                    name=%s, query_text=%s, include_keywords_json=%s,
                    exclude_keywords_json=%s, desired_skills_json=%s,
                    min_budget=%s, contract_type=%s, active=%s, updated_at=%s
                WHERE id=%s
            """, (
                theme["name"], theme.get("query_text", ""),
                theme.get("include_keywords_json", "[]"),
                theme.get("exclude_keywords_json", "[]"),
                theme.get("desired_skills_json", "[]"),
                theme.get("min_budget", 0),
                theme.get("contract_type", "any"),
                1 if theme.get("active", True) else 0,
                now, theme["id"],
            ))
            return theme["id"]
        else:
            c.execute("""
                INSERT INTO search_themes
                    (name, query_text, include_keywords_json, exclude_keywords_json,
                     desired_skills_json, min_budget, contract_type, active,
                     created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                theme["name"], theme.get("query_text", ""),
                theme.get("include_keywords_json", "[]"),
                theme.get("exclude_keywords_json", "[]"),
                theme.get("desired_skills_json", "[]"),
                theme.get("min_budget", 0),
                theme.get("contract_type", "any"),
                1 if theme.get("active", True) else 0,
                now, now,
            ))
            return c.fetchone()[0]


def get_themes(active_only=False):
    with get_conn() as conn:
        c = conn.cursor()
        if active_only:
            c.execute("SELECT * FROM search_themes WHERE active=1 ORDER BY name")
        else:
            c.execute("SELECT * FROM search_themes ORDER BY name")
        return _rows_as_dicts(c)


def delete_theme(theme_id):
    with get_conn() as conn:
        conn.cursor().execute("DELETE FROM search_themes WHERE id=%s", (theme_id,))


def seed_default_themes():
    from config import DEFAULT_THEMES
    existing_names = {t["name"] for t in get_themes()}
    for theme in DEFAULT_THEMES:
        if theme["name"] not in existing_names:
            upsert_theme(theme)


# ── Jobs ──────────────────────────────────────────────────────────────────────

def insert_job(job):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO jobs
                    (external_url, source_method, search_theme_id, title,
                     description_raw, description_clean, posted_at,
                     budget_type, budget_min, budget_max, hourly_min, hourly_max,
                     skills_json, client_name_if_visible, client_country,
                     client_payment_verified, client_spend_text, client_hire_rate_text,
                     proposal_activity_text, raw_snapshot_path, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (external_url) DO NOTHING
                RETURNING id
            """, (
                job.get("external_url"), job.get("source_method", "browser_manual"),
                job.get("search_theme_id"), job.get("title"),
                job.get("description_raw"), job.get("description_clean"),
                job.get("posted_at"),
                job.get("budget_type"), job.get("budget_min"), job.get("budget_max"),
                job.get("hourly_min"), job.get("hourly_max"),
                job.get("skills_json", "[]"),
                job.get("client_name_if_visible"), job.get("client_country"),
                1 if job.get("client_payment_verified") else 0,
                job.get("client_spend_text"), job.get("client_hire_rate_text"),
                job.get("proposal_activity_text"), job.get("raw_snapshot_path"),
                now, now,
            ))
            row = c.fetchone()
            return row[0] if row else None
        except Exception:
            return None


def get_job(job_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM jobs WHERE id=%s", (job_id,))
        return _row_as_dict(c)


def get_jobs_with_scores(
    theme_ids=None,
    statuses=None,
    min_score=None,
    budget_type=None,
    source_method=None,
    order_by="combined_score DESC NULLS LAST",
    limit=200,
):
    with get_conn() as conn:
        c = conn.cursor()

        query = """
            SELECT j.*,
                   s.relevance_score, s.automation_score, s.win_likelihood_score,
                   s.combined_score, s.explanation_json,
                   ws.status, ws.notes, ws.applied_at, ws.outcome,
                   st.name AS theme_name
            FROM jobs j
            LEFT JOIN scores s ON s.job_id = j.id
            LEFT JOIN workflow_status ws ON ws.job_id = j.id
            LEFT JOIN search_themes st ON st.id = j.search_theme_id
            WHERE 1=1
        """
        params = []

        if theme_ids:
            query += f" AND j.search_theme_id = ANY(%s)"
            params.append(theme_ids)

        if statuses:
            if "new" in statuses:
                query += " AND (ws.status = ANY(%s) OR ws.status IS NULL)"
            else:
                query += " AND ws.status = ANY(%s)"
            params.append(statuses)

        if min_score is not None:
            query += " AND s.combined_score >= %s"
            params.append(min_score)

        if budget_type and budget_type != "any":
            query += " AND j.budget_type = %s"
            params.append(budget_type)

        if source_method:
            query += " AND j.source_method = %s"
            params.append(source_method)

        query += f" ORDER BY {order_by} LIMIT %s"
        params.append(limit)

        c.execute(query, params)
        return _rows_as_dicts(c)


# ── Scores ────────────────────────────────────────────────────────────────────

def upsert_score(job_id, scores):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO scores
                (job_id, relevance_score, automation_score, win_likelihood_score,
                 combined_score, explanation_json, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (job_id) DO UPDATE SET
                relevance_score=EXCLUDED.relevance_score,
                automation_score=EXCLUDED.automation_score,
                win_likelihood_score=EXCLUDED.win_likelihood_score,
                combined_score=EXCLUDED.combined_score,
                explanation_json=EXCLUDED.explanation_json,
                created_at=EXCLUDED.created_at
        """, (
            job_id, scores["relevance_score"], scores["automation_score"],
            scores["win_likelihood_score"], scores["combined_score"],
            json.dumps(scores.get("explanation", {})), now,
        ))


# ── Proposals ─────────────────────────────────────────────────────────────────

def upsert_proposal(job_id, proposal):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO proposals
                (job_id, diagnosis_text, positioning_text, opening_paragraph,
                 upsell_text, caution_text, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (job_id) DO UPDATE SET
                diagnosis_text=EXCLUDED.diagnosis_text,
                positioning_text=EXCLUDED.positioning_text,
                opening_paragraph=EXCLUDED.opening_paragraph,
                upsell_text=EXCLUDED.upsell_text,
                caution_text=EXCLUDED.caution_text,
                updated_at=EXCLUDED.updated_at
        """, (
            job_id, proposal.get("diagnosis_text"), proposal.get("positioning_text"),
            proposal.get("opening_paragraph"), proposal.get("upsell_text"),
            proposal.get("caution_text"), now, now,
        ))


def get_proposal(job_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM proposals WHERE job_id=%s", (job_id,))
        return _row_as_dict(c)


# ── Workflow Status ───────────────────────────────────────────────────────────

def set_status(job_id, status, notes=None, applied_at=None, outcome=None):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO workflow_status
                (job_id, status, notes, applied_at, outcome, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (job_id) DO UPDATE SET
                status=EXCLUDED.status,
                notes=COALESCE(EXCLUDED.notes, workflow_status.notes),
                applied_at=COALESCE(EXCLUDED.applied_at, workflow_status.applied_at),
                outcome=COALESCE(EXCLUDED.outcome, workflow_status.outcome),
                updated_at=EXCLUDED.updated_at
        """, (job_id, status, notes, applied_at, outcome, now, now))


def get_status(job_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM workflow_status WHERE job_id=%s", (job_id,))
        return _row_as_dict(c)


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM jobs")
        total_jobs = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM scores WHERE combined_score >= 75")
        high_priority = c.fetchone()[0]

        c.execute("""
            SELECT COUNT(*) FROM jobs j
            LEFT JOIN workflow_status ws ON ws.job_id = j.id
            WHERE ws.status IS NULL OR ws.status = 'new'
        """)
        pending_review = c.fetchone()[0]

        c.execute("SELECT status, COUNT(*) FROM workflow_status GROUP BY status")
        status_counts = {row[0]: row[1] for row in c.fetchall()}

    return {
        "total_jobs": total_jobs,
        "high_priority": high_priority,
        "pending_review": pending_review,
        "status_counts": status_counts,
    }


# ── Export ────────────────────────────────────────────────────────────────────

def get_jobs_for_export(statuses=None):
    with get_conn() as conn:
        c = conn.cursor()

        query = """
            SELECT j.id, st.name AS search_theme, j.title, j.external_url, j.posted_at,
                   j.budget_type, j.budget_min, j.budget_max, j.hourly_min, j.hourly_max,
                   j.skills_json, j.client_country, j.client_payment_verified,
                   j.client_spend_text, j.client_hire_rate_text,
                   s.relevance_score, s.automation_score, s.win_likelihood_score, s.combined_score,
                   p.diagnosis_text AS opportunity_hypothesis,
                   p.opening_paragraph AS proposal_angle,
                   ws.status, ws.notes, ws.applied_at, ws.outcome,
                   j.source_method
            FROM jobs j
            LEFT JOIN scores s ON s.job_id = j.id
            LEFT JOIN proposals p ON p.job_id = j.id
            LEFT JOIN workflow_status ws ON ws.job_id = j.id
            LEFT JOIN search_themes st ON st.id = j.search_theme_id
            WHERE 1=1
        """
        params = []
        if statuses:
            query += " AND ws.status = ANY(%s)"
            params.append(statuses)

        query += " ORDER BY s.combined_score DESC NULLS LAST"
        c.execute(query, params)
        return _rows_as_dicts(c)
