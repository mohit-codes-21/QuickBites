# QuickBites Module B Makefile
# Usage:
#   make run     -> create venv (if needed), install deps, run Flask app
#   make install -> create venv (if needed), install deps
#   make venv    -> create venv only (if missing)

PYTHON ?= python
VENV_DIR := .venv

ifeq ($(OS),Windows_NT)
VENV_PY := $(VENV_DIR)/Scripts/python.exe
else
VENV_PY := $(VENV_DIR)/bin/python
endif

REQ_FILE := app/requirements.txt
APP_FILE := app/app.py

ifeq ("$(wildcard $(VENV_PY))","")
CREATE_VENV_CMD := $(PYTHON) -m venv $(VENV_DIR)
else
CREATE_VENV_CMD := echo "Virtual environment already exists at $(VENV_DIR)"
endif

.PHONY: help venv install run report-latex clean

help:
	@echo "Targets:"
	@echo "  make venv    - Create virtual environment if it does not exist"
	@echo "  make install - Install Python dependencies into the venv"
	@echo "  make run     - Install deps (if needed) and run app/app.py"
	@echo "  make report-latex - Build report/assignment_report.pdf from report/assignment_report.tex"
	@echo "  make clean   - Remove virtual environment"

venv:
	@$(CREATE_VENV_CMD)

install: venv
	@$(VENV_PY) -m pip install --upgrade pip
	@$(VENV_PY) -m pip install -r $(REQ_FILE)

run: install
	@$(VENV_PY) $(APP_FILE)

report-latex:
	@command -v tectonic >/dev/null 2>&1 || { echo "tectonic not found. Install it with: brew install tectonic"; exit 1; }
	@tectonic --outdir report report/assignment_report.tex

clean:
	@$(VENV_PY) -c "import shutil, pathlib; p=pathlib.Path('$(VENV_DIR)'); shutil.rmtree(p, ignore_errors=True); print('Removed', p)"