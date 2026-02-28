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
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Versioning ────────────────────────────────────────────────────────────────
SCHEMA_VERSION: str = "mvp.v0.2.1"
TAXONOMY_VERSION: str = "v1.4"
CONFIG_VERSION: str = "1"          # bump when prompt/model defaults change
OUTPUT_MODE: str = "coaching_first_2s1e"

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_MODEL_DEFAULT: str = "gpt-4o"
OPENAI_MAX_TOKENS: int = 8192
OPENAI_CONNECT_TIMEOUT: float = 10.0
OPENAI_READ_TIMEOUT: float = 90.0
OPENAI_MAX_CONCURRENCY: int = 3     # semaphore cap per process

# ── Retry policy (shared for OpenAI + Airtable) ───────────────────────────────
RETRY_ATTEMPTS: int = 4
RETRY_BASE_DELAY: float = 1.0       # seconds
RETRY_MAX_DELAY: float = 30.0

# ── Transcript limits ─────────────────────────────────────────────────────────
TRANSCRIPT_MAX_WORDS: int = 10_000
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
MVP_SCHEMA_PATH = SCHEMAS_DIR / "mvp_v0_2_1.json"

# ── Pattern ordering (must be stable) ────────────────────────────────────────
PATTERN_ORDER = [
    "agenda_clarity",
    "objective_signaling",
    "turn_allocation",
    "facilitative_inclusion",
    "decision_closure",
    "owner_timeframe_specification",
    "summary_checkback",
    "question_quality",
    "listener_response_quality",
    "conversational_balance",
]
