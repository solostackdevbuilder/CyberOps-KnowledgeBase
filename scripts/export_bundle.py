#!/usr/bin/env python3
"""
Copy a clean distributable bundle (sibling folder by default) without API keys or secret settings files.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_RELATIVE = {
    Path("backend/data/settings.json"),
}


def _is_env_file(name: str) -> bool:
    """Return True for any dotenv-style file we must never ship.

    Catches .env, .env.local, .env.production, .env.example.local, etc.
    """
    return name == ".env" or name.startswith(".env.")


def _ignore_pycache(dir_name: str, names: list[str]) -> list[str]:
    skip = {"__pycache__", ".pytest_cache", ".mypy_cache"}
    return [
        n
        for n in names
        if n in skip or n.endswith(".pyc") or _is_env_file(n)
    ]


def _ignore_frontend(_dir: str, names: list[str]) -> list[str]:
    skip = {"node_modules", "dist", ".vite"}
    return [n for n in names if n in skip or _is_env_file(n)]


def _copy_backend_app(dest_root: Path) -> None:
    src = REPO_ROOT / "backend" / "app"
    dst = dest_root / "backend" / "app"
    shutil.copytree(src, dst, ignore=_ignore_pycache, dirs_exist_ok=True)
    for path in dst.rglob("*.backup.py"):
        path.unlink()


def _copy_frontend(dest_root: Path) -> None:
    src = REPO_ROOT / "frontend"
    dst = dest_root / "frontend"
    shutil.copytree(src, dst, ignore=_ignore_frontend, dirs_exist_ok=True)


def _copy_example_data(dest_root: Path) -> None:
    sessions_src = REPO_ROOT / "backend" / "data" / "sessions"
    sessions_dst = dest_root / "backend" / "data" / "sessions"
    sessions_dst.mkdir(parents=True, exist_ok=True)
    if sessions_src.is_dir():
        for f in sessions_src.glob("*.json"):
            shutil.copy2(f, sessions_dst / f.name)

    ops_src = REPO_ROOT / "backend" / "data" / "operations"
    ops_dst = dest_root / "backend" / "data" / "operations"
    ops_dst.mkdir(parents=True, exist_ok=True)
    if ops_src.is_dir():
        for f in ops_src.glob("*.json"):
            shutil.copy2(f, ops_dst / f.name)

    for rel in (
        Path("backend/data/query_cache"),
        Path("backend/data/insights_cache"),
        Path("backend/data/screenshots"),
        Path("backend/data/terminal_logs"),
        Path("backend/data/red_team/faa"),
    ):
        p = dest_root / rel
        p.mkdir(parents=True, exist_ok=True)
        (p / ".gitkeep").write_text("", encoding="utf-8")


def _assert_no_forbidden(dest_root: Path) -> None:
    for rel in FORBIDDEN_RELATIVE:
        p = dest_root / rel
        if p.exists():
            raise RuntimeError(f"Refusing to ship forbidden path: {rel}")

    # Belt-and-suspenders sweep for dotenv-style files that slipped through the
    # ignore functions. Third-party tooling sometimes names env files in
    # unexpected locations, and a single .env.local left in the bundle can leak
    # API keys that the ignore lists above were supposed to catch.
    for candidate in dest_root.rglob("*"):
        if candidate.is_file() and _is_env_file(candidate.name):
            rel = candidate.relative_to(dest_root)
            raise RuntimeError(
                f"Refusing to ship env file in distribution bundle: {rel}. "
                f"Extend _ignore_pycache / _ignore_frontend if this was unexpected."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export clean app bundle (no API keys on disk).")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT.parent / "CyberOps-KnowledgeBase",
        help="Output directory (default: ../CyberOps-KnowledgeBase next to repo)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove existing output directory",
    )
    args = parser.parse_args()
    dest = args.out.resolve()

    for rel in FORBIDDEN_RELATIVE:
        if (REPO_ROOT / rel).exists():
            print(f"Note: source tree contains {rel} - it will NOT be copied.", file=sys.stderr)

    if dest.exists():
        if not args.force:
            print(f"Output exists: {dest}\nUse --force to replace.", file=sys.stderr)
            return 1
        shutil.rmtree(dest)

    dest.mkdir(parents=True)

    _copy_backend_app(dest)
    shutil.copy2(REPO_ROOT / "backend" / "requirements.txt", dest / "backend" / "requirements.txt")

    _copy_frontend(dest)
    _copy_example_data(dest)

    for name in ("Dockerfile", "docker-compose.yml", ".dockerignore"):
        shutil.copy2(REPO_ROOT / name, dest / name)

    env_ex = REPO_ROOT / ".env.example"
    if env_ex.is_file():
        shutil.copy2(env_ex, dest / ".env.example")

    readme = REPO_ROOT / "README.md"
    if readme.is_file():
        shutil.copy2(readme, dest / "README.md")

    scripts_dst = dest / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    for script in ("start.sh", "start.ps1"):
        p = REPO_ROOT / "scripts" / script
        if p.is_file():
            shutil.copy2(p, scripts_dst / script)

    _assert_no_forbidden(dest)
    print(f"Exported bundle to: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
