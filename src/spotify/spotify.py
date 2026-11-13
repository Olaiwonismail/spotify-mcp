"""Spotify MCP tools for taste, discovery, playlists, and playback."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import quote

from mcp.server import MCPServer

from . import auth
from .api import bounded_int, json_result, spotify_request

mcp = MCPServer("spotify")

TimeRange = Literal["short_term", "medium_term", "long_term"]
ItemType = Literal["artists", "tracks"]


def _path_id(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required.")
    return quote(cleaned, safe="")


def _track_uri(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("spotify:track:"):
        return cleaned
    if not cleaned:
        raise ValueError("Track URI or Spotify track ID is required.")
    return f"spotify:track:{cleaned}"


def _market_params(market: str | None) -> dict[str, str]:
    if market is None:
        return {}
    value = market.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", value):
        raise ValueError("market must be a two-letter ISO country code.")
    return {"market": value}


@mcp.tool()
async def auth_status() -> str:
    """Show Spotify login readiness without exposing any credentials."""
    return json_result(auth.get_auth_status(auth.SCOPES))


@mcp.tool()
async def whoami() -> str:
    """Get the signed-in Spotify user's profile."""
    profile = await spotify_request(
        "GET", "/me", required_scopes={"user-read-private", "user-read-email"}
    )
    return json_result(profile)


