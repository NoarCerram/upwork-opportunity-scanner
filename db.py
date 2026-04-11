import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS search_themes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            query_text TEXT,
            include_keywords_json TEXT DEFAULT '[]',
            exclude_keywords_json TEXT DEFAULT '[]',
            desired_skills_json TEXT DEFAULT '[]',
            min_budget REAL DEFAULT 0,
            contract_type TEXT DEFAULT 'any',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_url TEXT UNIQUE,
            source_method TEXT DEFAULT 'browser_manual',
            search_theme_id INTEGER,
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            relevance_score REAL DEFAULT 0,
            automation_score REAL DEFAULT 0,
            win_likelihood_score REAL DEFAULT 0,
            combined_score REAL DEFAULT 0,
            explanation_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            diagnosis_text TEXT,
            positioning_text TEXT,
            opening_paragraph TEXT,
            upsell_text TEXT,
            caution_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS workflow_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            status TEXT DEFAULT 'new',
            notes TEXT,
            applied_at TEXT,
            outcome TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)

    conn.commit()
    conn.close()


# ── Search Themes ─────────────────────────────────────────────────────────────

def upsert_theme(theme):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    if theme.get("id"):
        c.execute("""
            UPDATE search_themes SET
                name=?, query_text=?, include_keywords_json=?,
                exclude_keywords_json=?, desired_skills_json=?,
                min_budget=?, contract_type=?, active=?, updated_at=?
            WHERE id=?
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
        row_id = theme["id"]
    else:
        c.execute("""
            INSERT INTO search_themes
                (name, query_text, include_keywords_json, exclude_keywords_json,
                 desired_skills_json, min_budget, contract_type, active,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
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
        row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_themes(active_only=False):
    conn = get_conn()
    c = conn.cursor()
    if active_only:
        c.execute("SELECT * FROM search_themes WHERE active=1 ORDER BY name")
    else:
        c.execute("SELECT * FROM search_themes ORDER BY name")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_theme(theme_id):
    conn = get_conn()
    conn.execute("DELETE FROM search_themes WHERE id=?", (theme_id,))
    conn.commit()
    conn.close()


def seed_default_themes():
    from config import DEFAULT_THEMES
    existing_names = {t["name"] for t in get_themes()}
    for theme in DEFAULT_THEMES:
        if theme["name"] not in existing_names:
            upsert_theme(theme)


# ── Jobs ──────────────────────────────────────────────────────────────────────

def insert_job(job):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        c.execute("""
            INSERT OR IGNORE INTO jobs
                (external_url, source_method, search_theme_id, title,
                 description_raw, description_clean, posted_at,
                 budget_type, budget_min, budget_max, hourly_min, hourly_max,
                 skills_json, client_name_if_visible, client_country,
                 client_payment_verified, client_spend_text, client_hire_rate_text,
                 proposal_activity_text, raw_snapshot_path, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        conn.commit()
        job_id = c.lastrowid if c.rowcount > 0 else None
    except Exception:
        job_id = None
    conn.close()
    return job_id


def get_job(job_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_jobs_with_scores(
    theme_ids=None,
    statuses=None,
    min_score=None,
    budget_type=None,
    source_method=None,
    order_by="combined_score DESC",
    limit=200,
):
    conn = get_conn()
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
        placeholders = ",".join("?" * len(theme_ids))
        query += f" AND j.search_theme_id IN ({placeholders})"
        params.extend(theme_ids)

    if statuses:
        placeholders = ",".join("?" * len(statuses))
        if "new" in statuses:
            query += f" AND (ws.status IN ({placeholders}) OR ws.status IS NULL)"
        else:
            query += f" AND ws.status IN ({placeholders})"
        params.extend(statuses)

    if min_score is not None:
        query += " AND s.combined_score >= ?"
        params.append(min_score)

    if budget_type and budget_type != "any":
        query += " AND j.budget_type = ?"
        params.append(budget_type)

    if source_method:
        query += " AND j.source_method = ?"
        params.append(source_method)

    query += f" ORDER BY {order_by} LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Scores ────────────────────────────────────────────────────────────────────

def upsert_score(job_id, scores):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("SELECT id FROM scores WHERE job_id=?", (job_id,))
    if c.fetchone():
        c.execute("""
            UPDATE scores SET
                relevance_score=?, automation_score=?, win_likelihood_score=?,
                combined_score=?, explanation_json=?, created_at=?
            WHERE job_id=?
        """, (
            scores["relevance_score"], scores["automation_score"],
            scores["win_likelihood_score"], scores["combined_score"],
            json.dumps(scores.get("explanation", {})), now, job_id,
        ))
    else:
        c.execute("""
            INSERT INTO scores
                (job_id, relevance_score, automation_score, win_likelihood_score,
                 combined_score, explanation_json, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            job_id, scores["relevance_score"], scores["automation_score"],
            scores["win_likelihood_score"], scores["combined_score"],
            json.dumps(scores.get("explanation", {})), now,
        ))
    conn.commit()
    conn.close()


# ── Proposals ─────────────────────────────────────────────────────────────────

def upsert_proposal(job_id, proposal):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("SELECT id FROM proposals WHERE job_id=?", (job_id,))
    if c.fetchone():
        c.execute("""
            UPDATE proposals SET
                diagnosis_text=?, positioning_text=?, opening_paragraph=?,
                upsell_text=?, caution_text=?, updated_at=?
            WHERE job_id=?
        """, (
            proposal.get("diagnosis_text"), proposal.get("positioning_text"),
            proposal.get("opening_paragraph"), proposal.get("upsell_text"),
            proposal.get("caution_text"), now, job_id,
        ))
    else:
        c.execute("""
            INSERT INTO proposals
                (job_id, diagnosis_text, positioning_text, opening_paragraph,
                 upsell_text, caution_text, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            job_id, proposal.get("diagnosis_text"), proposal.get("positioning_text"),
            proposal.get("opening_paragraph"), proposal.get("upsell_text"),
            proposal.get("caution_text"), now, now,
        ))
    conn.commit()
    conn.close()


def get_proposal(job_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM proposals WHERE job_id=?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ── Workflow Status ───────────────────────────────────────────────────────────

def set_status(job_id, status, notes=None, applied_at=None, outcome=None):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("SELECT id FROM workflow_status WHERE job_id=?", (job_id,))
    if c.fetchone():
        sets = ["status=?", "updated_at=?"]
        params = [status, now]
        if notes is not None:
            sets.append("notes=?")
            params.append(notes)
        if applied_at is not None:
            sets.append("applied_at=?")
            params.append(applied_at)
        if outcome is not None:
            sets.append("outcome=?")
            params.append(outcome)
        params.append(job_id)
        c.execute(f"UPDATE workflow_status SET {', '.join(sets)} WHERE job_id=?", params)
    else:
        c.execute("""
            INSERT INTO workflow_status
                (job_id, status, notes, applied_at, outcome, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
        """, (job_id, status, notes, applied_at, outcome, now, now))
    conn.commit()
    conn.close()


def get_status(job_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM workflow_status WHERE job_id=?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats():
    conn = get_conn()
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

    conn.close()
    return {
        "total_jobs": total_jobs,
        "high_priority": high_priority,
        "pending_review": pending_review,
        "status_counts": status_counts,
    }


# ── Export ────────────────────────────────────────────────────────────────────

def get_jobs_for_export(statuses=None):
    conn = get_conn()
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
        placeholders = ",".join("?" * len(statuses))
        query += f" AND ws.status IN ({placeholders})"
        params.extend(statuses)

    query += " ORDER BY s.combined_score DESC NULLS LAST"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
