# setup.py
import json, os, shutil, subprocess, sys
from pathlib import Path
import questionary
from . import auth

NAME = "spotify"  # your package name, must match pyproject.toml

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", ""))
UV = shutil.which("uv") or "uv"
PROJECT = r"C:\Users\Windows\Desktop\MCP\spotify"

SERVE = [UV, "--directory", PROJECT, "run", NAME, "serve"]

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
    print(json.dumps({NAME: entry}, indent=2))


def add_to_file(name, agent):
    """Returns True if the config file was changed."""
    f, key = agent["file"], agent["key"]
    entry = agent.get("entry", ENTRY)

    # OpenCode also reads opencode.jsonc. If we're already in there, leave it alone.
    jsonc = f.with_suffix(".jsonc")
    if jsonc.exists():
        text = jsonc.read_text(encoding="utf-8-sig", errors="ignore")
        if f'"{NAME}"' in text:
            print(f"{name}: already set up (found in {jsonc.name})")
            return False

    try:
        cfg = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
    except json.JSONDecodeError:
        print_manual(name, key, entry, f"could not read {f}")
        return False

    current = cfg.get(key, {}).get(NAME)
    if current == entry:
        print(f"{name}: already set up")
        return False

    if not f.exists() and name == "OpenCode":
        cfg["$schema"] = "https://opencode.ai/config.json"

    cfg.setdefault(key, {})[NAME] = entry
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"{name}: {'updated' if current else 'added'}")
    return True


def add_to_claude_code():
    claude = shutil.which("claude")
    r = subprocess.run(
        [claude, "mcp", "add", "--scope", "user", NAME, "--", *SERVE],
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


def run():
    if auth.is_signed_in():
        print("Already signed in.")
    elif questionary.confirm("Sign in now?").ask():
        try:
            auth.login()
            print("Signed in.")
        except RuntimeError as e:
            print(f"Sign in failed: {e}")

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