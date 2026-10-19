"""Validate plan baselines and render the repository WBS without external services."""

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"done": "완료", "in_progress": "진행", "blocked": "차단", "not_started": "미착수"}
PROTECTED = (
    "id",
    "phase",
    "name",
    "owner",
    "depends_on",
    "baseline_start",
    "duration",
    "acceptance",
)


def validate():
    current = tomllib.loads((ROOT / "docs/management/wbs.toml").read_text(encoding="utf-8"))
    baselines = {
        "1.1.0": (
            "v1.1",
            "6bf23d295e53ae3ffa2bf74c60deacf5e2c695b260940324f050e5ffa91c0bf0",
            "CR-0001",
        ),
        "1.2.0": (
            "v1.2",
            "597770ebc13ec7de50a86354e90a16305e8e43092dfe5d188f88f689d78a4d35",
            "CR-0002",
        ),
    }
    baselines["1.3.0"] = (
        "v1.3",
        "3414ae2e001899c8b86e1b6c25b1b57238ca683b50d0320d0f0c2c914555b147",
        "CR-0003",
    )
    baselines["1.4.0"] = (
        "v1.4",
        "f47636165c88bdeb6d76df943bf9853d89398805be99cedaa503e78033baf20d",
        "CR-0004",
    )
    known = {}
    for version, (directory, digest, change) in baselines.items():
        baseline_path = ROOT / "docs/baselines" / directory / "wbs.toml"
        if hashlib.sha256(baseline_path.read_bytes()).hexdigest() != digest:
            raise ValueError("immutable WBS baseline changed")
        if (baseline_path.parent / "wbs.sha256").read_text(encoding="utf-8").strip() != digest:
            raise ValueError("immutable baseline checksum record changed")
        if not (ROOT / "docs/changes" / f"{change}.md").is_file():
            raise ValueError("baseline requires registered change request")
        known[version] = tomllib.loads(baseline_path.read_text(encoding="utf-8"))
        if known[version]["plan_version"] != version:
            raise ValueError("baseline version mismatch")
    if current["plan_version"] not in known:
        raise ValueError("plan version requires a new baseline and change request")
    baseline = known[current["plan_version"]]
    for directory in ("v1.0", "v1.4"):
        manifest_path = ROOT / "docs/baselines" / directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, digest in manifest["sha256"].items():
            content = (manifest_path.parent / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"immutable design baseline changed: {directory}/{name}")
    tasks = {task["id"]: task for task in current["tasks"]}
    if len(tasks) != len(current["tasks"]):
        raise ValueError("duplicate WBS ID")
    original = {task["id"]: task for task in baseline["tasks"]}
    if tasks.keys() != original.keys():
        raise ValueError("WBS membership requires a versioned change request")
    visited, active = set(), set()

    def visit(identifier):
        if identifier in active:
            raise ValueError("cyclic WBS dependencies")
        if identifier in visited:
            return
        active.add(identifier)
        task = tasks[identifier]
        if any(task[field] != original[identifier][field] for field in PROTECTED):
            raise ValueError(f"baseline scope/schedule changed without new version: {identifier}")
        if task["status"] not in LABELS:
            raise ValueError(f"unknown status: {identifier}")
        if task["duration"] <= 0 or task["baseline_start"] < 0:
            raise ValueError(f"invalid estimate: {identifier}")
        for dependency in task["depends_on"]:
            if dependency not in tasks:
                raise ValueError(f"missing dependency: {dependency}")
            visit(dependency)
            parent = tasks[dependency]
            if task["baseline_start"] < parent["baseline_start"] + parent["duration"]:
                raise ValueError(f"baseline dependency schedule violation: {identifier}")
            if task["status"] == "done" and parent["status"] != "done":
                raise ValueError(f"cannot finish before dependency: {identifier}")
        if task["status"] == "done":
            if not task.get("actual_finish") or not task.get("evidence"):
                raise ValueError(f"completion requires actual date and evidence: {identifier}")
        if task["status"] == "blocked" and not task.get("blocker"):
            raise ValueError(f"blocked task requires reason: {identifier}")
        for evidence in task.get("evidence", []):
            if not (ROOT / evidence).is_file():
                raise ValueError(f"missing evidence: {evidence}")
        active.remove(identifier)
        visited.add(identifier)

    for identifier in tasks:
        visit(identifier)
    return current


def render(plan):
    tasks = plan["tasks"]
    lines = [
        "# WBS 진행 현황",
        "",
        f"계획 버전 **{plan['plan_version']}** · 기준일 {plan['baseline_date']} (한국 시간) · "
        f"실적 갱신 {plan['updated_on']}",
        "",
        "이 파일은 `docs/management/wbs.toml`에서 생성합니다. "
        "`uv run --frozen python scripts/project_status.py --write`로 갱신하고 "
        "Git에 함께 커밋합니다.",
        "",
        "D+n은 승인된 일정 기준점 이후 계획 작업일입니다. "
        "의존성 기반 초안 추정이며 "
        "달력 마감일·자동 작업 예약이 아닙니다. 관찰 기간·접근권한·예산에 따라 달라지는 예측은 "
        "아래 차단 사유에 기록하고, 기준 일정 변경은 CR과 새 버전으로 남깁니다.",
        "",
        f"전체 {len(tasks)}개 작업 중 {sum(t['status'] == 'done' for t in tasks)}개 완료. "
        "게이트가 통과하기 전에는 해당 단계 완료나 다음 단계 운용 준비를 주장하지 않습니다.",
        "",
        "| WBS | 단계 / 작업 | 담당 기능 | 선행 작업 | 기준 일정 / 예상 작업일 "
        "| 상태 | 실적 완료 | 근거 / 차단 사유 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task in tasks:
        links = ", ".join(f"[{Path(path).name}](../{path})" for path in task.get("evidence", []))
        note = task.get("blocker", "")
        evidence = "; ".join(part for part in (links, note) if part)
        finish = task["baseline_start"] + task["duration"]
        lines.append(
            f"| {task['id']} | {task['phase']} / {task['name']} | {task['owner']} | "
            f"{', '.join(task['depends_on']) or '—'} | "
            f"D+{task['baseline_start']}–{finish} / {task['duration']}일 | "
            f"{LABELS[task['status']]} | {task.get('actual_finish', '—')} | {evidence} |"
        )
    lines += ["", "## 완료 기준", ""]
    lines += [f"- **{task['id']}**: {task['acceptance']}" for task in tasks]
    lines += [
        "",
        "변경관리: [관리 규칙](management/CONTROL.md) · "
        "[CR-0001](changes/CR-0001.md) · [CR-0002](changes/CR-0002.md) · "
        "[CR-0003](changes/CR-0003.md) · [CR-0004](changes/CR-0004.md) · "
        "[일일 현황](management/STATUS.md)",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = render(validate())
    path = ROOT / "docs/WBS.md"
    if args.write:
        path.write_text(output, encoding="utf-8", newline="\n")
    elif not path.exists() or path.read_text(encoding="utf-8") != output:
        raise SystemExit("WBS rendering is stale; run scripts/project_status.py --write")
    print("Plan baselines, dependencies, evidence and WBS rendering verified")


if __name__ == "__main__":
    main()
