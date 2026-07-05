"""
Persistent alias vault for protected domain replacement.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import string
import sys
from pathlib import Path
from typing import Callable, Dict, Tuple, TypeVar

from app.config import settings as app_settings


T = TypeVar("T")


def _acquire_file_lock(fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _release_file_lock(fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class PrivacyAliasVault:
    """Stores stable original<->alias domain mappings."""

    def __init__(self, vault_file: Path | None = None):
        if vault_file is None:
            vault_file = Path(app_settings.data_dir) / "privacy_alias_map.json"
        self.vault_file = vault_file
        self.lock_file = vault_file.with_suffix(vault_file.suffix + ".lock")
        self._lock = asyncio.Lock()
        self._cache: dict[str, str] | None = None

    def _ensure_parent_sync(self) -> None:
        self.vault_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_map_sync(self) -> dict[str, str]:
        if not self.vault_file.exists():
            return {}
        content = self.vault_file.read_text(encoding="utf-8")
        if not content.strip():
            return {}
        data = json.loads(content)
        return {
            str(original).lower(): str(alias).lower()
            for original, alias in data.items()
        }

    def _write_map_atomic_sync(self, data: Dict[str, str]) -> None:
        tmp_path = self.vault_file.with_suffix(self.vault_file.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.vault_file)

    def _with_cross_process_lock(self, update_fn: Callable[[dict[str, str]], Tuple[T, dict[str, str] | None]]) -> T:
        """Run `update_fn` under an OS file lock.

        update_fn receives the current map and returns (result, new_map_or_None).
        If new_map is None, no write occurs. Caller is responsible for not mutating the map in place.
        """
        self._ensure_parent_sync()
        with open(self.lock_file, "a+") as lock_fh:
            _acquire_file_lock(lock_fh)
            try:
                current = self._read_map_sync()
                result, new_map = update_fn(current)
                if new_map is not None:
                    self._write_map_atomic_sync(new_map)
                return result
            finally:
                _release_file_lock(lock_fh)

    async def _load_map(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache

        def _read(_current: dict[str, str]) -> Tuple[dict[str, str], None]:
            return _current, None

        self._cache = await asyncio.to_thread(self._with_cross_process_lock, _read)
        return self._cache

    @staticmethod
    def _random_label(length: int = 18) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def get_or_create_alias_domain(self, original_domain: str, alias_suffix: str) -> str:
        original = original_domain.strip().lower()
        suffix = alias_suffix.strip().lower()
        if not original:
            return original_domain

        async with self._lock:
            def _read_or_write(current: dict[str, str]) -> Tuple[str, dict[str, str] | None]:
                existing = current.get(original)
                if existing:
                    return existing, None

                alias = f"{self._random_label()}.{suffix}"
                reverse_values = set(current.values())
                while alias in reverse_values:
                    alias = f"{self._random_label()}.{suffix}"

                updated = dict(current)
                updated[original] = alias
                return alias, updated

            alias, updated_cache = await asyncio.to_thread(
                self._with_cross_process_lock_returning_state, _read_or_write
            )
            self._cache = updated_cache
            return alias

    def _with_cross_process_lock_returning_state(
        self,
        update_fn: Callable[[dict[str, str]], Tuple[T, dict[str, str] | None]],
    ) -> Tuple[T, dict[str, str]]:
        """Like _with_cross_process_lock but returns (result, final_map_state) so caller can refresh cache."""
        self._ensure_parent_sync()
        with open(self.lock_file, "a+") as lock_fh:
            _acquire_file_lock(lock_fh)
            try:
                current = self._read_map_sync()
                result, new_map = update_fn(current)
                if new_map is not None:
                    self._write_map_atomic_sync(new_map)
                    return result, new_map
                return result, current
            finally:
                _release_file_lock(lock_fh)

    async def get_reverse_map(self) -> dict[str, str]:
        mapping = await self._load_map()
        return {alias: original for original, alias in mapping.items()}
