def generate_proposal(job, scores, hypothesis_text=""):
    title = (job.get("title") or "this project").lower().strip()
    automation_score = scores.get("automation_score", 0)
    win_score = scores.get("win_likelihood_score", 0)

    try:
        auto_exp = scores.get("explanation", {}).get("automation", {})
        struct_matched = auto_exp.get("structured_input", {}).get("matched", [])
        pen_matched = auto_exp.get("penalty", {}).get("matched", [])
    except Exception:
        struct_matched = []
        pen_matched = []

    # ── Diagnosis ──────────────────────────────────────────────────────────────
    if struct_matched:
        tools = ", ".join(struct_matched[:2])
        diagnosis = (
            f"The client needs ongoing support with {title}, working primarily in {tools}. "
            "The core challenge appears to be recurring manual work that needs consistent, reliable execution."
        )
    else:
        diagnosis = (
            f"The client needs reliable support with {title}. "
            "The core challenge appears to be recurring operational work that needs consistent "
            "execution and clear documentation."
        )

    # ── Positioning ────────────────────────────────────────────────────────────
    if automation_score >= 70:
        positioning = (
            "Position as an operator who executes tasks and builds lightweight systems to make "
            "them faster and more reliable over time. Differentiate from pure VAs by offering "
            "process improvement alongside execution."
        )
    elif automation_score >= 45:
        positioning = (
            "Position as a structured operator who documents processes and identifies efficiency "
            "improvements. Offer a short discovery phase to map the workflow before execution."
        )
    else:
        positioning = (
            "Position as a reliable, detail-oriented operator with relevant domain experience. "
            "Focus on quality, turnaround time, and clear communication as differentiators."
        )

    # ── Opening Paragraph ──────────────────────────────────────────────────────
    if automation_score >= 70:
        opening = (
            f"I've handled exactly this kind of work before — where the core need is reliable "
            f"execution, but the underlying workflow has room to become faster and more systematic. "
            f"I'd take care of the immediate tasks while also surfacing small, practical improvements "
            f"that reduce your manual workload over time."
        )
    else:
        opening = (
            f"I have direct experience with the type of work you're describing. "
            f"I focus on reliable execution, clear communication, and documented processes "
            f"so nothing falls through the cracks as we work together."
        )

    # ── Soft Upsell ────────────────────────────────────────────────────────────
    if automation_score >= 60:
        upsell = (
            "After the first week or two, I can share a short workflow map showing which parts "
            "of this work could be partially automated — with no obligation to pursue it further "
            "if the manual approach is working well."
        )
    else:
        upsell = ""

    # ── Caution ────────────────────────────────────────────────────────────────
    caution_parts = []
    if pen_matched:
        caution_parts.append(
            f"Bespoke/high-judgment signals detected ({', '.join(pen_matched[:2])}). "
            "Avoid leading with automation — emphasise reliability and expertise instead."
        )
    if win_score < 40:
        caution_parts.append(
            "Low win-likelihood (high competition or weak client signals). "
            "Consider whether Connects are worth spending here."
        )
    caution = " ".join(caution_parts)

    return {
        "diagnosis_text": diagnosis,
        "positioning_text": positioning,
        "opening_paragraph": opening,
        "upsell_text": upsell,
        "caution_text": caution,
    }
