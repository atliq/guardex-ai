# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""HTTP routes backing the local UI's Config, Logs, and Meta views."""

from __future__ import annotations

import dataclasses
import pathlib
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Query

from guardex._types import CATEGORY_DESCRIPTIONS
from guardex._ui.events import EventRecorder
from guardex._ui.playground import run_playground
from guardex._ui.samples import sample_payloads
from guardex._ui.schema import GATE_GROUPS, UI_CONFIG_FIELDS
from guardex._ui.state import ServerDefaults, UnknownConfigField
from guardex._ui.yaml_io import POLICY_FILENAME, save_policy
from guardex._version import get_package_version


def _entity_options() -> List[str]:
    from guardex._engine.services.pii_detector import DEFAULT_ENTITIES

    return sorted(DEFAULT_ENTITIES)


def build_router(
    defaults: ServerDefaults,
    recorder: EventRecorder,
    runner: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/config")
    def get_config() -> Dict[str, Any]:
        return {"config": defaults.snapshot()}

    @router.get("/v1/config/schema")
    def get_config_schema() -> Dict[str, Any]:
        return {
            "fields": [dataclasses.asdict(f) for f in UI_CONFIG_FIELDS],
            "gate_groups": GATE_GROUPS,
            "options": {
                "pii_entities": _entity_options(),
                "categories": [
                    {"value": code, "label": label}
                    for code, label in sorted(CATEGORY_DESCRIPTIONS.items())
                ],
            },
        }

    @router.get("/v1/samples")
    def get_samples() -> Dict[str, Any]:
        return {"samples": sample_payloads()}

    @router.post("/v1/playground")
    def playground(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        if runner is None:
            raise HTTPException(status_code=501, detail="no screening runner attached")

        started = time.perf_counter()
        try:
            result = run_playground(
                runner,
                defaults,
                text=text,
                stage=body.get("stage") or "input",
                sources=body.get("sources") or [],
                overrides=body.get("overrides") or {},
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc).split("\n")[0]) from exc

        recorder.record(
            stage=body.get("stage") or "input",
            result=result["raw"],
            latency_ms=(time.perf_counter() - started) * 1000,
            request_id=result.get("request_id"),
            text=text,
            gate_results=result["gates"],
            decided_by=result["decided_by"],
            degraded=result["degraded"],
        )
        result.pop("raw", None)
        return result

    @router.put("/v1/config")
    def put_config(patch: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        try:
            return {"config": defaults.replace(patch)}
        except UnknownConfigField as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/v1/config/reset")
    def reset_config() -> Dict[str, Any]:
        return {"config": defaults.reset()}

    @router.post("/v1/config/save")
    def save_config() -> Dict[str, Any]:
        path = pathlib.Path.cwd() / POLICY_FILENAME
        try:
            written = save_policy(defaults.snapshot(), path)
        except ImportError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"cannot write {path}: {exc}") from exc
        return {"path": str(written)}

    @router.get("/v1/logs")
    def get_logs(limit: int = Query(200, ge=1, le=1000)) -> Dict[str, Any]:
        return {"events": recorder.recent(limit=limit), "store_text": recorder.store_text}

    @router.get("/v1/logs/stats")
    def get_log_stats() -> Dict[str, Any]:
        return recorder.stats()

    @router.delete("/v1/logs")
    def clear_logs() -> Dict[str, Any]:
        recorder.clear()
        return {"cleared": True}

    @router.get("/v1/meta")
    def get_meta() -> Dict[str, Any]:
        from guardex._engine.providers.registry import (
            get_classifier_provider,
            get_grounding_provider,
            get_pii_provider,
            get_topic_scope_provider,
        )

        return {
            "version": get_package_version(),
            "ui": True,
            "engines": {
                "classifier": get_classifier_provider() is not None,
                "pii": get_pii_provider() is not None,
                "scope": get_topic_scope_provider() is not None,
                "grounding": get_grounding_provider() is not None,
            },
        }

    return router
