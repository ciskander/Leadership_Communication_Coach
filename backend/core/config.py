"""
config.py — environment variables and application constants.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Secrets ──────────────────────────────────────────────────────────────────
AIRTABLE_TOKEN: str = os.environ["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID: str = os.environ["AIRTABLE_BASE_ID"]
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")  # optional — only needed when using Claude models
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Versioning ────────────────────────────────────────────────────────────────
SCHEMA_VERSION: str = "mvp.v0.6.0"
TAXONOMY_VERSION: str = "v3.1"
CONFIG_VERSION: str = "1"          # bump when prompt/model defaults change
OUTPUT_MODE: str = "coaching_first_2s1e"
SCORING_OUTPUT_MODE: str = "scoring_only"

# ── Two-stage pipeline ────────────────────────────────────────────────────
EDITOR_ENABLED: bool = False  # Editor is deprecated; Stage 2 coaching call replaces it

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_MODEL_DEFAULT: str = "gpt-5.4"
OPENAI_MAX_TOKENS: int = 16384
OPENAI_CONNECT_TIMEOUT: float = 10.0
OPENAI_READ_TIMEOUT: float = 300.0
OPENAI_MAX_CONCURRENCY: int = 3     # semaphore cap per process

# ── Anthropic ──────────────────────────────────────────────────────────────────
ANTHROPIC_MAX_TOKENS: int = 65536
ANTHROPIC_READ_TIMEOUT: float = 600.0  # Sonnet with thinking on large prompts; extra headroom for rate-limit queuing
ANTHROPIC_READ_TIMEOUT_OPUS: float = 300.0  # Opus with extended thinking needs more headroom
ANTHROPIC_JSON_REPAIR_MODEL: str = os.getenv("ANTHROPIC_JSON_REPAIR_MODEL", "claude-sonnet-4-6")
ANTHROPIC_RETRY_ATTEMPTS: int = 2  # Fewer retries than OpenAI — long timeouts make 4 attempts too slow

# ── Retry policy (shared for OpenAI + Anthropic + Airtable) ───────────────────
RETRY_ATTEMPTS: int = 4
RETRY_BASE_DELAY: float = 1.0       # seconds
RETRY_MAX_DELAY: float = 30.0

# ── Transcript limits ─────────────────────────────────────────────────────────
TRANSCRIPT_MAX_WORDS: int = 50_000
TRANSCRIPT_MIN_CHARS: int = 50

# ── Airtable table names ──────────────────────────────────────────────────────
AT_TABLE_TRANSCRIPTS = "transcripts"
AT_TABLE_RUN_REQUESTS = "run_requests"
AT_TABLE_RUNS = "runs"
AT_TABLE_VALIDATION_ISSUES = "validation_issues"
AT_TABLE_BASELINE_PACKS = "baseline_packs"
AT_TABLE_BASELINE_PACK_ITEMS = "baseline_pack_items"
AT_TABLE_EXPERIMENTS = "experiments"
AT_TABLE_EXPERIMENT_EVENTS = "experiment_events"
AT_TABLE_USERS = "users"
AT_TABLE_CONFIG = "config"

# ── Schema file ───────────────────────────────────────────────────────────────
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
MVP_SCHEMA_PATH = SCHEMAS_DIR / "mvp_v0_6_0.json"

# ── Pattern ordering (must be stable) ────────────────────────────────────────
PATTERN_ORDER = [
    "purposeful_framing",
    "focus_management",
    "disagreement_navigation",
    "trust_and_credibility",
    "resolution_and_alignment",
    "assignment_clarity",
    "question_quality",
    "communication_clarity",
    "feedback_quality",
]
