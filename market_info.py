"""
Market information module for fetching data from Polymarket APIs.
Uses CLOB API for condition_id lookups (more reliable for sports markets).
Uses Gamma API for search functionality.
"""

import json
from dataclasses import dataclass
from typing import Optional, List

import httpx


@dataclass
class MarketData:
    """Container for market information."""
    condition_id: str
    question: str
    slug: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    outcomes: List[str]
    active: bool
    closed: bool
    # Required for order creation (from CLOB API)
    tick_size: str = "0.01"  # Default tick size
    neg_risk: bool = False   # Whether this is a neg risk market


class GammaAPIError(Exception):
    """Exception for API errors."""
    pass


class MarketClient:
    """
    Client for Polymarket APIs to fetch market metadata.

    Uses two APIs:
    - CLOB API: For direct condition_id lookups (reliable for sports)
    - Gamma API: For search functionality
    """

    def __init__(
        self,
        clob_host: str = "https://clob.polymarket.com",
        gamma_host: str = "https://gamma-api.polymarket.com"
    ):
        """
        Initialize the market client.

        Args:
            clob_host: CLOB API endpoint URL
            gamma_host: Gamma API endpoint URL
        """
        self.clob_host = clob_host
        self.gamma_host = gamma_host
        self._http_client = httpx.Client(timeout=10.0)

    def get_market_by_condition_id(self, condition_id: str) -> Optional[MarketData]:
        """
        Fetch market data using condition_id via CLOB API.

        The CLOB API provides reliable data including:
        - Token IDs for YES/NO outcomes
        - Current prices
        - Market status

        Args:
            condition_id: The market's condition ID (e.g., '0x1234...')

        Returns:
            MarketData object or None if not found

        Raises:
            GammaAPIError: If API request fails
        """
        url = f"{self.clob_host}/markets/{condition_id}"

        try:
            response = self._http_client.get(url)

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                raise GammaAPIError(f"CLOB API returned status {response.status_code}: {response.text}")

            data = response.json()
            return self._parse_clob_market(data, condition_id)

        except httpx.RequestError as e:
            raise GammaAPIError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            raise GammaAPIError(f"Invalid JSON response: {e}")

    def _parse_clob_market(self, data: dict, condition_id: str) -> Optional[MarketData]:
        """
        Parse CLOB API response into MarketData.

        CLOB API returns tokens in format:
        {
            "tokens": [
                {"token_id": "123...", "outcome": "Yes", "price": 0.45},
                {"token_id": "456...", "outcome": "No", "price": 0.55}
            ]
        }
        """
        try:
            tokens = data.get("tokens", [])

            if not tokens or len(tokens) < 2:
                return None

            # Find YES and NO tokens
            yes_token = None
            no_token = None

            for token in tokens:
                outcome = token.get("outcome", "").lower()
                if outcome == "yes":
                    yes_token = token
                elif outcome == "no":
                    no_token = token

            if not yes_token or not no_token:
                # Fallback: assume first is Yes, second is No
                yes_token = tokens[0]
                no_token = tokens[1]

            return MarketData(
                condition_id=condition_id,
                question=data.get("question", "Unknown Market"),
                slug=data.get("market_slug", ""),
                yes_token_id=yes_token.get("token_id", ""),
                no_token_id=no_token.get("token_id", ""),
                yes_price=float(yes_token.get("price", 0)),
                no_price=float(no_token.get("price", 0)),
                outcomes=["Yes", "No"],
                active=data.get("active", True),
                closed=data.get("closed", False),
                tick_size=str(data.get("minimum_tick_size", "0.01")),
                neg_risk=data.get("neg_risk", False)
            )

        except (IndexError, KeyError, TypeError) as e:
            return None

    def get_market_by_slug(self, slug: str) -> Optional[MarketData]:
        """
        Fetch market data using URL slug via Gamma API.

        Args:
            slug: The market's URL slug (e.g., 'will-trump-win-2024')

        Returns:
            MarketData object or None if not found
        """
        params = {"slug": slug}

        try:
            response = self._http_client.get(
                f"{self.gamma_host}/markets",
                params=params
            )

            if response.status_code != 200:
                raise GammaAPIError(f"API returned status {response.status_code}")

            markets = response.json()

            if not markets:
                return None

            market = markets[0] if isinstance(markets, list) else markets

            # Get condition_id and fetch from CLOB for accurate data
            condition_id = market.get("conditionId", market.get("condition_id"))
            if condition_id:
                return self.get_market_by_condition_id(condition_id)

            return self._parse_gamma_market(market)

        except httpx.RequestError as e:
            raise GammaAPIError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            raise GammaAPIError(f"Invalid JSON response: {e}")

    def search_markets(self, query: str, limit: int = 10) -> List[MarketData]:
        """
        Search for markets by question text via Gamma API.

        Args:
            query: Search term to match against market questions
            limit: Maximum number of results to return

        Returns:
            List of matching MarketData objects
        """
        params = {
            "limit": 100,
            "active": "true",
            "closed": "false"
        }

        try:
            response = self._http_client.get(
                f"{self.gamma_host}/markets",
                params=params
            )

            if response.status_code != 200:
                raise GammaAPIError(f"API returned status {response.status_code}")

            markets = response.json()
            results = []

            query_lower = query.lower()
            for market in markets:
                question = market.get("question", "")
                if query_lower in question.lower():
                    condition_id = market.get("conditionId", market.get("condition_id"))
                    if condition_id:
                        try:
                            parsed = self.get_market_by_condition_id(condition_id)
                            if parsed:
                                results.append(parsed)
                        except Exception:
                            continue

                    if len(results) >= limit:
                        break

            return results

        except httpx.RequestError as e:
            raise GammaAPIError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            raise GammaAPIError(f"Invalid JSON response: {e}")

    def _parse_gamma_market(self, market: dict) -> Optional[MarketData]:
        """
        Parse Gamma API response into MarketData (fallback).
        """
        try:
            clob_token_ids_raw = market.get("clobTokenIds", "[]")
            outcome_prices_raw = market.get("outcomePrices", "[]")

            if isinstance(clob_token_ids_raw, str):
                clob_token_ids = json.loads(clob_token_ids_raw)
            else:
                clob_token_ids = clob_token_ids_raw

            if isinstance(outcome_prices_raw, str):
                outcome_prices = json.loads(outcome_prices_raw)
            else:
                outcome_prices = outcome_prices_raw

            outcomes = market.get("outcomes", ["Yes", "No"])
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            if not clob_token_ids or len(clob_token_ids) < 2:
                return None

            yes_index = 0
            no_index = 1
            for i, outcome in enumerate(outcomes):
                if outcome.lower() == "yes":
                    yes_index = i
                elif outcome.lower() == "no":
                    no_index = i

            yes_price = 0.5
            no_price = 0.5
            if outcome_prices and len(outcome_prices) > max(yes_index, no_index):
                yes_price = float(outcome_prices[yes_index])
                no_price = float(outcome_prices[no_index])

            return MarketData(
                condition_id=market.get("conditionId", market.get("condition_id", "")),
                question=market.get("question", "Unknown Market"),
                slug=market.get("slug", ""),
                yes_token_id=clob_token_ids[yes_index],
                no_token_id=clob_token_ids[no_index],
                yes_price=yes_price,
                no_price=no_price,
                outcomes=outcomes,
                active=market.get("active", False),
                closed=market.get("closed", True),
                tick_size=str(market.get("minimum_tick_size", market.get("minimumTickSize", "0.01"))),
                neg_risk=market.get("neg_risk", market.get("negRisk", False))
            )

        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            return None

    def close(self):
        """Clean up HTTP client resources."""
        self._http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Alias for backward compatibility
GammaClient = MarketClient