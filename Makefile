# Wikipedia AI Overviews: pipeline entry points.
# Paths: override with WAO_RAW_DIR / WAO_DATA_DIR (see src/wao/config.py).

PY := uv run python -I

# Ignore any other active virtualenv: uv always uses this project's .venv.
unexport VIRTUAL_ENV

# `make all SAMPLE=1`: the whole pipeline on a small synthetic dump in .sample/ (built in P28).
# Never touches the real data or report/.
ifeq ($(SAMPLE),1)
SAMPLE_DIR ?= $(CURDIR)/.sample
export WAO_SAMPLE := 1
export WAO_RAW_DIR := $(SAMPLE_DIR)/raw
export WAO_DATA_DIR := $(SAMPLE_DIR)/data
export WAO_REFERENCE_DIR := $(SAMPLE_DIR)/reference
export WAO_REPORT_DIR := $(SAMPLE_DIR)/report
endif

.PHONY: all check-env progress reference ingest ingest-clickstream ingest-pageviews ingest-features sample build models figures report test test-network lint

all: check-env ingest build models figures report

check-env:
	$(PY) -m wao.check_env

# Progress bar: `make progress JOB=<name> WATCH=1` (speed + ETA). Downloads: clickstream country sql
# pageviews2023 pageviews repair stubs; API jobs: topics (cached responses), revisions (log).
progress:
	@$(PY) -m wao.progress $(or $(JOB),clickstream) $(if $(WATCH),--watch,)

# P01–P03: dump inventories, rollout (Google help page via Wayback), country shares, exposure.
reference:
	$(PY) -m wao.ingest.inventory
	$(PY) -m wao.build.rollout
	$(PY) -m wao.viz.rollout_timeline
	$(PY) -m wao.ingest.country
	$(PY) -m wao.build.exposure
	$(PY) -m wao.viz.exposure_curves

# Stages are filled in by later prompts (ingest P04–P10, build P11–P13, models P16–P25,
# figures P26–P27, report P30).
ingest: check-env ingest-clickstream ingest-pageviews ingest-features

# P05: all clickstream files -> Parquet pairs + per-article aggregates (resumable).
ingest-clickstream: check-env
	$(PY) -m wao.ingest.clickstream_ingest

# P07: daily pageviews (user 2016-01.., automated 2020-05..) for the P06 sample (resumable, ~10 h).
ingest-pageviews: check-env
	$(PY) -m wao.ingest.pageviews --procs 2

# P08: revision histories (stub dumps, 246 GB), the 2023-12-31 text features (API, needs the bot
# password WAO_BOT_USER/WAO_BOT_PASS), Lift Wing topics, infobox lists, HTML check, QA + figure.
ingest-features: check-env
	$(PY) -m wao.ingest.stub_history --procs 4
	$(PY) -m wao.ingest.revisions --procs 4 --interval 0.35
	$(PY) -m wao.ingest.topics
	$(PY) -m wao.ingest.infobox_templates
	$(PY) -m wao.build.features
	$(PY) -m wao.build.infobox_check
	$(PY) -m wao.viz.article_features

# P06: SQL table dumps + 2023 pageview totals -> frame and stratified sample (resumable).
sample: check-env
	$(PY) -m wao.ingest.sql_dumps
	$(PY) -m wao.ingest.pageview_months
	$(PY) -m wao.build.sample

build: sample

models:
	@echo "models: nothing yet (P16–P25)"

figures:
	@echo "figures: nothing yet (P26–P27)"

report:
	@echo "report: nothing yet (P30)"

test:
	uv run pytest -q

# Includes tests that call live Wikimedia endpoints.
test-network:
	WAO_NETWORK_TESTS=1 uv run pytest -q

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
