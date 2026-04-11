def _detect_workflow_type(auto_exp):
    role_m = " ".join(auto_exp.get("operations_role", {}).get("matched", []))
    struct_m = " ".join(auto_exp.get("structured_input", {}).get("matched", []))
    rep_m = " ".join(auto_exp.get("repetitive_task", {}).get("matched", []))
    out_m = " ".join(auto_exp.get("recurring_output", {}).get("matched", []))
    combined = " ".join([role_m, struct_m, rep_m, out_m]).lower()

    if any(x in combined for x in ["salesforce", "hubspot", "pipedrive", "crm"]):
        return "sales operations / CRM management"
    if any(x in combined for x in ["recruiting", "ats", "applicant tracking", "sourcing", "linkedin"]):
        return "recruiting coordination"
    if any(x in combined for x in ["shopify", "catalog", "product listing", "ecommerce", "e-commerce", "inventory"]):
        return "ecommerce operations"
    if any(x in combined for x in ["virtual assistant", "va ", "executive assistant", "admin", "scheduling", "calendar"]):
        return "administrative / virtual assistance"
    if any(x in combined for x in ["report", "dashboard", "summary", "digest"]):
        return "reporting and data aggregation"
    if any(x in combined for x in ["data entry", "manual entry", "input data"]):
        return "data entry and processing"
    if any(x in combined for x in ["research", "monitor", "extract", "scrape", "compile"]):
        return "research and data monitoring"
    if any(x in combined for x in ["email", "inbox", "outreach"]):
        return "email and outreach operations"
    return "operational workflow"


def generate_hypothesis(job, scores):
    try:
        auto_exp = scores.get("explanation", {}).get("automation", {})
    except Exception:
        auto_exp = {}

    automation_score = scores.get("automation_score", 0)
    workflow_type = _detect_workflow_type(auto_exp)

    struct_matched = auto_exp.get("structured_input", {}).get("matched", [])
    rep_matched = auto_exp.get("repetitive_task", {}).get("matched", [])

    parts = [f"This appears to be a recurring {workflow_type} role."]

    if struct_matched:
        tools = ", ".join(struct_matched[:3])
        parts.append(f"The client is working with: {tools}.")

    if rep_matched:
        signals = ", ".join(rep_matched[:3])
        parts.append(f"Recurring signals detected: {signals}.")

    if automation_score >= 75:
        parts.append(
            "Strong automation opportunity: the tasks show clear repetition, structured inputs, "
            "and predictable outputs — indicators that a workflow system could reduce ongoing labor cost significantly."
        )
    elif automation_score >= 50:
        parts.append(
            "Moderate automation potential: some tasks appear systemizable. "
            "A diagnostic or process audit could identify which portions are worth automating."
        )
    else:
        parts.append(
            "Low automation signals: the role may require significant human judgment. "
            "Position around operational expertise rather than automation."
        )

    return " ".join(parts)


def generate_offer_angle(job, scores):
    automation_score = scores.get("automation_score", 0)

    if automation_score >= 75:
        return (
            "Recommended angle: lead with completing the immediate task, then propose a lightweight "
            "automation pilot. Frame as: 'I can handle this manually while building you a system "
            "that reduces this work over time.'"
        )
    elif automation_score >= 50:
        return (
            "Recommended angle: offer to start with a workflow audit or diagnostic to identify "
            "automation opportunities before proposing a full build. Frame as: 'Before jumping in, "
            "I'd like to map your current process to find where we can save the most time.'"
        )
    else:
        return (
            "Recommended angle: position around operational reliability and quality execution. "
            "Mention structured processes as a differentiator, but don't over-promise automation. "
            "Frame as: 'I bring structured processes to every engagement so your work is always "
            "documented and repeatable.'"
        )
