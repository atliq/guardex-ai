# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Attach the local UI's routes and static assets to a FastAPI app."""

from __future__ import annotations

import pathlib
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from guardex._ui.events import EventRecorder
from guardex._ui.routes import build_router
from guardex._ui.state import ServerDefaults

DEFAULT_ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui_assets"


def install_ui(
    app: FastAPI,
    defaults: ServerDefaults,
    recorder: EventRecorder,
    assets_dir: Optional[pathlib.Path] = None,
    runner: Optional[object] = None,
) -> bool:
    """Mount UI routes and assets. Returns False when no built assets exist."""
    app.include_router(build_router(defaults, recorder, runner))

    root = (assets_dir or DEFAULT_ASSETS_DIR).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    nested = root / "assets"
    if nested.is_dir():
        app.mount("/assets", StaticFiles(directory=str(nested)), name="guardex-ui-assets")

    @app.get("/", include_in_schema=False)
    def _ui_index() -> FileResponse:
        return FileResponse(index)

    # React Router owns /logs and /config. Any non-/v1 path that reached
    # here is a client route, so return the shell and let it route.
    @app.get("/{path:path}", include_in_schema=False)
    def _ui_catchall(path: str) -> FileResponse:
        if path:
            try:
                candidate = (root / path).resolve()
            except (OSError, RuntimeError, ValueError):
                return FileResponse(index)
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index)

    return True
