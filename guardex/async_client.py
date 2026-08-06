# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""AsyncGuardExClient - async HTTP client for the GuardEx API.

Use this in async applications (FastAPI, aiohttp, Starlette) to avoid
blocking the event loop during guardrail calls.

Usage::

    from guardex import AsyncGuardExClient

    async with AsyncGuardExClient(base_url="http://localhost:8001") as gx:
        result, req_id = await gx.screen("Hello world", stage="input")
        print(result["classify"]["safe"])
"""

from __future__ import annotations

import asyncio
import os
import random
import logging
from typing import Any, Dict, List, Literal, TYPE_CHECKING

import httpx

from ._constants import DEFAULT_PII_THRESHOLD
from ._transport import (
    DEFAULT_API_ERROR_MESSAGES,
    HEADER_REQUEST_ID as _HEADER_REQUEST_ID,
    base_headers,
    build_screen_batch_payload,
    build_screen_payload,
    grounding_failopen_shape,
    parse_pii_blocked_error,
    screen_failopen_shape,
)
from ._types import resolve_categories
from ._version import get_package_version as _get_version

if TYPE_CHECKING:
    from .effective_config import EffectiveConfig

logger = logging.getLogger(__name__)

_SDK_VERSION = _get_version()
_DEFAULT_BASE_URL = "http://localhost:8001"


class AsyncGuardExClient:
    """Async HTTP client for the GuardEx API.

    Parameters
    ----------
    api_key:
        GuardEx API key. Falls back to ``GUARDEX_API_KEY`` env var.
    base_url:
        API server URL. Falls back to ``GUARDEX_BASE_URL`` env var.
    timeout:
        Read timeout in seconds.
    max_retries:
        Number of retries on 429/5xx errors.
    fail_open:
        If True, return safe on transport failures and on 429/5xx after
        retries are exhausted. 4xx client errors (401/403/404/422 ...)
        always raise. If False, raise on any failure.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        fail_open: bool = False,
    ) -> None:
        self.api_key = api_key or os.getenv("GUARDEX_API_KEY", "")
        explicit_url = base_url or os.getenv("GUARDEX_BASE_URL", "")
        if not self.api_key and not explicit_url:
            raise ValueError(
                "GuardEx requires either an api_key or a base_url (self-hosted server).\n"
                "  In-process:   Guard()\n"
                "  Self-hosted:  Guard(base_url='http://localhost:8001')\n"
                "  Set env var:  GUARDEX_API_KEY or GUARDEX_BASE_URL"
            )

        self.base_url = (explicit_url or _DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.fail_open = fail_open

        _headers = base_headers(_SDK_VERSION, self.api_key)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=_headers,
            timeout=httpx.Timeout(
                connect=5.0,
                read=float(self.timeout),
                write=5.0,
                pool=10.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=300,
            ),
            http2=True,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncGuardExClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json: Dict[str, Any],
        extra_headers: Dict[str, str] | None = None,
    ) -> tuple[Dict[str, Any], str | None]:
        """Make an API request with exponential-backoff retry.

        Returns
        -------
        tuple[dict, str | None]
            ``(response_body, request_id)``
        """
        from .exceptions import GuardExAPIError

        headers = dict(extra_headers) if extra_headers else {}
        last_exc: Exception | None = None

        for attempt in range(1 + self.max_retries):
            try:
                resp = await self._client.request(method, path, json=json,
                                                  headers=headers)

                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < self.max_retries:
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait = min(float(retry_after), 30.0)
                            except ValueError:
                                wait = 1.0
                        else:
                            wait = (2 ** attempt) * 0.5 + random.uniform(0, 0.25)
                        logger.warning(
                            "GuardEx %d retrying in %.2fs (attempt %d/%d)",
                            resp.status_code, wait, attempt + 1, 1 + self.max_retries,
                        )
                        await asyncio.sleep(wait)
                        continue
                    # Retries exhausted
                    if self.fail_open:
                        logger.error(
                            "GuardEx server error %d after %d attempts "
                            "(fail_open=True): returning unscreened pass",
                            resp.status_code, 1 + self.max_retries,
                        )
                        return {"_fail_open": True}, None
                    if resp.status_code == 429:
                        raise GuardExAPIError(
                            status_code=429,
                            error_type="rate_limit_error",
                            message="Rate limit exceeded. Slow down requests or add retry delays.",
                            code="rate_limited",
                        )
                    raise GuardExAPIError(
                        status_code=resp.status_code,
                        error_type="server_error",
                        message=f"GuardEx server error ({resp.status_code}). Try again later.",
                        code="server_error",
                    )

                if resp.status_code >= 400:
                    # Terminal client errors (auth, validation, wrong URL):
                    # never retried, never failed open.
                    try:
                        data = resp.json()
                    except Exception as e:
                        logger.debug(
                            "Failed to parse %s error body as JSON: %s",
                            resp.status_code, e,
                        )
                        data = {}
                    error_info = data.get("error", {})
                    raise GuardExAPIError(
                        status_code=resp.status_code,
                        error_type=error_info.get("type", "api_error"),
                        message=error_info.get(
                            "message",
                            DEFAULT_API_ERROR_MESSAGES.get(resp.status_code, resp.text),
                        ),
                        code=error_info.get("code", "unknown"),
                    )

                resp.raise_for_status()
                request_id = resp.headers.get(_HEADER_REQUEST_ID)
                return resp.json(), request_id

            except GuardExAPIError:
                raise  # never retry auth/validation errors
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = (2 ** attempt) * 0.5 + random.uniform(0, 0.25)
                    logger.warning(
                        "GuardEx async request failed (attempt %d/%d), "
                        "retrying in %.2fs: %s",
                        attempt + 1, 1 + self.max_retries, backoff, exc,
                    )
                    await asyncio.sleep(backoff)
                    continue

                if self.fail_open:
                    logger.warning("GuardEx API error (fail_open=True): %s", exc)
                    return {"_fail_open": True}, None
                raise

        if last_exc:
            raise last_exc
        return {}, None

    async def screen(
        self,
        text: str,
        stage: str = "input",
        pii_action: Literal["mask", "block", "none"] = "mask",
        categories: List[str] | None = None,
        pii_entities: List[str] | None = None,
        pii_threshold: float = DEFAULT_PII_THRESHOLD,
        pii_custom_regex: Dict[str, str] | None = None,
        scope_topics: List[str] | None = None,
        scope_utterances: Dict[str, List[str]] | None = None,
        scope_examples: List[str] | None = None,
        scope_width: str = "moderate",
        scope_threshold: float | None = None,
        scope_alpha: float = 0.0,
        cascade_mode: str = "safety",
        audit_log: bool = False,
        extra_headers: Dict[str, str] | None = None,
    ) -> tuple[Dict[str, Any], str | None]:
        """Combined PII + classification + scope in one round-trip.

        Returns
        -------
        tuple[dict, str | None]
            ``(result_body, request_id)``
        """
        from .exceptions import GuardExAPIError

        payload = build_screen_payload(
            text=text, stage=stage, pii_action=pii_action,
            pii_threshold=pii_threshold, cascade_mode=cascade_mode,
            audit_log=audit_log, categories=categories, pii_entities=pii_entities,
            pii_custom_regex=pii_custom_regex,
            scope_topics=scope_topics, scope_utterances=scope_utterances,
            scope_examples=scope_examples, scope_width=scope_width,
            scope_threshold=scope_threshold, scope_alpha=scope_alpha,
        )

        try:
            body, request_id = await self._request("POST", "/v1/screen",
                                                   json=payload,
                                                   extra_headers=extra_headers)
        except GuardExAPIError as exc:
            parse_pii_blocked_error(exc, stage)
            raise

        if body.get("_fail_open"):
            return screen_failopen_shape(text), None
        return body, request_id

    async def check_grounding(
        self,
        response_text: str,
        sources: List[str],
        mode: str | None = None,
        threshold: float | None = None,
        extra_headers: Dict[str, str] | None = None,
    ) -> tuple[Dict[str, Any], str | None]:
        """Async: verify LLM output against source documents for hallucination.

        Returns
        -------
        tuple[dict, str | None]
            ``(result_body, request_id)``
        """
        payload: Dict[str, Any] = {
            "response_text": response_text,
            "sources": sources,
        }
        if mode is not None:
            payload["mode"] = mode
        if threshold is not None:
            payload["threshold"] = threshold

        body, request_id = await self._request(
            "POST", "/v1/grounding", json=payload,
            extra_headers=extra_headers,
        )

        if body.get("_fail_open"):
            return grounding_failopen_shape(mode), None

        return body, request_id

    async def screen_batch(
        self,
        texts: List[str],
        stage: str = "input",
        pii_action: Literal["mask", "block", "none"] = "mask",
        categories: List[str] | None = None,
        pii_entities: List[str] | None = None,
        pii_threshold: float = DEFAULT_PII_THRESHOLD,
        pii_custom_regex: Dict[str, str] | None = None,
        cascade_mode: str = "safety",
        extra_headers: Dict[str, str] | None = None,
    ) -> List[Dict[str, Any]]:
        """Screen a batch of texts in a single round-trip.

        Returns
        -------
        list[dict]
            One result dict per input text, in the same order.
        """
        if not texts:
            return []

        payload = build_screen_batch_payload(
            texts=texts, stage=stage, pii_action=pii_action,
            pii_threshold=pii_threshold, cascade_mode=cascade_mode,
            categories=categories, pii_entities=pii_entities,
            pii_custom_regex=pii_custom_regex,
        )

        from .exceptions import GuardExAPIError

        try:
            body, _ = await self._request("POST", "/v1/screen/batch", json=payload,
                                          extra_headers=extra_headers)
        except Exception as exc:
            # Batch endpoint may not exist on older servers (404). Fall back
            # to sequential screen() calls instead of fail-open all-safe.
            if isinstance(exc, GuardExAPIError) and exc.status_code == 404:
                logger.info(
                    "Batch endpoint not available, falling back to sequential "
                    "(%d items)", len(texts),
                )
                results = []
                for t in texts:
                    r, _ = await self.screen(
                        text=t, stage=stage, pii_action=pii_action,
                        categories=categories, pii_entities=pii_entities,
                        pii_threshold=pii_threshold,
                        pii_custom_regex=pii_custom_regex,
                        cascade_mode=cascade_mode,
                        extra_headers=extra_headers,
                    )
                    results.append(r)
                return results
            raise

        if body.get("_fail_open"):
            logger.warning("Batch fail-open triggered, falling back to sequential")
            results = []
            for t in texts:
                r, _ = await self.screen(
                    text=t, stage=stage, pii_action=pii_action,
                    categories=categories, pii_entities=pii_entities,
                    pii_threshold=pii_threshold,
                    pii_custom_regex=pii_custom_regex,
                    cascade_mode=cascade_mode,
                    extra_headers=extra_headers,
                )
                results.append(r)
            return results

        return body.get("results", [])

    async def classify(
        self,
        text: str,
        stage: str = "input",
        categories: List[str] | None = None,
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """Classify text for safety.

        Returns dict with keys: safe, category, categories, description.
        """
        payload: Dict[str, Any] = {"text": text, "stage": stage}
        if categories:
            payload["categories"] = resolve_categories(categories)

        body, request_id = await self._request("POST", "/v1/classify", json=payload,
                                               extra_headers=extra_headers)
        if body.get("_fail_open"):
            return {"safe": True, "category": None, "categories": [], "_request_id": None}
        if request_id:
            body["_request_id"] = request_id
        return body

    async def pii_scan(
        self,
        text: str,
        entities: List[str] | None = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """Scan text for PII.

        Returns dict with keys: has_pii, entities.
        """
        payload: Dict[str, Any] = {"text": text, "threshold": threshold}
        if entities:
            payload["entities"] = entities

        body, _ = await self._request("POST", "/v1/pii/scan", json=payload,
                                      extra_headers=extra_headers)
        if body.get("_fail_open"):
            return {"has_pii": False, "entities": []}
        return body

    async def pii_mask(
        self,
        text: str,
        entities: List[str] | None = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """Scan and mask PII in text.

        Returns dict with keys: has_pii, entities, masked_text.
        """
        payload: Dict[str, Any] = {"text": text, "threshold": threshold}
        if entities:
            payload["entities"] = entities

        body, _ = await self._request("POST", "/v1/pii/mask", json=payload,
                                      extra_headers=extra_headers)
        if body.get("_fail_open"):
            return {"has_pii": False, "entities": [], "masked_text": text}
        return body

    async def get_effective_config(self) -> "EffectiveConfig":
        """Fetch merged effective config (dashboard + code).

        Calls GET /v1/config/effective. Returns a typed EffectiveConfig
        with merged PII and content moderation settings plus source annotations.
        """
        from .effective_config import EffectiveConfig

        body, _ = await self._request("GET", "/v1/config/effective", json={})
        return EffectiveConfig.from_api_response(body)

    async def health(self) -> Dict[str, Any]:
        """Check API server health (no auth required)."""
        resp = await self._client.get("/v1/health")
        resp.raise_for_status()
        return resp.json()
