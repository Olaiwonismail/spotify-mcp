# setup.py
import json, os, shutil, subprocess, sys
from pathlib import Path
import questionary
from . import auth

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", ""))

ENTRY = {"command": "uvx", "args": ["mytool", "serve"]}

OPENCODE_ENTRY = {
    "type": "local",
    "command": ["uvx", "mytool", "serve"],
    "enabled": True,
}

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
    print(json.dumps({"mytool": entry}, indent=2))


def add_to_file(name, agent):
    f, key = agent["file"], agent["key"]
    entry = agent.get("entry", ENTRY)

    # opencode.jsonc allows comments, which json.loads can't parse
    jsonc = f.with_suffix(".jsonc")
    if jsonc.exists():
        print_manual(name, key, entry, f"found {jsonc.name}")
        return

    try:
        cfg = json.loads(f.read_text()) if f.exists() else {}
    except json.JSONDecodeError:
        print_manual(name, key, entry, f"could not read {f}")
        return

    if not f.exists() and name == "OpenCode":
        cfg["$schema"] = "https://opencode.ai/config.json"

    cfg.setdefault(key, {})["mytool"] = entry
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cfg, indent=2))


def run():
    if not auth.is_signed_in():
        if questionary.confirm("Sign in now?").ask():
            auth.login()

    found = [n for n, a in AGENTS.items() if a["file"].parent.exists()]
    if shutil.which("claude"):
        found.append("Claude Code")

    picked = questionary.checkbox("Add to which agents?", choices=found).ask() or []

    for name in picked:
        if name == "Claude Code":
            subprocess.run(
                ["claude", "mcp", "add", "mytool", "--", "uvx", "mytool", "serve"]
            )
        else:
            add_to_file(name, AGENTS[name])

    print("Done. Restart your agent to load it.")