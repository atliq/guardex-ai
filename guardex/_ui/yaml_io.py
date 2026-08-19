# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Read and write the local policy file the Config page saves to."""

from __future__ import annotations

import copy
import os
import pathlib
from typing import Any, Dict

from guardex._ui.schema import UI_CONFIG_FIELDS

POLICY_FILENAME = "guardex.policy.yaml"

_HEADER = (
    "# Written by the GuardEx local UI. Load it with:\n"
    "#   GuardExPolicy.from_yaml('guardex.policy.yaml')\n"
)


def _require_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("pip install 'guardex-ai[ui]'") from exc
    return yaml


def save_policy(config: Dict[str, Any], path: pathlib.Path) -> pathlib.Path:
    """Write non-default fields of ``config`` to ``path``."""
    yaml = _require_yaml()
    defaults = {f.name: f.default for f in UI_CONFIG_FIELDS}
    body = {k: v for k, v in config.items() if k in defaults and v != defaults[k]}

    # Write-then-rename so a crash mid-write cannot truncate a good policy file.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        _HEADER + yaml.safe_dump(body, sort_keys=True, default_flow_style=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def load_policy(path: pathlib.Path) -> Dict[str, Any]:
    """Read ``path``; return an empty dict when it does not exist."""
    if not path.exists():
        return {}
    yaml = _require_yaml()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping, not {type(data).__name__}")
    return copy.deepcopy(data)
