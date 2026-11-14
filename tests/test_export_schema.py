"""tools/export_schema.py: JSON Schema for skill.yaml derived from the loader."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import export_schema  # noqa: E402


def test_schema_from_loader_has_core_and_amendment_fields():
    s = export_schema.build_schema()
    assert s["x-ghost-source"] == "gitd.skills.engine.loader"
    for key in ("name", "version", "actions", "fingerprint", "license", "generated_with", "side_effects", "tos_risk"):
        assert key in s["properties"], key
    assert s["required"] == ["name", "version", "actions", "license", "generated_with"]
    assert s["$defs"]["ActionDef"]["required"] == ["name", "ref_prompt", "steps", "end_state_validator"]
    assert "skill_dir" not in s["properties"]
    assert "hard" in s["properties"]["skill_class"]["enum"]


def test_stub_matches_loader_shape():
    real, stub = export_schema.build_from_loader(), export_schema.build_stub()
    assert stub["x-ghost-source"] == "stub"
    assert set(stub["properties"]) == set(real["properties"])
    assert set(stub["$defs"]) == set(real["$defs"])
    assert stub["required"] == real["required"]


def test_committed_site_schema_is_current():
    committed = json.loads((REPO / "site/src/lib/hub/skill.schema.json").read_text())
    assert committed == export_schema.build_schema(), "re-run: python3 tools/export_schema.py -o site/src/lib/hub/skill.schema.json"


def test_tiktok_skill_shape_against_schema_keys():
    path = REPO / "skillhub/ghost/tiktok/skill.yaml"
    if not path.exists():  # pre-migration layout
        path = REPO / "gitd/skills/tiktok/skill.yaml"
    raw = yaml.safe_load(path.read_text())
    props = export_schema.build_schema()["properties"]
    unknown = set(raw) - set(props)
    assert not unknown, f"skill.yaml keys missing from schema: {unknown}"


def test_cli_writes_file(tmp_path):
    out = tmp_path / "s.json"
    subprocess.run([sys.executable, str(REPO / "tools/export_schema.py"), "-o", str(out)], check=True)
    assert json.loads(out.read_text())["$id"].endswith("/skills/schema/v2.json")
