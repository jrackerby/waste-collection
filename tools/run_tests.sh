#!/usr/bin/env bash
# Run the suite. MUST be run from tests/ -- see tests/pytest.ini for why the
# repo root cannot be in pytest's collection tree.
set -euo pipefail
cd "$(dirname "$0")/../tests"
exec python -m pytest "$@"
