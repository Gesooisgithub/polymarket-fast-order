"""
Event fetcher module for Polymarket football matches.

Given a Polymarket event URL (e.g., https://polymarket.com/sports/sea/sea-gen-tor-2026-02-22),
fetches the event from the Gamma API and extracts the 3 football markets
(Team1 win, Draw, Team2 win) with their condition IDs.

Supported URL formats:
    https://polymarket.com/event/<slug>
    https://polymarket.com/event/<slug>/<sub-slug>
    https://polymarket.com/sports/<league>/<slug>
"""

from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx

from market_info import MarketClient, MarketData, GammaAPIError


def extract_slug_from_url(url: str) -> str:
    """
    Extract the event slug from a Polymarket URL.

    Handles:
        /event/<slug>              -> slug
        /event/<slug>/<sub-slug>   -> slug
        /sports/<league>/<slug>    -> slug

    Args:
        url: Polymarket event URL

    Returns:
        Event slug string

    Raises:
        ValueError if URL format is not recognized
    """
    parsed = urlparse(url.strip())
    path = parsed.path.strip("/")
    parts = path.split("/")

    if len(parts) >= 2 and parts[0] == "event":
        # /event/<slug> or /event/<slug>/<sub>
        return parts[1]
    elif len(parts) >= 3 and parts[0] == "sports":
        # /sports/<league>/<slug>
        return parts[2]
    elif len(parts) == 1 and parts[0]:
        # User pasted just the slug directly
        return parts[0]
    else:
        raise ValueError(
            f"Unrecognized URL format: {url}\n"
            "Expected: https://polymarket.com/event/<slug> or "
            "https://polymarket.com/sports/<league>/<slug>"
        )


def fetch_event_markets(
    slug: str,
    http_client: httpx.Client,
    gamma_host: str = "https://gamma-api.polymarket.com",
) -> dict:
    """
    Fetch event data from Gamma API by slug.

    Args:
        slug: Event slug (e.g., 'sea-gen-tor-2026-02-22')
        http_client: Existing httpx.Client to reuse
        gamma_host: Gamma API base URL

    Returns:
        Event dict with nested 'markets' list

    Raises:
        GammaAPIError if request fails or event not found
    """
    url = f"{gamma_host}/events"
    params = {"slug": slug}

    try:
        response = http_client.get(url, params=params)

        if response.status_code != 200:
            raise GammaAPIError(f"Gamma API returned status {response.status_code}")

        data = response.json()

        if not data:
            raise GammaAPIError(f"No event found for slug: {slug}")

        event = data[0] if isinstance(data, list) else data
        return event

    except httpx.RequestError as e:
        raise GammaAPIError(f"Network error fetching event: {e}")


