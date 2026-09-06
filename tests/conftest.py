"""Stage the PURE modules as an importable package -- and nothing else.

The repo root is the integration (hacs.json content_in_root, because
jrackerby/HA submodules it AS custom_components/waste_collection), and the
directory on disk is `waste-collection`, which is not an importable module
name. So the suite has to stage a package either way.

WHAT IT STAGES IS THE POINT. The package built here gets a BLANK __init__.py
and symlinks to const.py and resolver.py alone -- not the repo's own
__init__.py, which imports `homeassistant.config_entries` and would drag all
of core in behind it.

That is not a workaround, it is the enforcement of the rule resolver.py's
docstring claims: this suite runs with Home Assistant ABSENT, so any
`homeassistant` import that creeps into const.py or resolver.py fails the
whole suite at collection, loudly, on the commit that adds it. household_state
supplies a stub slice of core for the same job; a stub can drift from the real
thing, and no stub exists here to drift.

The real layout, with the real __init__.py against real core, is covered by
validate.yml's `imports` job -- which cannot run on the Python this was
written on. The two jobs together cover both claims; neither covers both.
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every module that must stay importable without Home Assistant. Adding one
# here is a claim that it is pure, and the suite is what tests the claim.
PURE_MODULES = ("const.py", "resolver.py")

_stage = Path(tempfile.mkdtemp(prefix="waste_collection_test_"))
atexit.register(shutil.rmtree, _stage, True)

_pkg = _stage / "waste_collection"
_pkg.mkdir()
(_pkg / "__init__.py").write_text(
    "# Blank on purpose -- see tests/conftest.py. The real __init__.py imports\n"
    "# homeassistant and is exercised by validate.yml's `imports` job instead.\n"
)
for _name in PURE_MODULES:
    source = ROOT / _name
    assert source.is_file(), f"PURE_MODULES names {_name}, which does not exist"
    (_pkg / _name).symlink_to(source)

sys.path.insert(0, str(_stage))
sys.path.insert(0, str(Path(__file__).resolve().parent))
