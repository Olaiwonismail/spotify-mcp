"""Shared authenticated Spotify Web API client helpers."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any, Iterable

import httpx2

from . import auth

API_BASE = "https://api.spotify.com/v1"
TIMEOUT_SECONDS = 30.0
MAX_429_RETRIES = 2
MAX_INLINE_RETRY_AFTER = 60.0


class SpotifyAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"Spotify request failed ({status_code}): {message}")


def _error_message(response: Any) -> str:
    try:
        body = response.json()
        error = body.get("error", body)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("error_description") or error)
        return str(error)
    except (ValueError, AttributeError):
        return response.text or "Unknown Spotify API error"


def _retry_after(response: Any) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


async def spotify_request(
    method: str,
    path: str,
    *,
    required_scopes: Iterable[str] = (),
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated request, refreshing once on 401 and backing off on 429."""
    required = tuple(required_scopes)
    access_token = await auth.get_access_token(required)
    refreshed_after_401 = False

    async with httpx2.AsyncClient(http2=True, timeout=TIMEOUT_SECONDS) as client:
        retry_number = 0
        while True:
            response = await client.request(
                method,
                f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                json=json_body,
            )

            if response.status_code == 401 and not refreshed_after_401:
                access_token = await auth.refresh_access_token(required)
                refreshed_after_401 = True
                continue

            if response.status_code == 429:
                retry_after = _retry_after(response)
                if retry_number >= MAX_429_RETRIES:
                    raise SpotifyAPIError(
                        response.status_code,
                        "Rate limit reached; wait before trying again.",
                        retry_after,
                    )

                backoff = retry_after
                if backoff is None:
                    backoff = min(2.0**retry_number, MAX_INLINE_RETRY_AFTER)
                # Avoid holding a tool call open for a long Retry-After. In that case,
                # surface the exact delay instead of retrying before Spotify permits it.
                if backoff > MAX_INLINE_RETRY_AFTER:
                    raise SpotifyAPIError(
                        response.status_code,
                        f"Rate limited; retry after {backoff:g} seconds.",
                        backoff,
                    )
                await asyncio.sleep(backoff + random.uniform(0.05, 0.25 * (retry_number + 1)))
                retry_number += 1
                continue

            if response.status_code >= 400:
                raise SpotifyAPIError(response.status_code, _error_message(response))
            if response.status_code == 204 or not response.content:
                return None
            return response.json()


def json_result(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def bounded_int(name: str, value: int, minimum: int, maximum: int) -> int:
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value
