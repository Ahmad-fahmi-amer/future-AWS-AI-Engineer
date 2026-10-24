#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
PYTHON="${NOVAMART_PYTHON:-.venv312/bin/python}"
mkdir -p evidence
"$PYTHON" -m compileall -q src infrastructure config.py
sha256sum -c evidence/official-tests.sha256
"$PYTHON" -m unittest discover -s tests -p test_local.py -v > evidence/local-tests.log 2>&1
cat evidence/local-tests.log
# The supplied grader prints failure checks but can exit 0. Check its content too.
"$PYTHON" tests/test_agent.py task2 > evidence/task2.log 2>&1
cat evidence/task2.log
if rg -q 'FAIL|Could not import' evidence/task2.log; then exit 1; fi
