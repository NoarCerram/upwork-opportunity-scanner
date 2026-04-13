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
# "automation" key kept for DB column compatibility — it now stores "niche fit" score.
WEIGHTS = {
    "relevance": 0.45,
    "automation": 0.30,   # stores specialization / niche-fit score
    "win_likelihood": 0.25,
}

# Score display thresholds
SCORE_HIGH = 75
SCORE_MODERATE = 50

# ── Niche: 3D Product Visual Specialist ──────────────────────────────────────
# These replace the old automation signals entirely.

NICHE_SIGNALS = {
    # Primary keywords — exact phrases from active job listings (highest match weight)
    "primary_keywords": [
        "3d product render",
        "product mockup",
        "3d product modeling",
        "product visualization",
        "3d ecommerce render",
        "product listing images",
        "3d product design",
        "ecommerce product render",
        "product photography 3d",
        "ai product visualization",
        "3d product mockup",
        "product render amazon",
        "product render shopify",
        "3d lifestyle render",
        "product infographic 3d",
    ],

    # Secondary keywords — supporting phrases in descriptions (moderate weight)
    "secondary_keywords": [
        "ecommerce visuals",
        "listing optimization visuals",
        "amazon a+ content design",
        "product page mockups",
        "social media product ads",
        "product ad creatives",
        "dtc product visuals",
        "product photography replacement",
        "listing image designer",
        "product visual designer",
        "3d packaging mockup",
        "360 product render",
        "product comparison visual",
    ],

    # HOT signals — flag job as high-priority immediately
    "hot_signals": [
        "need product renders for amazon listing",
        "replace product photos with 3d",
        "ecommerce product visualization",
        "make my product look premium",
        "360 product views",
        "lifestyle product shots",
        "ai-assisted",
        "fast turnaround",
        "listing image",
        "product render",
        "amazon listing",
        "shopify product",
        "product photos suck",
        "better listing images",
        "7-9 images",
        "a+ content",
        "hero shot",
        "lifestyle image",
    ],

    # Ecommerce platform/context signals (confirm the right buyer profile)
    "ecommerce_context": [
        "amazon",
        "shopify",
        "listing",
        "product page",
        "ecommerce",
        "e-commerce",
        "dtc",
        "direct to consumer",
        "fba",
        "fulfillment by amazon",
        "a+ content",
        "asin",
        "sku",
        "product launch",
        "brand store",
    ],
}

# Negative keywords — exclude to avoid generic / off-niche work
NICHE_NEGATIVE_KEYWORDS = [
    "logo design",
    "character modeling",
    "architectural render",
    "game asset",
    "nft art",
    "interior design",
    "game character",
    "architecture visualization",
    "floor plan",
    "building render",
    "nft",
    "character animation",
    "2d illustration",
    "cartoon",
    "explainer video",
]

# ── Win-likelihood thresholds ─────────────────────────────────────────────────
# Raised fixed minimum to $200 and hourly to $100 to match niche pricing.

WIN_THRESHOLDS = {
    "fresh_hours_great": 6,
    "fresh_hours_good": 24,
    "fresh_hours_ok": 72,
    "good_budget_fixed_min": 200,    # $200+ fixed (filters out $15/hr data entry)
    "good_budget_hourly_min": 100,   # $100+ hourly
}

# ── Default search themes seeded on first run ────────────────────────────────

DEFAULT_THEMES = [
    {
        "name": "3D Product Renders – Amazon & Shopify",
        "query_text": "3D product render amazon shopify listing",
        "include_keywords_json": '["3d product render", "product render", "product mockup", "listing images", "amazon", "shopify"]',
        "exclude_keywords_json": '["logo design", "character modeling", "architectural render", "game asset", "nft", "interior design"]',
        "desired_skills_json": '["3D Rendering", "Product Visualization", "Blender", "Cinema 4D", "Keyshot", "Product Mockup"]',
        "min_budget": 200,
        "contract_type": "any",
    },
    {
        "name": "Product Visualization & Mockups",
        "query_text": "product visualization mockup ecommerce visuals",
        "include_keywords_json": '["product visualization", "product mockup", "ecommerce visuals", "product photography replacement", "3d mockup"]',
        "exclude_keywords_json": '["logo design", "character modeling", "architectural render", "game asset", "nft", "interior design"]',
        "desired_skills_json": '["Product Visualization", "3D Modeling", "Blender", "Adobe Dimension", "Product Mockup"]',
        "min_budget": 200,
        "contract_type": "any",
    },
    {
        "name": "Amazon A+ Content & Listing Images",
        "query_text": "amazon listing images A+ content product images",
        "include_keywords_json": '["amazon", "listing images", "a+ content", "product images", "ecommerce", "listing optimization"]',
        "exclude_keywords_json": '["logo design", "character modeling", "architectural render", "game asset", "nft"]',
        "desired_skills_json": '["Amazon Listing Optimization", "Product Photography", "3D Rendering", "Graphic Design", "A+ Content"]',
        "min_budget": 150,
        "contract_type": "any",
    },
    {
        "name": "AI Product Visuals & Fast Turnaround",
        "query_text": "AI product visuals 3d render fast turnaround ecommerce",
        "include_keywords_json": '["ai product", "ai-assisted", "product visuals", "fast turnaround", "3d render", "product image"]',
        "exclude_keywords_json": '["logo design", "character modeling", "architectural render", "game asset", "nft", "interior design"]',
        "desired_skills_json": '["AI Image Generation", "Midjourney", "Product Visualization", "3D Rendering", "Blender"]',
        "min_budget": 150,
        "contract_type": "any",
    },
    {
        "name": "Lifestyle & Social Media Product Ads",
        "query_text": "lifestyle product render social media ad mockup DTC brand",
        "include_keywords_json": '["lifestyle", "product ads", "social media", "dtc", "brand", "product mockup", "ad creative"]',
        "exclude_keywords_json": '["logo design", "character modeling", "architectural render", "game asset", "nft", "interior design"]',
        "desired_skills_json": '["Product Mockup", "Social Media Design", "3D Rendering", "Lifestyle Photography", "Ad Creative"]',
        "min_budget": 150,
        "contract_type": "any",
    },
]
