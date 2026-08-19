# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Server-side policy defaults for requests that omit fields."""

from __future__ import annotations

import copy
import threading
from typing import Any, Dict

from guardex._ui.schema import UI_CONFIG_FIELDS


class UnknownConfigField(ValueError):
    """Raised when a config patch names a field outside UI_CONFIG_FIELDS."""


def _schema_defaults() -> Dict[str, Any]:
    return {f.name: copy.deepcopy(f.default) for f in UI_CONFIG_FIELDS}


class ServerDefaults:
    """Policy defaults applied under each request, swapped atomically."""

    def __init__(self) -> None:
        self._current: Dict[str, Any] = _schema_defaults()
        self._lock = threading.Lock()

    def snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(self._current)

    def replace(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        known = {f.name for f in UI_CONFIG_FIELDS}
        unknown = sorted(set(patch) - known)
        if unknown:
            raise UnknownConfigField(
                f"unknown config field(s): {', '.join(unknown)}. "
                f"GET /v1/config/schema lists the accepted names"
            )
        # Build the successor off-lock, then publish it in one assignment so
        # concurrent readers never observe a half-applied patch.
        successor = {**self.snapshot(), **copy.deepcopy(patch)}
        with self._lock:
            self._current = successor
        return copy.deepcopy(successor)

    def merge_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = self.snapshot()
        merged.update({k: v for k, v in payload.items() if v is not None})
        return merged

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self._current = _schema_defaults()
        return self.snapshot()
