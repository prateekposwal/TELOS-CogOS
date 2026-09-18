# TELOS Makefile
#
# Prefer the local .venv interpreter (has numpy/pytest); fall back to
# whatever `python3` is on PATH. Never hardcode a bare interpreter for
# project targets — see the sys.executable pattern in telos/core/actions/executor.py.

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
export PYTHONPATH := .

.PHONY: test test-core test-fallback test-all lint run audit coverage health check check-fast capabilities memory-consume clean

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

coverage:
	$(PYTHON) telos/tools/branch_coverage.py --scope core --top 20 \
		--json telos/audit/branch_coverage.json

health:
	$(PYTHON) telos/tools/cognitive_health.py --cycles 150 --ci

# Capability gates (Phase 0-3): the tool channel, memory retrieval, the
# learning curve, and the scorecard itself. Each exits nonzero on a miss.
capabilities:
	$(PYTHON) telos/tools/tool_channel_scan.py --ci
	$(PYTHON) telos/tools/memory_eval.py --ci
	$(PYTHON) telos/tools/learning_curve.py --ci
	$(PYTHON) telos/tools/capability_scorecard.py --ci

# Sustained memory measurement (slow: drives a real pipeline for many cycles).
# Separate from `capabilities` so the fast gate stays fast; CI runs it.
memory-consume:
	$(PYTHON) telos/tools/memory_consumption_run.py --cycles 120 --ci

# Release gate (periodic / CI): full suite + every invariant gate at full
# duration. ~3 min. Use check-fast for a per-commit loop.
check:
	$(PYTHON) -m pytest tests/ -q
	$(PYTHON) telos/tools/self_audit.py
	$(PYTHON) telos/tools/falsify_axioms.py --ci
	$(PYTHON) telos/tools/theorem_audit.py --cycles 20 --ci
	$(PYTHON) telos/tools/cognitive_health.py --cycles 150 --ci
	$(MAKE) capabilities

# Per-commit gate: same invariant gates at reduced simulation duration.
check-fast:
	$(PYTHON) -m pytest tests/ -q
	$(PYTHON) telos/tools/self_audit.py
	$(PYTHON) telos/tools/falsify_axioms.py --ci
	$(PYTHON) telos/tools/theorem_audit.py --cycles 10 --ci
	$(PYTHON) telos/tools/cognitive_health.py --cycles 40 --ci

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
