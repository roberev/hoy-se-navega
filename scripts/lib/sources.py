"""Acceso a las APIs externas, con caché en disco y reintentos.

Endpoints verificados en docs/verificacion-apis.md. No se inventa ningún
parámetro: todos salen de la documentación oficial y de respuestas reales.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "hoy-se-navega/1.0 (+proyecto personal no comercial)"

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
IHM_URL = "https://ideihm.covam.es/api-ihm/getmarea"

HOURLY_FORECAST = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
]

HOURLY_MARINE = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "swell_wave_period",
    "swell_wave_direction",
]


class FetchError(RuntimeError):
    pass


def _get(url: str, params: dict, *, cache_dir: Path | None, ttl: int,
         retries: int = 3, timeout: int = 30) -> dict:
    query = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{query}"

    cache_file = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(full.encode()).hexdigest()[:32]
        cache_file = cache_dir / f"{key}.json"
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < ttl:
            return json.loads(cache_file.read_text(encoding="utf-8"))

    last_error = None
    for intento in range(retries):
        try:
            req = urllib.request.Request(
                full,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8"))
            if cache_file is not None:
                cache_file.write_text(json.dumps(data), encoding="utf-8")
            return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if intento < retries - 1:
                time.sleep(2 ** intento)

    raise FetchError(f"No se pudo obtener {url}: {last_error}")


def fetch_forecast(lat: float, lon: float, days: int, *,
                   cache_dir: Path | None = None, ttl: int = 1800) -> dict:
    """Open-Meteo Forecast API. Viento en NUDOS (wind_speed_unit=kn)."""
    return _get(FORECAST_URL, {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ",".join(HOURLY_FORECAST),
        "wind_speed_unit": "kn",
        "timezone": "Europe/Madrid",
        "forecast_days": days,
    }, cache_dir=cache_dir, ttl=ttl)


def fetch_marine(lat: float, lon: float, days: int, *,
                 cache_dir: Path | None = None, ttl: int = 1800) -> dict:
    """Open-Meteo Marine API. Altura de ola significante en metros."""
    return _get(MARINE_URL, {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ",".join(HOURLY_MARINE),
        "timezone": "Europe/Madrid",
        "forecast_days": days,
    }, cache_dir=cache_dir, ttl=ttl)


def fetch_tide_month(station_id: int, yyyymm: str, *,
                     cache_dir: Path | None = None, ttl: int = 86400) -> dict:
    """Predicción de mareas del IHM para un mes completo.

    Devuelve SÓLO extremos (pleamares y bajamares). La curva horaria se
    interpola en lib/tides.py.
    """
    return _get(IHM_URL, {
        "request": "gettide",
        "format": "json",
        "id": station_id,
        "month": yyyymm,
    }, cache_dir=cache_dir, ttl=ttl)


def fetch_tide_stations(*, cache_dir: Path | None = None,
                        ttl: int = 604800) -> dict:
    return _get(IHM_URL, {"request": "getlist", "format": "json"},
                cache_dir=cache_dir, ttl=ttl)
