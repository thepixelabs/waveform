.PHONY: install lint format format-check test check clean

# Install all dependencies (runtime + dev)
install:
	pip install -r requirements.txt -r requirements-dev.txt

# Run ruff linter
lint:
	ruff check .

# Auto-format code
format:
	ruff format .

# Check formatting without modifying files
format-check:
	ruff format --check .

# Run test suite
test:
	python -m pytest tests/ -v

# Run all checks (CI equivalent)
check: lint format-check test

# Remove caches and build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
