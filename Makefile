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

.PHONY: all check-env progress reference ingest ingest-clickstream sample build models figures report test test-network lint

all: check-env ingest build models figures report

check-env:
	$(PY) -m wao.check_env

# Progress bar for a running download: `make progress` (JOB=clickstream|country|sql|pageviews2023; WATCH=1 redraws with speed + ETA).
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
ingest: check-env ingest-clickstream

# P05: all clickstream files -> Parquet pairs + per-article aggregates (resumable).
ingest-clickstream: check-env
	$(PY) -m wao.ingest.clickstream_ingest

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
