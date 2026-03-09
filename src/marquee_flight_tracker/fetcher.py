import logging
import time
from typing import List, Optional

import httpx

from .models import BoundingBox, RawAircraftState

logger = logging.getLogger(__name__)

OPENSKY_BASE = "https://opensky-network.org/api"


class OpenSkyFetcher:
    def __init__(
        self,
        bbox: BoundingBox,
        min_interval: float = 10.0,
        timeout: float = 15.0,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._bbox = bbox
        self._min_interval = min_interval
        self._timeout = timeout
        self._last_request_time: float = 0.0
        self._backoff: float = 0.0

        auth = (username, password) if username and password else None
        self._client = httpx.Client(timeout=timeout, auth=auth)
        self._authenticated = auth is not None

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def fetch(self) -> List[RawAircraftState]:
        """Fetch current aircraft states within the bounding box."""
        self._enforce_rate_limit()

        params = {
            "lamin": self._bbox.lat_min,
            "lomin": self._bbox.lon_min,
            "lamax": self._bbox.lat_max,
            "lomax": self._bbox.lon_max,
        }

        try:
            resp = self._client.get(f"{OPENSKY_BASE}/states/all", params=params)
            self._last_request_time = time.monotonic()

            if resp.status_code == 429:
                self._backoff = min(max(self._backoff * 2, 30), 300)
                logger.warning("Rate limited. Backing off %.0fs", self._backoff)
                return []

            resp.raise_for_status()
            self._backoff = 0.0
            data = resp.json()

        except httpx.TimeoutException:
            logger.warning("OpenSky request timed out")
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("OpenSky HTTP error: %s", e)
            return []
        except httpx.RequestError as e:
            logger.warning("OpenSky request failed: %s", e)
            return []

        states = data.get("states") or []
        results = []
        for s in states:
            callsign = s[1].strip() if s[1] else None
            if not callsign:
                continue
            results.append(self._parse_state(s, callsign))

        return results

    def fetch_routes(self, callsign: str) -> Optional[dict]:
        """Fetch route info for a callsign (requires authentication)."""
        if not self._authenticated:
            return None

        try:
            resp = self._client.get(
                f"{OPENSKY_BASE}/routes",
                params={"callsign": callsign},
            )
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.debug("Route lookup failed for %s: %s", callsign, e)

        return None

    def _enforce_rate_limit(self):
        wait = self._min_interval + self._backoff
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < wait:
            time.sleep(wait - elapsed)

    @staticmethod
    def _parse_state(s: list, callsign: str) -> RawAircraftState:
        return RawAircraftState(
            icao24=s[0],
            callsign=callsign,
            origin_country=s[2],
            longitude=s[5],
            latitude=s[6],
            baro_altitude=s[7],
            on_ground=s[8],
            velocity=s[9],
            true_track=s[10],
            vertical_rate=s[11],
            geo_altitude=s[13],
            squawk=s[14] if len(s) > 14 else None,
            category=s[17] if len(s) > 17 else None,
        )

    def close(self):
        self._client.close()
