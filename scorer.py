import json
import re
from datetime import datetime, timezone

from config import AUTOMATION_SIGNALS, AUTOMATION_PENALTIES, WEIGHTS, WIN_THRESHOLDS


def _lower(text):
    return (text or "").lower()


def _count_signals(text, signals):
    text_lower = _lower(text)
    matched = [s for s in signals if s.lower() in text_lower]
    return len(matched), matched


# ── Automation Opportunity Score ──────────────────────────────────────────────

def score_automation(job):
    combined = " ".join([
        job.get("title") or "",
        job.get("description_clean") or job.get("description_raw") or "",
        job.get("skills_json") or "",
    ])

    rep_n, rep_m = _count_signals(combined, AUTOMATION_SIGNALS["repetitive_task"])
    struct_n, struct_m = _count_signals(combined, AUTOMATION_SIGNALS["structured_input"])
    out_n, out_m = _count_signals(combined, AUTOMATION_SIGNALS["recurring_output"])
    role_n, role_m = _count_signals(combined, AUTOMATION_SIGNALS["operations_role"])
    scale_n, scale_m = _count_signals(combined, AUTOMATION_SIGNALS["scale_volume"])
    pen_n, pen_m = _count_signals(combined, AUTOMATION_PENALTIES)

    rep_s = min(rep_n / 3 * 100, 100)
    struct_s = min(struct_n / 3 * 100, 100)
    out_s = min(out_n / 2 * 100, 100)
    role_s = min(role_n / 2 * 100, 100)
    scale_s = min(scale_n / 2 * 100, 100)
    pen_s = min(pen_n / 2 * 100, 100)

    raw = (
        rep_s * 0.30
        + struct_s * 0.25
        + out_s * 0.20
        + role_s * 0.15
        + scale_s * 0.10
    ) - (pen_s * 0.25)

    score = round(max(0.0, min(100.0, raw)), 1)

    explanation = {
        "repetitive_task":  {"score": round(rep_s),    "matched": rep_m},
        "structured_input": {"score": round(struct_s),  "matched": struct_m},
        "recurring_output": {"score": round(out_s),     "matched": out_m},
        "operations_role":  {"score": round(role_s),    "matched": role_m},
        "scale_volume":     {"score": round(scale_s),   "matched": scale_m},
        "penalty":          {"score": round(pen_s),     "matched": pen_m},
    }
    return score, explanation


# ── Relevance Score ───────────────────────────────────────────────────────────

def score_relevance(job, theme):
    if not theme:
        return 50.0, {"note": "No theme assigned — default score applied"}

    combined = " ".join([
        job.get("title") or "",
        job.get("description_clean") or job.get("description_raw") or "",
        job.get("skills_json") or "",
    ])
    text_lower = _lower(combined)

    # Include keywords
    try:
        include_kw = json.loads(theme.get("include_keywords_json") or "[]")
    except Exception:
        include_kw = []
    kw_matched = [k for k in include_kw if k.lower() in text_lower]
    kw_score = (len(kw_matched) / len(include_kw) * 100) if include_kw else 50.0

    # Skills match
    try:
        desired_skills = json.loads(theme.get("desired_skills_json") or "[]")
    except Exception:
        desired_skills = []
    skills_matched = [s for s in desired_skills if s.lower() in text_lower]
    skills_score = (len(skills_matched) / len(desired_skills) * 100) if desired_skills else 50.0

    # Budget adequacy
    min_budget = float(theme.get("min_budget") or 0)
    job_budget = float(job.get("budget_min") or job.get("hourly_min") or 0)
    if min_budget and job_budget:
        if job_budget >= min_budget:
            budget_score = 100.0
        elif job_budget >= min_budget * 0.6:
            budget_score = 65.0
        else:
            budget_score = 20.0
    else:
        budget_score = 50.0

    # Contract type
    contract_type = theme.get("contract_type", "any")
    contract_score = 100.0 if contract_type == "any" else (
        100.0 if job.get("budget_type") == contract_type else 40.0
    )

    # Exclude keyword penalty
    try:
        exclude_kw = json.loads(theme.get("exclude_keywords_json") or "[]")
    except Exception:
        exclude_kw = []
    exclude_matched = [k for k in exclude_kw if k.lower() in text_lower]
    exclude_penalty = len(exclude_matched) * 15

    raw = (
        kw_score * 0.45
        + skills_score * 0.25
        + budget_score * 0.20
        + contract_score * 0.10
    ) - exclude_penalty

    score = round(max(0.0, min(100.0, raw)), 1)

    explanation = {
        "keyword_match":   {"score": round(kw_score),      "matched": kw_matched,      "total": len(include_kw)},
        "skills_match":    {"score": round(skills_score),   "matched": skills_matched},
        "budget_match":    {"score": round(budget_score),   "job_budget": job_budget,   "min_required": min_budget},
        "contract_match":  {"score": round(contract_score)},
        "exclude_penalty": {"penalty": exclude_penalty,     "matched": exclude_matched},
    }
    return score, explanation


