# Spotify Music MCP

A local MCP server for Spotify listening context, music discovery, playlists, and playback.

## Authentication

The server uses Spotify Authorization Code with PKCE. The existing token location is
`~/.config/spotify/token.json`; `spotify-music-mcp auth login` writes to that location and both the
CLI and MCP use the same path. Token values are never returned by tools.

After the package is published on PyPI, install it persistently with `uv` and run the
connector. It checks the token, refreshes it if needed, prompts for login or new
permissions, verifies the Spotify connection, and configures a supported MCP client:

```powershell
uv tool install spotify-music-mcp
spotify-music-mcp connect
```

For a one-time run without persistent installation:

```powershell
uvx spotify-music-mcp connect
```

After publication, a pip installation can also run the connector directly:

```powershell
py -m pip install spotify-music-mcp
spotify-music-mcp connect
```

For development from a cloned checkout, run `uv sync` followed by
`uv run spotify-music-mcp connect`; the generated MCP entry points back to that checkout.
Restart the selected MCP client when setup finishes. You can inspect auth state with
`spotify-music-mcp auth status`, or run `spotify-music-mcp auth login` to sign in or grant scopes
manually. Access tokens refresh automatically when possible. Playback control and
queueing require a Spotify Premium account and an active Spotify device.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `auth_status` | Read authentication state without exposing credentials |
| `whoami` | Read the current user's profile |
| `get_recently_played` | Read recent listening history, up to 50 items |
| `get_top_items` | Read top artists or tracks by time range |
| `get_saved_tracks` | Read a page of saved tracks |
| `search_catalog` | Find tracks and their Spotify URIs |
| `discover_by_genre` | Search tracks by genre, optional keywords, and year range |
| `find_underground_music` | Search matching low-popularity and broader albums, then retrieve their tracks |
| `get_artist_new_releases` | Read an artist's albums, singles, and compilations |
| `get_album_tracks` | Read tracks from an album |
| `get_user_playlists` | List the current user's playlists |
| `get_playlist_tracks` | Read a page of playlist items |
| `create_playlist` | Create a private playlist by default |
| `add_to_playlist` | Add track IDs or Spotify URIs to a playlist |
| `get_currently_playing` | Read the current playback item |
| `add_to_queue` | Queue a track on the active device |
| `start_playback` | Start a playlist context or track list on an active device |

Paged tools accept `limit` and `offset` where applicable. Search results and playlist
items include Spotify IDs or URIs for use by the playlist and playback tools.

## Example: Japanese rock discovery

You can ask your assistant for a mix that builds on your listening history while adding
artists you have not heard before:

> Find me Japanese rock. Make around 30% of the picks new-to-me artists, and don't limit
> the recommendations to anime soundtracks. Save the results to a private playlist.

An example result is **日本語ロック — 30% new blood**: 33 tracks in a private playlist,
including 11 picks from new-to-you artists. The rest draw on familiar Japanese rock
artists and deeper cuts. Representative new discoveries included:

- SiM — “The Rumbling”
- coldrain — “MAYDAY”
- Crossfaith — “Monolith”
- BAND-MAID — “DOMINATION”
- Vaundy — “Kaiju no Hanauta”

The assistant can use listening history and top-item tools to establish context, search
for tracks that match the requested genre and vibe, then create a playlist and add the
selected Spotify track URIs.

## Example: research-informed study playlist

The Spotify MCP can also build a playlist from recommendations the assistant develops
after doing research:

> Research whether listening to music while studying affects focus or test scores. Use
> the evidence carefully, find recordings used in the studies plus suitable instrumental
> tracks, and put them in a private playlist.

In one example, the assistant created a private playlist with 35 tracks and an estimated
runtime of about 2 hours 50 minutes. The assistant handled the research; the Spotify MCP
provided the catalog search and playlist tools. Private playlist links are account-specific
and should not be copied into public documentation.
