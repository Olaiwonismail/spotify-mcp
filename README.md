# Spotify MCP

A local MCP server for Spotify listening context, music discovery, playlists, and playback.

## Authentication

The server uses Spotify Authorization Code with PKCE. The existing token location is
`~/.config/spotify/token.json`; `spotify auth login` writes to that location and both the
CLI and MCP use the same path. Token values are never returned by tools.

```powershell
spotify auth login
spotify auth status
spotify serve
```

Login requests the scopes needed by the available tools. If Spotify reports missing
permissions, run `spotify auth login` again and approve the requested access. Access
tokens are refreshed automatically when possible. Playback control and queueing require
a Spotify Premium account and an active Spotify device.

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