# ── Win-Likelihood Score ──────────────────────────────────────────────────────

def score_win_likelihood(job):
    base = 50.0
    bonuses = 0.0
    penalties = 0.0
    explanation = {}

    # Freshness
    freshness_bonus = 0.0
    posted_at = job.get("posted_at")
    if posted_at:
        try:
            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_old = (now - posted_dt).total_seconds() / 3600
            if hours_old <= WIN_THRESHOLDS["fresh_hours_great"]:
                freshness_bonus = 25.0
            elif hours_old <= WIN_THRESHOLDS["fresh_hours_good"]:
                freshness_bonus = 15.0
            elif hours_old <= WIN_THRESHOLDS["fresh_hours_ok"]:
                freshness_bonus = 5.0
            explanation["freshness_hours"] = round(hours_old, 1)
        except Exception:
            freshness_bonus = 5.0
            explanation["freshness_hours"] = "unknown"
    explanation["freshness_bonus"] = freshness_bonus
    bonuses += freshness_bonus

    # Payment verified
    if job.get("client_payment_verified"):
        bonuses += 10.0
        explanation["payment_verified_bonus"] = 10
    else:
        explanation["payment_verified_bonus"] = 0

    # Client spend history
    spend_text = _lower(job.get("client_spend_text") or "")
    spend_bonus = 0.0
    if any(x in spend_text for x in ["$100k", "$50k", "100,000", "50,000"]):
        spend_bonus = 15.0
    elif any(x in spend_text for x in ["$10k", "$5k", "10,000", "5,000"]):
        spend_bonus = 8.0
    elif any(x in spend_text for x in ["$1k", "1,000"]):
        spend_bonus = 4.0
    explanation["spend_bonus"] = spend_bonus
    bonuses += spend_bonus

    # Hire rate
    hire_text = _lower(job.get("client_hire_rate_text") or "")
    hire_bonus = 0.0
    hire_match = re.search(r"(\d+)%", hire_text)
    if hire_match:
        rate = int(hire_match.group(1))
        if rate >= 70:
            hire_bonus = 15.0
        elif rate >= 40:
            hire_bonus = 8.0
        else:
            hire_bonus = -5.0
    explanation["hire_rate_bonus"] = hire_bonus
    bonuses += hire_bonus

    # Budget adequacy
    budget_bonus = 0.0
    if job.get("budget_type") == "fixed" and float(job.get("budget_min") or 0) >= WIN_THRESHOLDS["good_budget_fixed_min"]:
        budget_bonus = 10.0
    elif job.get("budget_type") == "hourly" and float(job.get("hourly_min") or 0) >= WIN_THRESHOLDS["good_budget_hourly_min"]:
        budget_bonus = 10.0
    explanation["budget_bonus"] = budget_bonus
    bonuses += budget_bonus

    # Competition / proposal count
    prop_text = _lower(job.get("proposal_activity_text") or "")
    competition_penalty = 0.0
    prop_match = re.search(r"(\d+)", prop_text)
    if prop_match and any(w in prop_text for w in ["proposal", "bid", "applicant"]):
        n = int(prop_match.group(1))
        if n <= 5:
            competition_penalty = 0.0
        elif n <= 15:
            competition_penalty = 10.0
        elif n <= 30:
            competition_penalty = 20.0
        else:
            competition_penalty = 30.0
    explanation["competition_penalty"] = competition_penalty
    penalties += competition_penalty

    score = round(max(0.0, min(100.0, base + bonuses - penalties)), 1)
    return score, explanation


# ── Combined ──────────────────────────────────────────────────────────────────

def compute_scores(job, theme=None):
    automation_score, auto_exp = score_automation(job)
    relevance_score, rel_exp = score_relevance(job, theme)
    win_score, win_exp = score_win_likelihood(job)

    combined = round(
        relevance_score * WEIGHTS["relevance"]
        + automation_score * WEIGHTS["automation"]
        + win_score * WEIGHTS["win_likelihood"],
        1,
    )

    return {
        "relevance_score": relevance_score,
        "automation_score": automation_score,
        "win_likelihood_score": win_score,
        "combined_score": combined,
        "explanation": {
            "relevance": rel_exp,
            "automation": auto_exp,
            "win_likelihood": win_exp,
        },
    }