@mcp.tool()
async def get_recently_played(
    limit: int = 50,
    after: int | None = None,
    before: int | None = None,
) -> str:
    """Get up to 50 recently played tracks for listening context."""
    bounded_int("limit", limit, 1, 50)
    if after is not None and before is not None:
        raise ValueError("Use either after or before, not both.")
    params: dict[str, int] = {"limit": limit}
    if after is not None:
        params["after"] = after
    if before is not None:
        params["before"] = before
    data = await spotify_request(
        "GET",
        "/me/player/recently-played",
        required_scopes={"user-read-recently-played"},
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def get_top_items(
    type: ItemType,
    time_range: TimeRange = "medium_term",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Get top artists or tracks over about 4 weeks, 6 months, or all time."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 100000)
    data = await spotify_request(
        "GET",
        f"/me/top/{type}",
        required_scopes={"user-top-read"},
        params={"time_range": time_range, "limit": limit, "offset": offset},
    )
    return json_result(data)


@mcp.tool()
async def get_saved_tracks(limit: int = 20, offset: int = 0, market: str | None = None) -> str:
    """Get a page of the current user's saved tracks."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 100000)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    params.update(_market_params(market))
    data = await spotify_request(
        "GET",
        "/me/tracks",
        required_scopes={"user-library-read"},
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def search_catalog(
    query: str,
    limit: int = 10,
    offset: int = 0,
    market: str | None = None,
) -> str:
    """Search Spotify tracks by title, artist, album, or Spotify query filters."""
    if not query.strip():
        raise ValueError("query is required.")
    bounded_int("limit", limit, 1, 10)
    bounded_int("offset", offset, 0, 1000)
    params: dict[str, object] = {
        "q": query.strip(),
        "type": "track",
        "limit": limit,
        "offset": offset,
    }
    params.update(_market_params(market))
    data = await spotify_request("GET", "/search", params=params)
    return json_result(data)


@mcp.tool()
async def discover_by_genre(
    genre: str,
    keywords: str = "",
    year_range: str | None = None,
    limit: int = 10,
    offset: int = 0,
    market: str | None = None,
) -> str:
    """Find tracks for a genre, optional vibe keywords, and optional release years."""
    if not genre.strip():
        raise ValueError("genre is required.")
    bounded_int("limit", limit, 1, 10)
    bounded_int("offset", offset, 0, 1000)
    safe_genre = genre.strip().replace('"', "")
    terms = [f'genre:"{safe_genre}"']
    if keywords.strip():
        terms.append(keywords.strip())
    if year_range:
        if not re.fullmatch(r"\d{4}(?:-\d{4})?", year_range):
            raise ValueError("year_range must be YYYY or YYYY-YYYY.")
        terms.append(f"year:{year_range}")
    params: dict[str, object] = {
        "q": " ".join(terms),
        "type": "track",
        "limit": limit,
        "offset": offset,
    }
    params.update(_market_params(market))
    data = await spotify_request("GET", "/search", params=params)
    return json_result(data)


@mcp.tool()
async def find_underground_music(
    vibe: str,
    genre: str | None = None,
    strategy: Literal["balanced", "low_popularity", "broad"] = "balanced",
    album_limit: int = 5,
    album_offset: int = 0,
    tracks_per_album: int = 10,
    market: str | None = None,
) -> str:
    """Find lesser-known albums for a vibe using low-popularity and broad searches."""
    if not vibe.strip():
        raise ValueError("vibe is required.")
    bounded_int("album_limit", album_limit, 1, 10)
    bounded_int("album_offset", album_offset, 0, 1000)
    bounded_int("tracks_per_album", tracks_per_album, 1, 50)

    query_terms = []
    if genre and genre.strip():
        safe_genre = genre.strip().replace('"', "")
        query_terms.append(f'genre:"{safe_genre}"')
    base_query = " ".join([*query_terms, vibe.strip()])
    queries = [base_query]
    if strategy == "low_popularity":
        queries = [f"{base_query} tag:hipster"]
    elif strategy == "balanced":
        # Hipster is an album-only low-popularity filter. Pair it with a normal
        # catalog search so the tool can also find niche matches outside that tag.
        queries = [f"{base_query} tag:hipster", base_query]

    market_params = _market_params(market)
    album_pages = []
    for query in queries:
        search = await spotify_request(
            "GET",
            "/search",
            params={
                "q": query,
                "type": "album",
                "limit": album_limit,
                "offset": album_offset,
                **market_params,
            },
        )
        album_pages.append((search or {}).get("albums", {}).get("items", []))

    if len(album_pages) == 2:
        ordered_albums = [album for pair in zip(*album_pages) for album in pair]
        ordered_albums.extend(album_pages[0][len(album_pages[1]) :])
        ordered_albums.extend(album_pages[1][len(album_pages[0]) :])
    else:
        ordered_albums = album_pages[0]
    albums = []
    seen_album_ids = set()
    for album in ordered_albums:
        album_id = album.get("id")
        if album_id and album_id not in seen_album_ids:
            seen_album_ids.add(album_id)
            albums.append(album)
        if len(albums) >= album_limit:
            break

    results = []
    for album in albums:
        album_id = album.get("id")
        if not album_id:
            continue
        tracks = await spotify_request(
            "GET",
            f"/albums/{_path_id(album_id, 'album_id')}/tracks",
            params={"limit": tracks_per_album, **_market_params(market)},
        )
        results.append(
            {
                "album": {
                    "id": album_id,
                    "name": album.get("name"),
                    "uri": album.get("uri"),
                    "release_date": album.get("release_date"),
                    "artists": album.get("artists", []),
                    "external_urls": album.get("external_urls", {}),
                },
                "tracks": (tracks or {}).get("items", []),
            }
        )
    return json_result(
        {
            "strategy": strategy,
            "albums": results,
            "offset": album_offset,
            "limit": album_limit,
        }
    )


@mcp.tool()
async def get_artist_new_releases(
    artist_id: str,
    include_groups: str = "album,single,compilation",
    limit: int = 20,
    offset: int = 0,
    market: str | None = None,
) -> str:
    """Get albums, singles, and compilations for an artist, newest first."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 1000)
    params: dict[str, object] = {
        "include_groups": include_groups,
        "limit": limit,
        "offset": offset,
    }
    params.update(_market_params(market))
    data = await spotify_request(
        "GET",
        f"/artists/{_path_id(artist_id, 'artist_id')}/albums",
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def get_album_tracks(
    album_id: str,
    limit: int = 50,
    offset: int = 0,
    market: str | None = None,
) -> str:
    """Get tracks from a Spotify album."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 1000)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    params.update(_market_params(market))
    data = await spotify_request(
        "GET",
        f"/albums/{_path_id(album_id, 'album_id')}/tracks",
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def get_user_playlists(limit: int = 20, offset: int = 0) -> str:
    """List the current user's playlists."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 100000)
    data = await spotify_request(
        "GET",
        "/me/playlists",
        required_scopes={"playlist-read-private", "playlist-read-collaborative"},
        params={"limit": limit, "offset": offset},
    )
    return json_result(data)


@mcp.tool()
async def get_playlist_tracks(
    playlist_id: str,
    limit: int = 20,
    offset: int = 0,
    market: str | None = None,
) -> str:
    """Get tracks and episodes from a playlist page."""
    bounded_int("limit", limit, 1, 50)
    bounded_int("offset", offset, 0, 100000)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    params.update(_market_params(market))
    data = await spotify_request(
        "GET",
        f"/playlists/{_path_id(playlist_id, 'playlist_id')}/items",
        required_scopes={"playlist-read-private"},
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def create_playlist(
    name: str,
    description: str = "",
    public: bool = False,
    collaborative: bool = False,
) -> str:
    """Create a playlist for the signed-in user; private by default."""
    if not name.strip():
        raise ValueError("name is required.")
    if collaborative and public:
        raise ValueError("A collaborative playlist must be private.")
    scope = "playlist-modify-public" if public else "playlist-modify-private"
    data = await spotify_request(
        "POST",
        "/me/playlists",
        required_scopes={scope},
        json_body={
            "name": name.strip(),
            "description": description,
            "public": public,
            "collaborative": collaborative,
        },
    )
    return json_result(data)


@mcp.tool()
async def add_to_playlist(
    playlist_id: str,
    track_uris: list[str],
    position: int | None = None,
) -> str:
    """Add track IDs or Spotify track URIs to a playlist, in batches of 100."""
    if not track_uris:
        raise ValueError("track_uris must contain at least one track.")
    uris = [_track_uri(uri) for uri in track_uris]
    playlist_path = f"/playlists/{_path_id(playlist_id, 'playlist_id')}/items"
    responses = []
    insert_position = position
    for start in range(0, len(uris), 100):
        batch = uris[start : start + 100]
        body: dict[str, object] = {"uris": batch}
        if insert_position is not None:
            body["position"] = insert_position
        response = await spotify_request(
            "POST",
            playlist_path,
            required_scopes={"playlist-modify-public", "playlist-modify-private"},
            json_body=body,
        )
        responses.append(response)
        if insert_position is not None:
            insert_position += len(batch)
    return json_result({"added": len(uris), "responses": responses})


@mcp.tool()
async def get_currently_playing(market: str | None = None) -> str:
    """Get the current playback item, or an empty result if nothing is playing."""
    params = _market_params(market)
    data = await spotify_request(
        "GET",
        "/me/player/currently-playing",
        required_scopes={"user-read-currently-playing"},
        params=params,
    )
    return json_result(data)


@mcp.tool()
async def add_to_queue(track_uri: str, device_id: str | None = None) -> str:
    """Add one Spotify track to the active playback queue (Premium required)."""
    params: dict[str, str] = {"uri": _track_uri(track_uri)}
    if device_id:
        params["device_id"] = device_id
    await spotify_request(
        "POST",
        "/me/player/queue",
        required_scopes={"user-modify-playback-state"},
        params=params,
    )
    return json_result({"queued": params["uri"]})


@mcp.tool()
async def start_playback(
    context_uri: str | None = None,
    track_uris: list[str] | None = None,
    device_id: str | None = None,
    position_ms: int | None = None,
) -> str:
    """Start a playlist/context or track list on an active Spotify device."""
    if context_uri and track_uris:
        raise ValueError("Use context_uri or track_uris, not both.")
    if position_ms is not None:
        bounded_int("position_ms", position_ms, 0, 2_147_483_647)
    body: dict[str, object] = {}
    if context_uri:
        body["context_uri"] = context_uri.strip()
    elif track_uris:
        body["uris"] = [_track_uri(uri) for uri in track_uris]
    if position_ms is not None:
        body["position_ms"] = position_ms
    params = {"device_id": device_id} if device_id else None
    await spotify_request(
        "PUT",
        "/me/player/play",
        required_scopes={"user-modify-playback-state"},
        params=params,
        json_body=body or None,
    )
    return json_result({"started": True, "context_uri": context_uri, "track_count": len(track_uris or [])})
