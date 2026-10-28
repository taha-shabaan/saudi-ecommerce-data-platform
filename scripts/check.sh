#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "🔍 Running Ruff Linter & Formatter Check"
echo "========================================"
.venv/bin/ruff check src/ tests/

echo ""
echo "========================================"
echo "🧠 Running Mypy Static Type Checking"
echo "========================================"
.venv/bin/mypy src/ tests/

echo ""
echo "========================================"
echo "🧪 Running Pytest Unit Test Suite"
echo "========================================"
.venv/bin/pytest tests/unit/ -v

echo ""
echo "✅ All Quality & Architecture Checks Passed!"

