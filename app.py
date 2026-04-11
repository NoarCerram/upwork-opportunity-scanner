import os
import re
import csv
import io
import json
from datetime import datetime

import streamlit as st

# Inject DATABASE_URL from Streamlit secrets into the environment before
# any module that reads config.DATABASE_URL at import time is loaded.
if "DATABASE_URL" not in os.environ:
    try:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        pass

import db
import scorer
import hypothesis
import proposal
import ingestion

st.set_page_config(
    page_title="Upwork Opportunity Scanner",
    page_icon="🎯",
    layout="wide",
)

# ── Bootstrap ─────────────────────────────────────────────────────────────────

db.init_db()
db.seed_default_themes()

# ── Helpers ───────────────────────────────────────────────────────────────────

def process_job(job_dict, theme_id=None):
    """Normalize, score, generate proposal, save. Returns job_id or None."""
    if theme_id:
        job_dict["search_theme_id"] = theme_id

    job_id = db.insert_job(job_dict)
    if not job_id:
        return None

    job_full = db.get_job(job_id)
    theme_obj = None
    if theme_id:
        theme_obj = next((t for t in db.get_themes() if t["id"] == theme_id), None)

    scores = scorer.compute_scores(job_full, theme_obj)
    db.upsert_score(job_id, scores)

    hyp = hypothesis.generate_hypothesis(job_full, scores)
    offer = hypothesis.generate_offer_angle(job_full, scores)
    prop = proposal.generate_proposal(job_full, scores, hyp)
    prop["diagnosis_text"] = hyp + "\n\n" + offer
    db.upsert_proposal(job_id, prop)
    db.set_status(job_id, "new")
    return job_id


def score_badge(score):
    if score is None:
        return "—"
    s = float(score)
    if s >= 75:
        return f"🟢 {s:.0f}"
    if s >= 50:
        return f"🟡 {s:.0f}"
    return f"🔴 {s:.0f}"


STATUS_ICONS = {
    "new": "🆕", "reviewed": "👁️", "shortlisted": "⭐",
    "passed": "❌", "applied": "📤", "archived": "🗃️",
    "interviewing": "💬", "won": "🏆", "lost": "😔",
}
ALL_STATUSES = ["new", "reviewed", "shortlisted", "passed", "applied", "archived"]

# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("🎯 Upwork Scanner")
st.sidebar.markdown("---")

stats = db.get_stats()
col_a, col_b, col_c = st.sidebar.columns(3)
col_a.metric("Total", stats["total_jobs"])
col_b.metric("🔥 Hot", stats["high_priority"])
col_c.metric("Inbox", stats["pending_review"])

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    ["📥 Import", "📋 Review Queue", "🔍 Search Themes", "📤 Export"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "⚠️ **Compliance notice:** Upwork-originated client relationships must remain "
    "on-platform for communications and payments during the non-circumvention period. "
    "This tool is for internal research and proposal support only."
)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: IMPORT
# ══════════════════════════════════════════════════════════════════════════════