def parse_football_event(
    event: dict,
    market_client: MarketClient,
) -> Tuple[MarketData, MarketData, MarketData, str, str]:
    """
    Parse a football event into 3 MarketData objects.

    Uses 'groupItemTitle' to identify:
        - Team markets: groupItemTitle = team name (e.g., "Genoa CFC")
        - Draw market:  groupItemTitle starts with "Draw"

    Uses event 'title' ("Team1 vs. Team2") to determine team order.

    Args:
        event: Event dict from Gamma API
        market_client: MarketClient for fetching full MarketData via CLOB

    Returns:
        Tuple of (team1_market, draw_market, team2_market, team1_name, team2_name)

    Raises:
        GammaAPIError if markets can't be identified
    """
    title = event.get("title", "")
    markets_raw = event.get("markets", [])

    if not markets_raw:
        raise GammaAPIError(f"Event has no markets: {title}")

    # Filter to only active, non-closed markets
    active_markets = [
        m for m in markets_raw
        if m.get("active", False) and not m.get("closed", True)
    ]

    if len(active_markets) < 3:
        # Fallback: use all markets if filtering was too aggressive
        active_markets = markets_raw

    if len(active_markets) < 3:
        raise GammaAPIError(
            f"Expected 3 markets (Team1, Draw, Team2), found {len(active_markets)}"
        )

    # Extract team names from event title ("Team1 vs. Team2")
    team1_name = ""
    team2_name = ""
    if " vs. " in title:
        parts = title.split(" vs. ", 1)
        team1_name = parts[0].strip()
        team2_name = parts[1].strip()
    elif " vs " in title:
        parts = title.split(" vs ", 1)
        team1_name = parts[0].strip()
        team2_name = parts[1].strip()

    # Classify each market using groupItemTitle
    draw_raw = None
    team1_raw = None
    team2_raw = None

    for m in active_markets:
        group_title = m.get("groupItemTitle", "")

        if group_title.lower().startswith("draw"):
            draw_raw = m
        elif group_title == team1_name:
            team1_raw = m
        elif group_title == team2_name:
            team2_raw = m

    # Fallback: if groupItemTitle matching failed, use question text
    if not draw_raw or not team1_raw or not team2_raw:
        for m in active_markets:
            question = m.get("question", "").lower()
            group_title = m.get("groupItemTitle", "")

            if not draw_raw and "draw" in question:
                draw_raw = m
            elif not team1_raw and team1_name.lower() in question and "draw" not in question:
                team1_raw = m
            elif not team2_raw and team2_name.lower() in question and "draw" not in question:
                team2_raw = m

    if not team1_raw or not draw_raw or not team2_raw:
        # Last resort: if no team names found, assign by order
        # Typically: [team1_win, draw, team2_win] or similar
        non_draw = [m for m in active_markets if "draw" in m.get("question", "").lower()]
        teams = [m for m in active_markets if "draw" not in m.get("question", "").lower()]

        if len(non_draw) >= 1:
            draw_raw = non_draw[0]
        if len(teams) >= 2:
            team1_raw = teams[0]
            team2_raw = teams[1]
            if not team1_name:
                team1_name = team1_raw.get("groupItemTitle", "Team 1")
            if not team2_name:
                team2_name = team2_raw.get("groupItemTitle", "Team 2")

    if not team1_raw or not draw_raw or not team2_raw:
        raise GammaAPIError(
            "Could not identify Team1, Draw, and Team2 markets from event.\n"
            f"Event title: {title}\n"
            f"Markets found: {[m.get('groupItemTitle', m.get('question', '?')) for m in active_markets]}"
        )

    # Fetch full MarketData from CLOB for each condition ID
    team1_cid = team1_raw.get("conditionId", "")
    draw_cid = draw_raw.get("conditionId", "")
    team2_cid = team2_raw.get("conditionId", "")

    team1_market = market_client.get_market_by_condition_id(team1_cid)
    if not team1_market:
        raise GammaAPIError(f"Could not fetch market data for {team1_name} (conditionId: {team1_cid})")

    draw_market = market_client.get_market_by_condition_id(draw_cid)
    if not draw_market:
        raise GammaAPIError(f"Could not fetch market data for Draw (conditionId: {draw_cid})")

    team2_market = market_client.get_market_by_condition_id(team2_cid)
    if not team2_market:
        raise GammaAPIError(f"Could not fetch market data for {team2_name} (conditionId: {team2_cid})")

    # Fallback team names
    if not team1_name:
        team1_name = "Team 1"
    if not team2_name:
        team2_name = "Team 2"

    return team1_market, draw_market, team2_market, team1_name, team2_name


def fetch_football_markets_from_url(
    url: str,
    market_client: MarketClient,
    gamma_host: str = "https://gamma-api.polymarket.com",
) -> Tuple[MarketData, MarketData, MarketData, str, str]:
    """
    Main entry point: URL -> 3 MarketData objects + team names.

    Takes a Polymarket event URL, fetches the event via Gamma API,
    identifies the 3 football markets, and returns full MarketData
    objects ready for the Trader.

    Args:
        url: Polymarket event URL
        market_client: Existing MarketClient instance
        gamma_host: Gamma API base URL

    Returns:
        Tuple of (team1_market, draw_market, team2_market, team1_name, team2_name)

    Raises:
        ValueError: If URL format is invalid
        GammaAPIError: If API call fails or markets can't be identified
    """
    slug = extract_slug_from_url(url)
    event = fetch_event_markets(slug, market_client._http_client, gamma_host)
    return parse_football_event(event, market_client)
