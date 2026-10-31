"""Project paths and constants.

Paths come from environment variables so nothing machine-specific is hard-coded
in the pipeline. The defaults match the author's setup (see DATA.md).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = Path(os.environ.get("WAO_RAW_DIR", "/Volumes/Drive3/data/wikimedia"))
DATA_DIR = Path(os.environ.get("WAO_DATA_DIR", "/Volumes/Drive3/wao"))

# Contact info for the Wikimedia User-Agent (email or URL). No default on purpose.
CONTACT = os.environ.get("WAO_CONTACT", "").strip()
# Wikimedia bot password (Special:BotPasswords): logged-in API limits are per account, not per IP
BOT_USER = os.environ.get("WAO_BOT_USER", "").strip()
BOT_PASS = os.environ.get("WAO_BOT_PASS", "").strip()

CLICKSTREAM_DIR = RAW_DIR / "clickstream"
PAGEVIEW_DIR = RAW_DIR / "pageview_complete"
WIKIDATA_DIR = RAW_DIR / "wikidata"
COUNTRY_DIR = RAW_DIR / "country"

PARQUET_DIR = DATA_DIR / "parquet"
PANEL_DIR = DATA_DIR / "panels"
MODEL_DIR = DATA_DIR / "models"
CACHE_DIR = DATA_DIR / "cache"
DUCKDB_PATH = DATA_DIR / "wao.duckdb"
# DuckDB spill space: point WAO_TMP_DIR at a fast internal disk for the big joins.
TMP_DIR = Path(os.environ.get("WAO_TMP_DIR", DATA_DIR / "tmp"))

# Overridable so the sample pipeline (make all SAMPLE=1) never touches the real outputs.
REFERENCE_DIR = Path(os.environ.get("WAO_REFERENCE_DIR", REPO_ROOT / "data" / "reference"))
REPORT_DIR = Path(os.environ.get("WAO_REPORT_DIR", REPO_ROOT / "report"))
FIGURE_DIR = REPORT_DIR / "figures"

# Sample mode: synthetic data, fewer bootstrap replicates (CI path).
SAMPLE = os.environ.get("WAO_SAMPLE", "") == "1"

# Provisional language set (clickstream languages); finalised in P03.
LANGS = ("en", "de", "fr", "es", "it", "pl", "pt", "ja", "ru", "zh", "fa")

# Key dates (verified against primary sources in P02).
CHATGPT_RELEASE = date(2022, 11, 30)
SGE_LABS_US = date(2023, 5, 10)
AIO_US_LAUNCH = date(2024, 5, 14)
PRE_PERIOD_END = date(2024, 4, 30)  # last day of the headline pre-period (blinding rule)

# Wikimedia endpoints
AQS_BASE = "https://wikimedia.org/api/rest_v1/metrics"
DUMPS_BASE = "https://dumps.wikimedia.org/other"