if page == "📥 Import":
    st.title("📥 Import Jobs")
    st.markdown(
        "Add Upwork job listings via paste, URL, HTML snapshot, or JSON. "
        "All paths feed the same scoring pipeline."
    )

    themes = db.get_themes(active_only=True)
    theme_options = {t["name"]: t["id"] for t in themes}

    top_col1, top_col2, top_col3 = st.columns([3, 2, 2])
    with top_col2:
        selected_theme_name = st.selectbox(
            "Assign to search theme",
            ["— none —"] + list(theme_options.keys()),
        )
        selected_theme_id = theme_options.get(selected_theme_name)
    with top_col3:
        source_method = st.selectbox(
            "Source method",
            ["browser_manual", "browser_agent", "direct_source"],
        )

    st.markdown("---")
    tab_text, tab_url, tab_html, tab_json = st.tabs(
        ["📝 Paste Text", "🔗 URL List", "🌐 HTML Snapshot", "📊 JSON Import"]
    )

    # ── Tab: Paste Text ────────────────────────────────────────────────────────
    with tab_text:
        st.markdown(
            "Paste one or more job descriptions. "
            "Separate multiple jobs with `---` on its own line."
        )
        text_input = st.text_area(
            "Job description(s)", height=300,
            placeholder=(
                "Paste the job title, description, budget, skills, client details...\n\n"
                "Separate multiple jobs with\n---"
            ),
        )
        url_hint = st.text_input(
            "Job URL (optional — paste the Upwork link for this job)",
            placeholder="https://www.upwork.com/jobs/~...",
        )

        if st.button("Import from Text", type="primary", key="btn_text"):
            if not text_input.strip():
                st.warning("Paste some job text first.")
            else:
                blocks = re.split(r"\n-{3,}\n", text_input)
                imported = 0
                for i, block in enumerate(blocks):
                    block = block.strip()
                    if not block:
                        continue
                    url = url_hint.strip() if (i == 0 and url_hint.strip()) else None
                    job_dict = ingestion.parse_text_block(
                        block, source_url=url, source_method=source_method
                    )
                    if job_dict and process_job(job_dict, selected_theme_id):
                        imported += 1

                if imported:
                    st.success(f"Imported {imported} job(s).")
                    st.rerun()
                else:
                    st.error("Could not parse any jobs from the provided text.")

    # ── Tab: URL List ──────────────────────────────────────────────────────────
    with tab_url:
        st.markdown(
            "Paste Upwork job URLs, one per line. "
            "The system will attempt to fetch each page — note that Upwork may require "
            "a logged-in session for full job details."
        )
        urls_text = st.text_area(
            "Job URLs", height=200,
            placeholder=(
                "https://www.upwork.com/jobs/~01abc...\n"
                "https://www.upwork.com/jobs/~02def..."
            ),
        )

        if st.button("Import URLs", type="primary", key="btn_url"):
            if not urls_text.strip():
                st.warning("Paste some URLs first.")
            else:
                urls = ingestion.parse_url_list(urls_text)
                if not urls:
                    st.warning("No valid Upwork job URLs detected.")
                else:
                    bar = st.progress(0, text=f"Importing {len(urls)} URL(s)…")
                    imported = 0
                    for i, url in enumerate(urls):
                        bar.progress((i + 1) / len(urls), text=f"Fetching {url[:70]}…")
                        job_dict = ingestion.fetch_job_url(url, source_method=source_method)
                        if not job_dict:
                            # Store as stub so user can enrich it later
                            job_dict = {
                                "external_url": url,
                                "source_method": source_method,
                                "title": f"Job — {url.split('/')[-1][:60]}",
                                "description_raw": "",
                                "description_clean": "",
                                "skills_json": "[]",
                            }
                        else:
                            job_dict["source_method"] = source_method
                        if process_job(job_dict, selected_theme_id):
                            imported += 1
                    bar.empty()
                    st.success(f"Imported {imported} job(s) from {len(urls)} URL(s).")
                    st.rerun()

    # ── Tab: HTML Snapshot ─────────────────────────────────────────────────────
    with tab_html:
        st.markdown(
            "Paste the full HTML of an Upwork search results page. "
            "**How to get it:** open the search page in Chrome → right-click → "
            "View Page Source (Ctrl+U) → select all → paste here."
        )
        html_input = st.text_area("HTML content", height=300, placeholder="<!DOCTYPE html>…")

        if st.button("Parse HTML", type="primary", key="btn_html"):
            if not html_input.strip():
                st.warning("Paste some HTML first.")
            else:
                found = ingestion.parse_html_snapshot(html_input, source_method=source_method)
                if not found:
                    st.warning(
                        "No jobs extracted from the HTML. "
                        "Try the Paste Text tab instead."
                    )
                else:
                    imported = sum(
                        1 for j in found if process_job(j, selected_theme_id)
                    )
                    st.success(f"Extracted and imported {imported} job(s).")
                    st.rerun()

    # ── Tab: JSON Import ───────────────────────────────────────────────────────
    with tab_json:
        st.markdown("Paste a JSON array of job objects — useful when importing from a browser agent.")
        st.code(
            '[{\n'
            '  "url": "https://www.upwork.com/jobs/~...",\n'
            '  "title": "VA for CRM updates",\n'
            '  "description": "We need someone to...",\n'
            '  "budget_type": "fixed",\n'
            '  "budget_min": 200,\n'
            '  "skills": ["HubSpot", "Data Entry"],\n'
            '  "client_country": "US",\n'
            '  "client_payment_verified": true,\n'
            '  "client_spend_text": "$5k+",\n'
            '  "hire_rate": "80%",\n'
            '  "proposals": "5-10 proposals"\n'
            '}]',
            language="json",
        )
        json_input = st.text_area("JSON data", height=200, placeholder="[{…}]")

        if st.button("Import JSON", type="primary", key="btn_json"):
            if not json_input.strip():
                st.warning("Paste JSON data first.")
            else:
                found = ingestion.parse_json_import(json_input, source_method=source_method)
                if not found:
                    st.error("Could not parse JSON. Check the format.")
                else:
                    imported = sum(
                        1 for j in found if process_job(j, selected_theme_id)
                    )
                    st.success(f"Imported {imported} job(s).")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: REVIEW QUEUE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📋 Review Queue":
    st.title("📋 Review Queue")

    themes = db.get_themes()
    theme_map = {t["id"]: t["name"] for t in themes}

    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        filter_themes = fc1.multiselect(
            "Search Theme",
            options=[t["id"] for t in themes],
            format_func=lambda x: theme_map.get(x, str(x)),
        )
        filter_statuses = fc2.multiselect(
            "Status", ALL_STATUSES, default=["new", "shortlisted"]
        )
        min_score_filter = fc3.slider("Min Combined Score", 0, 100, 0)
        budget_type_filter = fc4.selectbox("Budget Type", ["any", "fixed", "hourly"])

    jobs = db.get_jobs_with_scores(
        theme_ids=filter_themes or None,
        statuses=filter_statuses or None,
        min_score=min_score_filter if min_score_filter > 0 else None,
        budget_type=budget_type_filter if budget_type_filter != "any" else None,
    )

    st.markdown(f"**{len(jobs)} job(s)** matching filters")

    if not jobs:
        st.info("No jobs found. Import some using the Import page.")
    else:
        for job in jobs:
            job_id = job["id"]
            status = job.get("status") or "new"
            combined = job.get("combined_score")
            rel = job.get("relevance_score")
            auto = job.get("automation_score")
            win = job.get("win_likelihood_score")

            # Budget display
            if job.get("budget_type") == "fixed":
                lo, hi = job.get("budget_min"), job.get("budget_max")
                budget_str = f"${lo:.0f}–${hi:.0f}" if lo and hi else (f"${lo:.0f}" if lo else "—")
                budget_str += " fixed"
            elif job.get("budget_type") == "hourly":
                lo, hi = job.get("hourly_min"), job.get("hourly_max")
                budget_str = f"${lo:.0f}–${hi:.0f}/hr" if lo and hi else (f"${lo:.0f}/hr" if lo else "—")
            else:
                budget_str = "—"

            header = (
                f"{STATUS_ICONS.get(status, '•')} **{job.get('title', 'Untitled')}** "
                f"| {job.get('theme_name') or '—'} "
                f"| {budget_str} "
                f"| Combined: {score_badge(combined)}"
            )

            with st.expander(header):
                left, right = st.columns([2, 1])

                with left:
                    url = job.get("external_url", "")
                    if url.startswith("http"):
                        st.markdown(f"**URL:** [{url}]({url})")
                    else:
                        st.markdown(f"**URL:** `{url}`")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.markdown(f"**Budget**\n{budget_str}")
                    m2.markdown(f"**Posted**\n{job.get('posted_at') or '—'}")
                    m3.markdown(f"**Client**\n{'✅ Verified' if job.get('client_payment_verified') else '❓ Unverified'}")
                    m4.markdown(f"**Method**\n{job.get('source_method') or '—'}")

                    extras = []
                    if job.get("client_country"):
                        extras.append(f"Country: {job['client_country']}")
                    if job.get("client_spend_text"):
                        extras.append(f"Spend: {job['client_spend_text']}")
                    if job.get("proposal_activity_text"):
                        extras.append(f"Proposals: {job['proposal_activity_text']}")
                    if extras:
                        st.caption("  ·  ".join(extras))

                    desc = job.get("description_clean") or job.get("description_raw") or ""
                    if desc:
                        st.markdown("**Description**")
                        st.text(desc[:800] + ("…" if len(desc) > 800 else ""))

                with right:
                    st.markdown("**Scores**")
                    sc1, sc2 = st.columns(2)
                    sc1.metric("Relevance", f"{rel:.0f}" if rel is not None else "—")
                    sc2.metric("Automation", f"{auto:.0f}" if auto is not None else "—")
                    sc1.metric("Win", f"{win:.0f}" if win is not None else "—")
                    sc2.metric("Combined", f"{combined:.0f}" if combined is not None else "—")

                    # Score explanation toggle
                    if job.get("explanation_json"):
                        try:
                            exp = json.loads(job["explanation_json"])
                            with st.expander("Score details"):
                                auto_exp = exp.get("automation", {})
                                for dim, data in auto_exp.items():
                                    if isinstance(data, dict) and data.get("matched"):
                                        st.caption(f"**{dim}**: {', '.join(data['matched'][:5])}")
                        except Exception:
                            pass

                    st.markdown("---")
                    st.markdown("**Opportunity**")
                    prop_data = db.get_proposal(job_id)
                    if prop_data:
                        st.caption((prop_data.get("diagnosis_text") or "")[:350])
                        with st.expander("Full proposal draft"):
                            if prop_data.get("positioning_text"):
                                st.markdown("**Positioning**")
                                st.write(prop_data["positioning_text"])
                            if prop_data.get("opening_paragraph"):
                                st.markdown("**Opening paragraph**")
                                st.write(prop_data["opening_paragraph"])
                            if prop_data.get("upsell_text"):
                                st.markdown("**Optional upsell**")
                                st.write(prop_data["upsell_text"])
                            if prop_data.get("caution_text"):
                                st.warning(prop_data["caution_text"])

                    st.markdown("---")
                    st.markdown("**Actions**")

                    new_status = st.selectbox(
                        "Status",
                        ALL_STATUSES,
                        index=ALL_STATUSES.index(status) if status in ALL_STATUSES else 0,
                        key=f"status_{job_id}",
                    )
                    notes = st.text_area(
                        "Notes", value=job.get("notes") or "",
                        key=f"notes_{job_id}", height=70,
                    )

                    btn1, btn2 = st.columns(2)
                    if btn1.button("Save", key=f"save_{job_id}", type="primary"):
                        db.set_status(job_id, new_status, notes=notes)
                        st.success("Saved.")
                        st.rerun()

                    if btn2.button("Regen", key=f"regen_{job_id}", help="Regenerate scores & proposal"):
                        job_full = db.get_job(job_id)
                        theme_obj = None
                        if job.get("search_theme_id"):
                            theme_obj = next(
                                (t for t in themes if t["id"] == job["search_theme_id"]), None
                            )
                        new_scores = scorer.compute_scores(job_full, theme_obj)
                        db.upsert_score(job_id, new_scores)
                        hyp = hypothesis.generate_hypothesis(job_full, new_scores)
                        offer = hypothesis.generate_offer_angle(job_full, new_scores)
                        prop = proposal.generate_proposal(job_full, new_scores, hyp)
                        prop["diagnosis_text"] = hyp + "\n\n" + offer
                        db.upsert_proposal(job_id, prop)
                        st.success("Regenerated.")
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SEARCH THEMES
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🔍 Search Themes":
    st.title("🔍 Search Themes")
    st.markdown(
        "Manage saved search configurations. "
        "Themes tag imported jobs and tune relevance scoring."
    )

    themes = db.get_themes()

    if themes:
        for theme in themes:
            active_icon = "✅" if theme.get("active") else "🚫"
            with st.expander(f"{active_icon} {theme['name']}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    n_name = st.text_input("Name", value=theme["name"], key=f"tn_{theme['id']}")
                    n_query = st.text_input(
                        "Query text", value=theme.get("query_text") or "", key=f"tq_{theme['id']}"
                    )

                    def _load_list(val):
                        try:
                            return ", ".join(json.loads(val or "[]"))
                        except Exception:
                            return ""

                    n_inc = st.text_input(
                        "Include keywords (comma-separated)",
                        value=_load_list(theme.get("include_keywords_json")),
                        key=f"ti_{theme['id']}",
                    )
                    n_exc = st.text_input(
                        "Exclude keywords (comma-separated)",
                        value=_load_list(theme.get("exclude_keywords_json")),
                        key=f"te_{theme['id']}",
                    )
                    n_skills = st.text_input(
                        "Desired skills (comma-separated)",
                        value=_load_list(theme.get("desired_skills_json")),
                        key=f"ts_{theme['id']}",
                    )
                    r1, r2, r3 = st.columns(3)
                    n_budget = r1.number_input(
                        "Min budget ($)", value=float(theme.get("min_budget") or 0),
                        min_value=0.0, key=f"tb_{theme['id']}",
                    )
                    n_ctype = r2.selectbox(
                        "Contract type", ["any", "fixed", "hourly"],
                        index=["any", "fixed", "hourly"].index(theme.get("contract_type") or "any"),
                        key=f"tc_{theme['id']}",
                    )
                    n_active = r3.checkbox(
                        "Active", value=bool(theme.get("active", 1)), key=f"ta_{theme['id']}"
                    )

                with c2:
                    st.markdown("<br>" * 2, unsafe_allow_html=True)
                    if st.button("Save", key=f"tsave_{theme['id']}", type="primary"):
                        def _to_json_list(s):
                            return json.dumps([x.strip() for x in s.split(",") if x.strip()])

                        db.upsert_theme({
                            "id": theme["id"],
                            "name": n_name,
                            "query_text": n_query,
                            "include_keywords_json": _to_json_list(n_inc),
                            "exclude_keywords_json": _to_json_list(n_exc),
                            "desired_skills_json": _to_json_list(n_skills),
                            "min_budget": n_budget,
                            "contract_type": n_ctype,
                            "active": n_active,
                        })
                        st.success("Saved.")
                        st.rerun()
                    if st.button("Delete", key=f"tdel_{theme['id']}"):
                        db.delete_theme(theme["id"])
                        st.warning("Deleted.")
                        st.rerun()

    st.markdown("---")
    st.subheader("Create New Theme")
    with st.form("new_theme"):
        fn_name = st.text_input("Name *", placeholder="e.g. CRM + lead gen")
        fn_query = st.text_input("Query text", placeholder="crm cleanup lead generation")
        fn_inc = st.text_input("Include keywords", placeholder="crm, lead, cleanup, salesforce")
        fn_exc = st.text_input("Exclude keywords", placeholder="senior, director")
        fn_skills = st.text_input("Desired skills", placeholder="CRM, Data Entry, Lead Generation")
        fr1, fr2, fr3 = st.columns(3)
        fn_budget = fr1.number_input("Min budget ($)", min_value=0.0, value=50.0)
        fn_ctype = fr2.selectbox("Contract type", ["any", "fixed", "hourly"])
        fn_active = fr3.checkbox("Active", value=True)
        submitted = st.form_submit_button("Create Theme", type="primary")
        if submitted:
            if not fn_name.strip():
                st.error("Name is required.")
            else:
                def _tojl(s):
                    return json.dumps([x.strip() for x in s.split(",") if x.strip()])

                db.upsert_theme({
                    "name": fn_name.strip(),
                    "query_text": fn_query.strip(),
                    "include_keywords_json": _tojl(fn_inc),
                    "exclude_keywords_json": _tojl(fn_exc),
                    "desired_skills_json": _tojl(fn_skills),
                    "min_budget": fn_budget,
                    "contract_type": fn_ctype,
                    "active": fn_active,
                })
                st.success(f"Theme '{fn_name}' created.")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: EXPORT
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📤 Export":
    st.title("📤 Export")
    st.markdown("Download jobs as CSV for use in spreadsheets, CRMs, or reporting.")

    ec1, ec2 = st.columns(2)
    export_statuses = ec1.multiselect(
        "Filter by status (empty = all)",
        ALL_STATUSES,
        default=["shortlisted", "applied"],
    )

    rows = db.get_jobs_for_export(statuses=export_statuses or None)
    st.markdown(f"**{len(rows)} job(s)** will be exported.")

    if rows:
        fieldnames = [
            "id", "search_theme", "title", "external_url", "posted_at",
            "budget_type", "budget_min", "budget_max", "hourly_min", "hourly_max",
            "skills_json", "client_country", "client_payment_verified",
            "client_spend_text", "client_hire_rate_text",
            "relevance_score", "automation_score", "win_likelihood_score", "combined_score",
            "opportunity_hypothesis", "proposal_angle",
            "status", "notes", "applied_at", "outcome", "source_method",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

        st.download_button(
            "⬇️ Download CSV",
            data=buf.getvalue(),
            file_name=f"upwork_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            type="primary",
        )

        st.markdown("---")
        st.subheader("Preview")
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            preview_cols = [
                c for c in
                ["title", "search_theme", "combined_score", "automation_score",
                 "budget_type", "budget_min", "status"]
                if c in df.columns
            ]
            st.dataframe(df[preview_cols].head(25), use_container_width=True)
        except ImportError:
            for row in rows[:10]:
                st.text(
                    f"{row.get('title', '—')[:50]}  |  "
                    f"score={row.get('combined_score', '—')}  |  "
                    f"status={row.get('status', '—')}"
                )
    else:
        st.info("No jobs to export with the selected filters.")
