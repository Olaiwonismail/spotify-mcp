import json
import httpx2
from mcp.server import MCPServer
from .auth import TOKEN_FILE

mcp = MCPServer("spotify")

@mcp.tool()
async def whoami() -> str:
    """Get the signed-in Spotify user's profile."""
    if not TOKEN_FILE.exists():
        return "Not signed in. Run: spotify auth login"
    token = json.loads(TOKEN_FILE.read_text())["access_token"]
    async with httpx2.AsyncClient() as client:
        r = await client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
    if r.status_code != 200:
        return f"Spotify request failed ({r.status_code}). Try: spotify auth login"
    p = r.json()
    return f"{p.get('display_name')} ({p.get('email')})"