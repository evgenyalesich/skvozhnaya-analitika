#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# Temporary allow-list for legacy monolith files.
LEGACY_FILE_LIMITS: dict[str, int] = {
    "backend/app/api/routers/reports.py": 3400,
    "backend/app/api/routers/roistat_weekly_report.py": 1200,
    "backend/app/api/routers/admin.py": 520,
    "backend/app/services/report_repository.py": 2800,
    "backend/app/services/roistat_weekly_report.py": 1300,
    "backend/app/services/raw_user_repository.py": 850,
    "backend/app/services/aggregate_refresher.py": 760,
    "backend/app/services/telegram_membership_service.py": 1100,
    "backend/app/services/marketing_daily_service.py": 900,
    "backend/app/services/roistat_lessons_report.py": 900,
    "backend/app/worker/tasks.py": 1000,
    "backend/app/ingestion/pokerhub_ingestor.py": 850,
    "backend/app/ingestion/google_sheets_ingestor.py": 620,
    "backend/app/ingestion/replication_worker.py": 1150,
    "backend/app/ingestion/telegram_ingestor.py": 500,
    "backend/app/ingestion/pokerhub_cache_ingestor.py": 500,
    "backend/app/ingestion/ingestion_service.py": 500,
}

DEFAULT_FILE_LIMIT = 450
DEFAULT_FUNCTION_LIMIT = 120


def _iter_target_files() -> list[Path]:
    files = []
    for base in ("backend/app", "backend/tests"):
        base_path = ROOT / base
        if base_path.exists():
            files.extend(base_path.rglob("*.py"))
    return files


def _check_file_lines(path: Path) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    limit = LEGACY_FILE_LIMITS.get(rel, DEFAULT_FILE_LIMIT)
    if len(lines) > limit:
        return f"{rel}: {len(lines)} lines exceeds limit {limit}"
    return None


def _function_length_violations(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    # Keep function-size gate relaxed inside explicitly legacy modules.
    if rel in LEGACY_FILE_LIMITS:
        return []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=rel)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        fn_len = end_lineno - node.lineno + 1
        if fn_len > DEFAULT_FUNCTION_LIMIT:
            violations.append(f"{rel}:{node.lineno} function `{node.name}` has {fn_len} lines (limit {DEFAULT_FUNCTION_LIMIT})")
    return violations


def main() -> int:
    violations: list[str] = []
    for path in _iter_target_files():
        file_violation = _check_file_lines(path)
        if file_violation:
            violations.append(file_violation)
        violations.extend(_function_length_violations(path))

    if violations:
        print("Size guard violations:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("Size guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
