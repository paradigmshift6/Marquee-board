"""Resolve flight routes (origin/destination) from callsigns.

Uses a tiered approach:
1. OpenSky /routes endpoint (needs authentication)
2. Local disk cache from previous resolutions
3. Graceful degradation (no route)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..models import RouteInfo

if TYPE_CHECKING:
    from ..fetcher import OpenSkyFetcher
    from .airport_db import AirportDB

logger = logging.getLogger(__name__)


class RouteResolver:
    def __init__(
        self,
        cache_dir: Path,
        airport_db: "AirportDB",
        fetcher: Optional["OpenSkyFetcher"] = None,
        cache_ttl_hours: int = 24,
    ):
        self._cache_dir = cache_dir
        self._airport_db = airport_db
        self._fetcher = fetcher
        self._cache_ttl = cache_ttl_hours * 3600
        self._memory_cache: dict[str, RouteInfo] = {}
        self._disk_cache = self._load_disk_cache()
        self._failed_lookups: dict[str, float] = {}  # callsign -> timestamp
        self._fail_cooldown = 600  # Don't retry failed lookups for 10 min

    def resolve(self, callsign: str, icao24: str) -> Optional[RouteInfo]:
        # Memory cache (instant)
        if callsign in self._memory_cache:
            return self._memory_cache[callsign]

        # Disk cache
        if callsign in self._disk_cache:
            entry = self._disk_cache[callsign]
            age = time.time() - entry.get("_cached_at", 0)
            if age < self._cache_ttl:
                route = self._entry_to_route(entry)
                self._memory_cache[callsign] = route
                return route

        # Don't retry recently failed lookups
        if callsign in self._failed_lookups:
            if time.time() - self._failed_lookups[callsign] < self._fail_cooldown:
                return None

        # Tier 1: OpenSky /routes endpoint
        if self._fetcher and self._fetcher.authenticated:
            route = self._try_opensky_routes(callsign)
            if route:
                self._cache_route(callsign, route)
                return route

        # Mark as failed
        self._failed_lookups[callsign] = time.time()
        return None

    def _try_opensky_routes(self, callsign: str) -> Optional[RouteInfo]:
        data = self._fetcher.fetch_routes(callsign)
        if not data:
            return None

        route_list = data.get("route", [])
        if len(route_list) < 2:
            return None

        dep_icao = route_list[0]
        arr_icao = route_list[-1]

        dep_airport = self._airport_db.lookup(dep_icao)
        arr_airport = self._airport_db.lookup(arr_icao)

        return RouteInfo(
            departure_icao=dep_icao,
            departure_iata=dep_airport.iata if dep_airport else None,
            departure_city=dep_airport.city if dep_airport else None,
            arrival_icao=arr_icao,
            arrival_iata=arr_airport.iata if arr_airport else None,
            arrival_city=arr_airport.city if arr_airport else None,
        )

    def _cache_route(self, callsign: str, route: RouteInfo):
        self._memory_cache[callsign] = route
        self._disk_cache[callsign] = {
            "dep_icao": route.departure_icao,
            "dep_iata": route.departure_iata,
            "dep_city": route.departure_city,
            "arr_icao": route.arrival_icao,
            "arr_iata": route.arrival_iata,
            "arr_city": route.arrival_city,
            "_cached_at": time.time(),
        }
        self._save_disk_cache()

    def _entry_to_route(self, entry: dict) -> RouteInfo:
        return RouteInfo(
            departure_icao=entry.get("dep_icao"),
            departure_iata=entry.get("dep_iata"),
            departure_city=entry.get("dep_city"),
            arrival_icao=entry.get("arr_icao"),
            arrival_iata=entry.get("arr_iata"),
            arrival_city=entry.get("arr_city"),
        )

    def _load_disk_cache(self) -> dict:
        cache_file = self._cache_dir / "route_cache.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_disk_cache(self):
        cache_file = self._cache_dir / "route_cache.json"
        try:
            cache_file.write_text(json.dumps(self._disk_cache, indent=2))
        except OSError as e:
            logger.warning("Failed to save route cache: %s", e)
