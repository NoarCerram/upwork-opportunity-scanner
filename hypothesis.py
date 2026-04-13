def _detect_job_type(spec_exp, job):
    """Classify the job into a product visual sub-category."""
    all_matched = []
    for dim in ("primary_keywords", "secondary_keywords", "hot_signals", "ecommerce_context"):
        all_matched += spec_exp.get(dim, {}).get("matched", [])
    combined = " ".join(all_matched).lower()

    title = (job.get("title") or "").lower()
    desc = (job.get("description_clean") or job.get("description_raw") or "").lower()
    text = combined + " " + title + " " + desc

    if any(x in text for x in ["a+ content", "a+content", "amazon listing", "product render amazon", "amazon"]):
        return "Amazon listing visual kit"
    if any(x in text for x in ["shopify", "product page", "product render shopify"]):
        return "Shopify product page visual"
    if any(x in text for x in ["social media", "ad creative", "product ad", "dtc"]):
        return "Social media / DTC ad creative"
    if any(x in text for x in ["lifestyle", "lifestyle render", "lifestyle image"]):
        return "Lifestyle product render"
    if any(x in text for x in ["360", "360 product", "360 render"]):
        return "360° product render"
    if any(x in text for x in ["packaging", "3d packaging", "box mockup"]):
        return "Packaging / box mockup"
    if any(x in text for x in ["mockup", "product mockup", "3d mockup"]):
        return "Product mockup set"
    return "product visual project"


def generate_hypothesis(job, scores):
    try:
        spec_exp = scores.get("explanation", {}).get("specialization", {})
    except Exception:
        spec_exp = {}

    specialization_score = scores.get("automation_score", 0)
    job_type = _detect_job_type(spec_exp, job)

    primary_matched = spec_exp.get("primary_keywords", {}).get("matched", [])
    hot_matched = spec_exp.get("hot_signals", {}).get("matched", [])
    ec_matched = spec_exp.get("ecommerce_context", {}).get("matched", [])
    neg_matched = spec_exp.get("negative_keywords", {}).get("matched", [])

    parts = [f"This looks like a {job_type} opportunity."]

    if ec_matched:
        platforms = ", ".join(ec_matched[:3])
        parts.append(f"Platform context: {platforms}.")

    if primary_matched:
        kws = ", ".join(primary_matched[:3])
        parts.append(f"Strong niche match — primary keywords found: {kws}.")

    if hot_matched:
        sigs = ", ".join(hot_matched[:3])
        parts.append(f"Buyer-intent signals detected: {sigs}.")

    if neg_matched:
        parts.append(
            f"Off-niche signals present ({', '.join(neg_matched[:2])}). "
            "Confirm the job is product-visual focused before applying."
        )

    if specialization_score >= 75:
        parts.append(
            "HIGH niche fit: the job clearly targets professional product visuals for ecommerce — "
            "your AI-accelerated render workflow is a direct match for this buyer's pain point."
        )
    elif specialization_score >= 50:
        parts.append(
            "MEDIUM niche fit: the job has product visual elements but may include adjacent work. "
            "Lead with your listing-image expertise and confirm scope in the discovery call."
        )
    else:
        parts.append(
            "LOW niche fit: limited product visual signals. "
            "Consider whether this is worth the Connects — the brief may be too generic or off-niche."
        )

    return " ".join(parts)


def generate_offer_angle(job, scores):
    specialization_score = scores.get("automation_score", 0)

    budget_min = float(job.get("budget_min") or job.get("hourly_min") or 0)

    if specialization_score >= 75:
        return (
            "Recommended angle: lead with your Amazon/Shopify listing visual kit offer. "
            "Frame as: 'I specialise in conversion-focused product visuals — not just pretty renders, "
            "but images engineered to make buyers click Add to Cart. "
            "I can deliver a full 7-image listing kit using AI-accelerated rendering "
            "in a fraction of the time and cost of a studio shoot.'"
        )
    elif specialization_score >= 50:
        if budget_min >= 200:
            return (
                "Recommended angle: open with a focused discovery question about their current images, "
                "then pitch the listing visual kit. Frame as: 'What are your current product images costing you "
                "in lost conversions? I can show you what professional 3D visuals would look like for your SKU "
                "before you commit to anything.'"
            )
        else:
            return (
                "Recommended angle: position as a fast, affordable alternative to studio photography. "
                "Frame as: 'I can get you professional-grade product images without the $2k photography shoot — "
                "AI-assisted 3D rendering means fast turnaround at a fraction of the traditional cost.'"
            )
    else:
        return (
            "Recommended angle: if applying, keep it brief. "
            "Ask one qualifying question to confirm they need product visuals specifically, "
            "then offer a quick sample render of their product before committing to a full project."
        )
