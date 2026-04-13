def generate_proposal(job, scores, hypothesis_text=""):
    title = (job.get("title") or "this project").lower().strip()
    specialization_score = scores.get("automation_score", 0)
    win_score = scores.get("win_likelihood_score", 0)

    try:
        spec_exp = scores.get("explanation", {}).get("specialization", {})
        primary_matched = spec_exp.get("primary_keywords", {}).get("matched", [])
        hot_matched = spec_exp.get("hot_signals", {}).get("matched", [])
        neg_matched = spec_exp.get("negative_keywords", {}).get("matched", [])
        ec_matched = spec_exp.get("ecommerce_context", {}).get("matched", [])
    except Exception:
        primary_matched = []
        hot_matched = []
        neg_matched = []
        ec_matched = []

    budget_min = float(job.get("budget_min") or job.get("hourly_min") or 0)
    platform = "Amazon" if "amazon" in " ".join(ec_matched).lower() else (
        "Shopify" if "shopify" in " ".join(ec_matched).lower() else "your store"
    )

    # ── Diagnosis ──────────────────────────────────────────────────────────────
    if primary_matched:
        kws = ", ".join(primary_matched[:2])
        diagnosis = (
            f"The client needs professional product visuals for {platform} — "
            f"specifically {kws}. "
            "Their core pain point: current images aren't converting, "
            "and a traditional studio shoot is too slow or expensive."
        )
    elif hot_matched:
        diagnosis = (
            f"The client is looking for high-quality product visuals to improve {platform} performance. "
            "They want images that look premium without the cost of a photography studio. "
            "This is exactly the gap that AI-assisted 3D rendering solves."
        )
    else:
        diagnosis = (
            f"The client needs product visual support for {title}. "
            "Their likely pain point: product images that don't convert, "
            "and a need for professional-looking visuals on a realistic budget."
        )

    # ── Positioning ────────────────────────────────────────────────────────────
    if specialization_score >= 70:
        positioning = (
            "Position as a conversion-focused product visual specialist — not a generic 3D artist. "
            "Your edge: you understand ecommerce buyer psychology and deliver marketing renders, "
            "not just technical models. "
            "Emphasise AI-accelerated workflow = faster delivery + lower cost than studio alternatives."
        )
    elif specialization_score >= 45:
        positioning = (
            "Position as a product visual specialist who bridges the gap between expensive studio photography "
            "and amateur DIY images. "
            "Lead with a single strong example from your portfolio that matches their product category. "
            "Offer a sample render as a low-risk entry point."
        )
    else:
        positioning = (
            "Position as a reliable visual creator with ecommerce experience. "
            "Keep the proposal short — ask one qualifying question to confirm they need 3D renders "
            "specifically, before investing Connects on a potentially off-niche job."
        )

    # ── Opening Paragraph ──────────────────────────────────────────────────────
    if specialization_score >= 70:
        opening = (
            "I specialise in exactly this: conversion-focused product visuals for ecommerce listings. "
            "Using AI-assisted 3D rendering, I can deliver a full image set — hero shots, lifestyle scenes, "
            "infographics — in days, not weeks, and at a fraction of what a studio shoot would cost. "
            "The difference isn't just aesthetics: I build images around what actually makes buyers click Add to Cart."
        )
    elif specialization_score >= 45:
        opening = (
            "I work with ecommerce brands to create product visuals that actually convert — "
            "professional-grade renders and mockups without the studio budget. "
            "I'd love to understand your current images and show you what a 3D visual upgrade would look like for your product."
        )
    else:
        opening = (
            "I create product visuals for ecommerce brands — 3D renders, mockups, and lifestyle images "
            "that work for Amazon listings, Shopify pages, and social ads. "
            "Happy to share relevant examples if this sounds like what you need."
        )

    # ── Soft Upsell ────────────────────────────────────────────────────────────
    if budget_min >= 400 or specialization_score >= 65:
        upsell = (
            "Once we've nailed the core listing images, I can extend the same visual set "
            "into social media ad formats and A+ Content modules — "
            "one shoot, multiple deliverables across all your channels."
        )
    elif specialization_score >= 40:
        upsell = (
            "If the first image set performs well, I can produce additional SKU variations "
            "or seasonal lifestyle scenes from the same base models at a reduced rate."
        )
    else:
        upsell = ""

    # ── Caution ────────────────────────────────────────────────────────────────
    caution_parts = []
    if neg_matched:
        caution_parts.append(
            f"Off-niche signals detected ({', '.join(neg_matched[:2])}). "
            "Verify the job is actually about product visuals before applying — "
            "do not pitch 3D rendering if they want logos or character art."
        )
    if win_score < 40:
        caution_parts.append(
            "Low win-likelihood (high competition or weak client signals). "
            "Consider whether Connects are worth spending here — "
            "prioritise HOT jobs with fresh postings and verified payment."
        )
    if budget_min and budget_min < 150:
        caution_parts.append(
            f"Budget (${budget_min:.0f}) is below the recommended minimum ($200 fixed / $100/hr). "
            "You may want to pass or use this as a portfolio-builder only."
        )
    caution = " ".join(caution_parts)

    return {
        "diagnosis_text": diagnosis,
        "positioning_text": positioning,
        "opening_paragraph": opening,
        "upsell_text": upsell,
        "caution_text": caution,
    }
