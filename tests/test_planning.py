import importlib.util
import json
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def planning(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "project_status", ROOT / "scripts/project_status.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shutil.copytree(ROOT / "docs/baselines", tmp_path / "docs/baselines")
    shutil.copytree(ROOT / "docs/changes", tmp_path / "docs/changes")
    (tmp_path / "docs/management").mkdir()
    shutil.copyfile(ROOT / "docs/management/wbs.toml", tmp_path / "docs/management/wbs.toml")
    plan = tomllib.loads((tmp_path / "docs/management/wbs.toml").read_text(encoding="utf-8"))
    for task in plan["tasks"]:
        for evidence in task.get("evidence", []):
            path = tmp_path / evidence
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture evidence", encoding="utf-8")
    module.ROOT = tmp_path
    return module, tmp_path


def test_current_plan_preserves_old_baselines_and_requires_windows_acceptance(planning):
    module, _ = planning
    plan = module.validate()
    assert plan["plan_version"] == "1.3.0"
    tasks = {t["id"]: t for t in plan["tasks"]}
    assert len(tasks) == 47
    assert tasks["0.6"]["status"] == "blocked"
    assert "0.6" in tasks["3.2"]["depends_on"]
    assert "1.19" in tasks["3.2"]["depends_on"]
    assert "1.19" in tasks["4.1"]["depends_on"]
    assert all(tasks[f"1.{i}"]["status"] == "not_started" for i in range(9, 20))


@pytest.mark.parametrize("version", ["v1.1", "v1.2", "v1.3"])
def test_any_immutable_baseline_change_is_rejected(planning, version):
    module, root = planning
    path = root / "docs/baselines" / version / "wbs.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# unauthorized mutation\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="immutable"):
        module.validate()


def test_original_design_manifest_is_checked(planning):
    module, root = planning
    manifest = json.loads((root / "docs/baselines/v1.0/manifest.json").read_text(encoding="utf-8"))
    name = next(iter(manifest["sha256"]))
    path = root / "docs/baselines/v1.0" / name
    path.write_text(path.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable design"):
        module.validate()


def test_missing_change_request_is_rejected(planning):
    module, root = planning
    (root / "docs/changes/CR-0002.md").unlink()
    with pytest.raises(ValueError, match="change request"):
        module.validate()


def test_scope_change_without_new_baseline_is_rejected(planning):
    module, root = planning
    path = root / "docs/management/wbs.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'name = "개발/운영 환경 경계·API 인증·준비 상태"', 'name = "silently changed scope"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="baseline scope"):
        module.validate()
