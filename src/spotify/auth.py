"""Spotify PKCE login and token lifecycle management."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import webbrowser
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import httpx2
import uvicorn
from fastapi import FastAPI, HTTPException

TOKEN_FILE = Path.home() / ".config" / "spotify" / "token.json"
CLIENT_ID = "8efd28def12e4772815042b5e7111a5f"
# Keep the registered loopback redirect URI stable; Spotify requires an exact match.
REDIRECT_URI = "http://127.0.0.1:8080"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

SCOPES = frozenset(
    {
        "user-read-private",
        "user-read-email",
        "user-read-recently-played",
        "user-top-read",
        "user-library-read",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-public",
        "playlist-modify-private",
        "user-read-currently-playing",
        "user-modify-playback-state",
    }
)


class AuthState(StrEnum):
    SIGNED_OUT = "signed_out"
    READY = "ready"
    REFRESHABLE = "refreshable"
    REFRESHING = "refreshing"
    AUTHORIZING = "authorizing"
    NEEDS_SCOPES = "needs_scopes"
    NEEDS_LOGIN = "needs_login"


class AuthenticationRequired(RuntimeError):
    """Raised when the user needs to complete Spotify login."""


class InsufficientScopes(RuntimeError):
    """Raised when the stored token does not grant a required scope."""

    def __init__(self, missing_scopes: Iterable[str]):
        self.missing_scopes = sorted(set(missing_scopes))
        super().__init__("Missing Spotify permission(s): " + ", ".join(self.missing_scopes))


_refresh_lock = asyncio.Lock()


def _read_token() -> dict[str, Any] | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthenticationRequired(
            "The saved Spotify token could not be read. Run: spotify auth login"
        ) from exc
    if not isinstance(token, dict) or not token.get("access_token"):
        return None
    return token


def _token_scopes(token: dict[str, Any]) -> set[str]:
    scope_value = token.get("scope", "")
    if isinstance(scope_value, str):
        return set(scope_value.split())
    if isinstance(scope_value, list):
        return set(scope_value)
    return set()


def _missing_scopes(token: dict[str, Any], required_scopes: Iterable[str]) -> set[str]:
    return set(required_scopes) - _token_scopes(token)


def _expires_at(token: dict[str, Any]) -> float | None:
    value = token.get("expires_at")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def get_auth_status(required_scopes: Iterable[str] = ()) -> dict[str, Any]:
    """Return a safe, non-secret snapshot of the authentication state."""
    try:
        token = _read_token()
    except AuthenticationRequired as exc:
        return {"state": AuthState.NEEDS_LOGIN.value, "message": str(exc)}
    if token is None:
        return {
            "state": AuthState.SIGNED_OUT.value,
            "message": "Not signed in. Run: spotify auth login",
        }

    missing = sorted(_missing_scopes(token, required_scopes))
    if missing:
        return {
            "state": AuthState.NEEDS_SCOPES.value,
            "missing_scopes": missing,
            "message": "Run: spotify auth login to grant the requested permissions.",
        }

    expiry = _expires_at(token)
    if expiry is not None and expiry <= time.time():
        state = AuthState.REFRESHABLE if token.get("refresh_token") else AuthState.NEEDS_LOGIN
    elif expiry is None and token.get("refresh_token"):
        # Older token files did not record an absolute expiry; refresh before use.
        state = AuthState.REFRESHABLE
    else:
        state = AuthState.READY

    result: dict[str, Any] = {"state": state.value}
    if expiry is not None:
        result["expires_at"] = int(expiry)
    if state == AuthState.NEEDS_LOGIN:
        result["message"] = "The token expired and cannot be refreshed. Run: spotify auth login"
    return result


def _write_token(token: dict[str, Any]) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = TOKEN_FILE.with_suffix(TOKEN_FILE.suffix + ".tmp")
    temp_file.write_text(json.dumps(token), encoding="utf-8")
    temp_file.replace(TOKEN_FILE)


async def refresh_access_token(required_scopes: Iterable[str] = ()) -> str:
    """Refresh the access token and return it, retaining an omitted refresh token."""
    async with _refresh_lock:
        token = _read_token()
        if token is None:
            raise AuthenticationRequired("Not signed in. Run: spotify auth login")

        missing = _missing_scopes(token, required_scopes)
        if missing:
            raise InsufficientScopes(missing)

        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise AuthenticationRequired(
                "The Spotify token cannot be refreshed. Run: spotify auth login"
            )

        async with httpx2.AsyncClient(http2=True, timeout=30.0) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        if response.status_code >= 400:
            try:
                message = response.json().get("error_description") or response.json().get("error")
            except (ValueError, AttributeError):
                message = response.text
            raise AuthenticationRequired(
                f"Spotify token refresh failed ({response.status_code}): {message}. "
                "Run: spotify auth login"
            )

        refreshed = response.json()
        updated = dict(token)
        updated.update(refreshed)
        updated["refresh_token"] = refreshed.get("refresh_token") or refresh_token
        updated["scope"] = refreshed.get("scope") or token.get("scope", "")
        expires_in = refreshed.get("expires_in")
        if expires_in is not None:
            updated["expires_at"] = time.time() + float(expires_in)
        _write_token(updated)
        return updated["access_token"]


async def get_access_token(required_scopes: Iterable[str] = ()) -> str:
    """Return a usable token, refreshing first when expiry is known or unknown."""
    token = _read_token()
    if token is None:
        raise AuthenticationRequired("Not signed in. Run: spotify auth login")

    missing = _missing_scopes(token, required_scopes)
    if missing:
        raise InsufficientScopes(missing)

    state = get_auth_status(required_scopes).get("state")
    if state == AuthState.NEEDS_LOGIN.value:
        raise AuthenticationRequired(
            "The Spotify token expired and cannot be refreshed. Run: spotify auth login"
        )
    if state == AuthState.REFRESHABLE.value:
        return await refresh_access_token(required_scopes)
    return token["access_token"]


async def login_async() -> str:
    """Run the PKCE login callback server without blocking an async event loop."""
    raise NotImplementedError("Use the synchronous login() command-line flow")


def login() -> str:
    code_verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("ascii").rstrip("=")
    oauth_state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": " ".join(sorted(SCOPES)),
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "redirect_uri": REDIRECT_URI,
        "state": oauth_state,
    }

    app = FastAPI()
    result: dict[str, str | None] = {"access_token": None}
    server: uvicorn.Server

    @app.get("/")
    async def callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> dict[str, str]:
        if error:
            server.should_exit = True
            raise HTTPException(status_code=400, detail=f"Spotify authorization failed: {error}")
        if not code or state != oauth_state:
            raise HTTPException(status_code=400, detail="Invalid Spotify authorization callback.")

        async with httpx2.AsyncClient(http2=True, timeout=30.0) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": code_verifier,
                },
            )
        if response.status_code >= 400:
            server.should_exit = True
            raise HTTPException(
                status_code=502,
                detail=f"Spotify token exchange failed ({response.status_code}).",
            )

        data = response.json()
        expires_in = data.get("expires_in")
        if expires_in is not None:
            data["expires_at"] = time.time() + float(expires_in)
        _write_token(data)
        result["access_token"] = data["access_token"]
        server.should_exit = True
        return {"message": "Login successful. You can close this tab."}

    webbrowser.open_new(AUTH_URL + "?" + urllib.parse.urlencode(params))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="warning"))
    server.run()

    if not result["access_token"]:
        raise RuntimeError("Spotify login did not complete. Try: spotify auth login")
    return result["access_token"]
