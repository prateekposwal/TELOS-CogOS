# TELOS Makefile
#
# Prefer the local .venv interpreter (has numpy/pytest); fall back to
# whatever `python3` is on PATH. Never hardcode a bare interpreter for
# project targets — see the sys.executable pattern in telos/core/actions/executor.py.

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
export PYTHONPATH := .

.PHONY: test test-core test-fallback test-all lint run audit clean

test: test-core test-fallback

test-core:
	$(PYTHON) -m pytest tests/core/ -v

test-fallback:
	$(PYTHON) -m pytest tests/test_latent_cognition.py -v

test-all:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m py_compile telos/core/runtime.py telos/core/simulation/__init__.py telos/core/simulation/engine.py telos/core/simulation/options.py telos/core/actions/executor.py

run:
	$(PYTHON) telos_task.py

audit:
	$(PYTHON) telos/tools/self_audit.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
