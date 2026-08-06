# SPDX-License-Identifier: Apache-2.0
"""Every PII threshold default resolves to a single constant."""
from __future__ import annotations

import importlib
import inspect

import pytest

from guardex._constants import DEFAULT_PII_THRESHOLD
from guardex.policy import GuardExPolicy

_MODULES = [
    "guardex.policy",
    "guardex.client",
    "guardex.async_client",
    "guardex._engine.runner",
    "guardex._engine.providers.base",
    "guardex._engine.providers.gliner_provider",
]

_PARAM_NAMES = {"threshold", "pii_threshold"}


def _threshold_defaults() -> list[tuple[str, float]]:
    found = []
    for module_name in _MODULES:
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            for func_name, func in inspect.getmembers(cls, inspect.isfunction):
                for param in inspect.signature(func).parameters.values():
                    if param.name in _PARAM_NAMES and isinstance(param.default, float):
                        found.append(
                            (f"{module_name}:{cls.__name__}.{func_name}", param.default)
                        )
    return sorted(found)


def test_policy_default_matches_constant():
    assert GuardExPolicy().pii_threshold == DEFAULT_PII_THRESHOLD


def test_scan_finds_threshold_parameters():
    assert _threshold_defaults(), "signature scan found nothing -- the test is vacuous"


@pytest.mark.parametrize("location,default", _threshold_defaults())
def test_signature_default_matches_constant(location, default):
    assert default == DEFAULT_PII_THRESHOLD, location
