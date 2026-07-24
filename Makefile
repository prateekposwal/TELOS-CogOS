.PHONY: test test-core test-fallback clean lint

test: test-core test-fallback

test-core:
	python3 -m pytest tests/core/ -v

test-fallback:
	python3 -m pytest tests/test_latent_cognition.py -v

test-all:
	python3 -m pytest tests/ -v

lint:
	python3 -m py_compile telos/core/runtime.py telos/core/simulation.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
