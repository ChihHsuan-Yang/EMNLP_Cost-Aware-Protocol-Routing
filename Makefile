# Offline reproduction targets for the protocol-routing release.
#
# Every target here runs on a laptop CPU. None of them calls a model endpoint,
# needs a GPU, or touches the network beyond `make setup` installing packages.
#
# Reproducing the paper's aggregate tables needs two inputs you supply:
#   MATCHED_DIR   directory of per-problem matched-outcome CSVs (one per setting)
#   REFERENCE_DIR directory of the camera-ready ancillary CSVs to diff against
# Both default to nothing; the table/figure targets tell you what to pass.

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip

# Where `make setup` builds its environment.
VENV ?= .venv

# Every other target runs through the venv when one exists, so that `make test`
# after `make setup` uses what setup just installed rather than whatever
# interpreter happens to be on PATH. Falls back to $(PYTHON) if there is no
# venv (for CI, or for `make setup VENV=`).
RUN_ABS := $(shell [ -x "$(CURDIR)/$(VENV)/bin/python" ] && echo "$(CURDIR)/$(VENV)/bin/python" || echo "$(PYTHON)")
RUN := $(shell [ -x "$(VENV)/bin/python" ] && echo "$(VENV)/bin/python" || echo "$(PYTHON)")

MATCHED_DIR   ?=
REFERENCE_DIR ?=
OUTPUT_DIR    ?= outputs
FIXTURE_DIR   := tests/fixtures

.DEFAULT_GOAL := help
.PHONY: help setup test smoke data validate-data reproduce-tables reproduce-figures lint clean

help:
	@echo "protocol-routing -- offline reproduction targets"
	@echo
	@echo "  make setup              install the package and test extras"
	@echo "  make test               run the full pytest suite (fixture only)"
	@echo "  make smoke              fast end-to-end check on the tiny fixture"
	@echo "  make lint               ruff check (skipped with a notice if absent)"
	@echo "  make reproduce-tables   MATCHED_DIR=... [REFERENCE_DIR=...]"
	@echo "  make reproduce-figures  MATCHED_DIR=..."
	@echo
	@echo "OFFLINE: all of the above. Protocol EXECUTION is inference-requiring"
	@echo "and is NOT provided here; see README 'Inference-requiring steps'."

# Creates a local virtual environment and installs into it. Installing into
# whatever interpreter happens to be on PATH would put 20+ dependencies into a
# reader's global or conda environment without asking -- a rude thing for a
# research artifact to do on its first command.
#
# Set VENV= (empty) to install into the current interpreter instead:
#   make setup VENV=

setup:
	@if [ -n "$(VENV)" ]; then \
		echo "== creating $(VENV) =="; \
		$(PYTHON) -m venv $(VENV); \
		$(VENV)/bin/python -m pip install --quiet --upgrade pip; \
		$(VENV)/bin/python -m pip install -e ".[test]"; \
		echo ""; \
		echo "== setup: OK =="; \
		echo "   activate it with:  source $(VENV)/bin/activate"; \
		echo "   or just run the other targets, which use $(VENV) automatically."; \
	else \
		echo "== installing into the current interpreter (VENV is empty) =="; \
		$(PIP) install -e ".[test]"; \
	fi

test:
	$(RUN) -m pytest tests

# The smoke target must stay fast and fixture-only: no network, no endpoint,
# no large inputs. It is the check a reader runs first.
smoke:
	@echo "== smoke: package imports =="
	$(RUN) -c "import sys; sys.path.insert(0,'src'); import protocol_routing as p; print('protocol_routing', p.__version__)"
	@echo "== smoke: CLI --help =="
	@for s in build_matched_tables train_router evaluate_router analyze_confidence \
	          analyze_protocol_interactions reproduce_paper_tables reproduce_paper_figures; do \
		$(RUN) scripts/$$s.py --help > /dev/null || exit 1; \
		echo "  ok  scripts/$$s.py --help"; \
	done
	@echo "== smoke: aggregate tables from the tiny fixture =="
	$(RUN) scripts/build_matched_tables.py \
		--matched_dir $(FIXTURE_DIR) \
		--output_dir $(OUTPUT_DIR)/smoke \
		--allow_non_paper_settings
	@echo "== smoke: pytest (fixture only) =="
	$(PYTHON) -m pytest tests -q
	@echo "== smoke: OK =="

# ---------------------------------------------------------------------------
# Data: download and validate the released tables.
#
# The per-problem data lives on Hugging Face rather than in git, because it is
# too large to belong in a repository. These two targets are the documented way
# to fetch it and to check what you fetched.
# ---------------------------------------------------------------------------

DATA_DIR ?= data/emnlp_protocol_routing
HF_DATASET ?= AgentsSci/EMNLP_Cost-Aware-Protocol-Routing

data:
	@command -v hf >/dev/null 2>&1 || { \
		echo "ERROR: the 'hf' CLI was not found."; \
		echo "  pip install -U huggingface_hub"; \
		exit 2; \
	}
	hf download $(HF_DATASET) --repo-type dataset --local-dir $(DATA_DIR)
	@echo "== data: downloaded to $(DATA_DIR) =="
	@echo "   next: make validate-data"

validate-data:
	@if [ ! -f "$(DATA_DIR)/validate.py" ]; then \
		echo "ERROR: $(DATA_DIR)/validate.py not found. Run 'make data' first,"; \
		echo "  or set DATA_DIR=/path/to/downloaded/dataset"; \
		exit 2; \
	fi
	@# Deliberately plain python: the validator is stdlib-only by design, so that
	@# it runs for a user who has installed nothing yet.
	cd $(DATA_DIR) && $(RUN_ABS) validate.py


reproduce-tables:
	@if [ -z "$(MATCHED_DIR)" ]; then \
		echo "ERROR: set MATCHED_DIR=/path/to/matched_labels"; \
		echo "  e.g. make reproduce-tables MATCHED_DIR=data/matched_labels REFERENCE_DIR=anc"; \
		exit 2; \
	fi
	$(RUN) scripts/reproduce_paper_tables.py \
		--matched_dir $(MATCHED_DIR) \
		$(if $(REFERENCE_DIR),--reference_dir $(REFERENCE_DIR),) \
		--output_dir $(OUTPUT_DIR)/tables

reproduce-figures:
	@if [ -z "$(MATCHED_DIR)" ]; then \
		echo "ERROR: set MATCHED_DIR=/path/to/matched_labels"; \
		exit 2; \
	fi
	$(RUN) scripts/reproduce_paper_figures.py \
		--matched_dir $(MATCHED_DIR) \
		--output_dir $(OUTPUT_DIR)/figures

lint:
	@if $(PYTHON) -c "import ruff" 2>/dev/null || command -v ruff >/dev/null 2>&1; then \
		ruff check src scripts tests; \
	else \
		echo "ruff not installed; run: $(PIP) install -e '.[lint]'"; \
	fi

clean:
	rm -rf $(OUTPUT_DIR) .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
