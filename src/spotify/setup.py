# setup.py
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import questionary
from . import auth

SERVER_NAME = "spotify"
PACKAGE_NAME = "spotify-vibe-mcp"
COMMAND_NAME = "spotify-mcp"

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", ""))
UV = shutil.which("uv") or "uv"
PROJECT = Path(__file__).resolve().parents[2]

# A checkout uses its own source tree; an installed release gets a portable
# uv tool-run entry that resolves the published package on any machine.
if (PROJECT / "pyproject.toml").is_file():
    SERVE = [UV, "--directory", str(PROJECT), "run", COMMAND_NAME, "serve"]
else:
    SERVE = [
        UV,
        "tool",
        "run",
        "--from",
        PACKAGE_NAME,
        COMMAND_NAME,
        "serve",
    ]

ENTRY = {"command": SERVE[0], "args": SERVE[1:]}

OPENCODE_ENTRY = {"type": "local", "command": SERVE, "enabled": True}

AGENTS = {
    "Claude Desktop": {
        "file": (
            HOME / "Library/Application Support/Claude/claude_desktop_config.json"
            if sys.platform == "darwin"
            else APPDATA / "Claude/claude_desktop_config.json"
        ),
        "key": "mcpServers",
    },
    "Cursor": {
        "file": HOME / ".cursor/mcp.json",
        "key": "mcpServers",
    },
    "OpenCode": {
        "file": HOME / ".config/opencode/opencode.json",
        "key": "mcp",
        "entry": OPENCODE_ENTRY,
    },
}


def print_manual(name, key, entry, reason):
    print(f"{name}: {reason}. Add this under \"{key}\" yourself:")
    print(json.dumps({SERVER_NAME: entry}, indent=2))


def add_to_file(name, agent):
    """Returns True if the config file was changed."""
    f, key = agent["file"], agent["key"]
    entry = agent.get("entry", ENTRY)

    # OpenCode also reads opencode.jsonc. If we're already in there, leave it alone.
    jsonc = f.with_suffix(".jsonc")
    if jsonc.exists():
        text = jsonc.read_text(encoding="utf-8-sig", errors="ignore")
        if f'"{SERVER_NAME}"' in text:
            print(f"{name}: already set up (found in {jsonc.name})")
            return False

    try:
        cfg = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
    except json.JSONDecodeError:
        print_manual(name, key, entry, f"could not read {f}")
        return False

    current = cfg.get(key, {}).get(SERVER_NAME)
    if current == entry:
        print(f"{name}: already set up")
        return False

    if not f.exists() and name == "OpenCode":
        cfg["$schema"] = "https://opencode.ai/config.json"

    cfg.setdefault(key, {})[SERVER_NAME] = entry
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"{name}: {'updated' if current else 'added'}")
    return True


def add_to_claude_code():
    claude = shutil.which("claude")
    r = subprocess.run(
        [claude, "mcp", "add", "--scope", "user", SERVER_NAME, "--", *SERVE],
        capture_output=True, text=True,
    )
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        print("Claude Code: added")
        return True
    if "already exists" in out.lower():
        print("Claude Code: already set up")
        return False
    print(f"Claude Code: could not add ({out})")
    return False


def _probe_spotify():
    """Refresh if needed and verify the token with Spotify before setup continues."""
    from .api import spotify_request

    status = auth.get_auth_status(auth.SCOPES)
    if status.get("state") == auth.AuthState.REFRESHABLE.value:
        asyncio.run(auth.get_access_token(auth.SCOPES))
        status = auth.get_auth_status(auth.SCOPES)
    if status.get("state") != auth.AuthState.READY.value:
        return False, status.get("message") or status.get("state", "Unknown auth state")

    asyncio.run(
        spotify_request(
            "GET",
            "/me",
            required_scopes={"user-read-private", "user-read-email"},
        )
    )
    return True, "Spotify account is connected and ready."


def ensure_spotify_auth():
    try:
        ready, message = _probe_spotify()
    except Exception as exc:
        ready, message = False, str(exc)

    if ready:
        print(message)
        return True

    print(f"Spotify authentication needs attention: {message}")
    if not questionary.confirm(
        "Sign in or reauthorize Spotify now?", default=True
    ).ask():
        print("Setup stopped. Run `spotify-mcp connect` again when you're ready to sign in.")
        return False

    try:
        auth.login()
        ready, message = _probe_spotify()
    except Exception as exc:
        ready, message = False, str(exc)

    if not ready:
        print(f"Spotify setup could not be verified: {message}")
        print("Run `spotify-mcp auth login` to try again, then run `spotify-mcp connect`.")
        return False

    print(message)
    return True


def run():
    if not ensure_spotify_auth():
        return

    found = [n for n, a in AGENTS.items() if a["file"].parent.exists()]
    if shutil.which("claude"):
        found.append("Claude Code")

    if not found:
        print_manual("Your agent", "mcpServers", ENTRY, "no supported agent found")
        return

    picked = questionary.checkbox(
        "Add to which agents?",
        choices=[questionary.Choice(n, checked=True) for n in found],
    ).ask() or []

    changed = False
    for name in picked:
        if name == "Claude Code":
            changed |= add_to_claude_code()
        else:
            changed |= add_to_file(name, AGENTS[name])

    if changed:
        print("Done. Restart your agent to load it.")
    else:
        print("Nothing to change.")
