"""Prueba de extremo a extremo del pipeline, sin tocar la red.

IMPORTANTE: las respuestas de Open-Meteo que se usan aquí son SINTÉTICAS.
Reproducen fielmente la ESTRUCTURA documentada de la API (nombres de claves,
unidades, formato de fecha) porque eso es lo que se está probando: el
plumbing. Los valores meteorológicos NO son una previsión y no salen de
aquí hacia el sitio publicado en ningún caso.

Los datos de marea, en cambio, son reales: extremos devueltos por la API
del IHM para Chipiona.
"""

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import build_data
import pytest
from lib import sources

RAIZ = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "render-fixture.json"

INICIO = date(2026, 8, 14)
HORAS = 5 * 24


def _horas_iso():
    t0 = datetime(INICIO.year, INICIO.month, INICIO.day)
    return [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(HORAS)]


def _forecast_sintetico(semilla: float):
    """Estructura idéntica a la de api.open-meteo.com/v1/forecast."""
    tiempos = _horas_iso()
    vel, raf, dirn, temp = [], [], [], []
    for i in range(HORAS):
        base = 17 + 9 * math.sin((i / 24 - 0.30) * 2 * math.pi) + 4 * math.sin(i / 47 + semilla)
        v = max(0.0, base)
        vel.append(round(v, 1))
        raf.append(round(v * 1.28, 1))
        dirn.append(round((235 + 30 * math.sin(i / 31 + semilla)) % 360, 1))
        temp.append(round(24 + 5 * math.sin((i / 24 - 0.4) * 2 * math.pi), 1))
    return {
        "latitude": 36.75, "longitude": -6.5,
        "utc_offset_seconds": 7200, "timezone": "Europe/Madrid",
        "hourly_units": {"time": "iso8601", "wind_speed_10m": "kn",
                         "wind_gusts_10m": "kn", "wind_direction_10m": "°",
                         "temperature_2m": "°C"},
        "hourly": {"time": tiempos, "wind_speed_10m": vel,
                   "wind_gusts_10m": raf, "wind_direction_10m": dirn,
                   "temperature_2m": temp},
    }


def _marine_sintetico(semilla: float):
    """Estructura idéntica a la de marine-api.open-meteo.com/v1/marine."""
    tiempos = _horas_iso()
    olas = [round(max(0.1, 0.75 + 0.5 * math.sin(i / 37 + semilla)), 2) for i in range(HORAS)]
    return {
        "hourly_units": {"time": "iso8601", "wave_height": "m"},
        "hourly": {"time": tiempos, "wave_height": olas,
                   "wave_period": [7.0] * HORAS, "wave_direction": [250] * HORAS,
                   "swell_wave_height": olas, "swell_wave_period": [9.0] * HORAS,
                   "swell_wave_direction": [255] * HORAS},
    }


# Extremos REALES del IHM para Chipiona (id 39), agosto 2026.
MAREA_REAL = {"mareas": {"copyright": "© Instituto Hidrográfico de la Marina (2026)",
                         "datos": {"marea": [
    {"fecha": "2026-08-13", "hora": "02:23", "altura": "3.301", "tipo": "pleamar"},
    {"fecha": "2026-08-13", "hora": "08:13", "altura": "0.556", "tipo": "bajamar"},
    {"fecha": "2026-08-13", "hora": "14:40", "altura": "3.605", "tipo": "pleamar"},
    {"fecha": "2026-08-13", "hora": "20:47", "altura": "0.474", "tipo": "bajamar"},
    {"fecha": "2026-08-14", "hora": "03:03", "altura": "3.441", "tipo": "pleamar"},
    {"fecha": "2026-08-14", "hora": "08:52", "altura": "0.451", "tipo": "bajamar"},
    {"fecha": "2026-08-14", "hora": "15:19", "altura": "3.745", "tipo": "pleamar"},
    {"fecha": "2026-08-14", "hora": "21:25", "altura": "0.379", "tipo": "bajamar"},
    {"fecha": "2026-08-15", "hora": "03:42", "altura": "3.529", "tipo": "pleamar"},
    {"fecha": "2026-08-15", "hora": "09:30", "altura": "0.400", "tipo": "bajamar"},
    {"fecha": "2026-08-15", "hora": "15:57", "altura": "3.812", "tipo": "pleamar"},
    {"fecha": "2026-08-15", "hora": "22:02", "altura": "0.350", "tipo": "bajamar"},
    {"fecha": "2026-08-16", "hora": "04:20", "altura": "3.540", "tipo": "pleamar"},
    {"fecha": "2026-08-16", "hora": "10:08", "altura": "0.420", "tipo": "bajamar"},
    {"fecha": "2026-08-16", "hora": "16:35", "altura": "3.780", "tipo": "pleamar"},
    {"fecha": "2026-08-16", "hora": "22:40", "altura": "0.400", "tipo": "bajamar"},
    {"fecha": "2026-08-17", "hora": "04:58", "altura": "3.470", "tipo": "pleamar"},
    {"fecha": "2026-08-17", "hora": "10:46", "altura": "0.510", "tipo": "bajamar"},
    {"fecha": "2026-08-17", "hora": "17:13", "altura": "3.660", "tipo": "pleamar"},
    {"fecha": "2026-08-17", "hora": "23:19", "altura": "0.520", "tipo": "bajamar"},
    {"fecha": "2026-08-18", "hora": "05:37", "altura": "3.320", "tipo": "pleamar"},
    {"fecha": "2026-08-18", "hora": "11:25", "altura": "0.680", "tipo": "bajamar"},
    {"fecha": "2026-08-18", "hora": "17:52", "altura": "3.480", "tipo": "pleamar"},
]}}}


@pytest.fixture
def sin_red(monkeypatch):
    contador = {"n": 0}

    def forecast(lat, lon, days, **kw):
        contador["n"] += 1
        return _forecast_sintetico(lat)

    def marine(lat, lon, days, **kw):
        return _marine_sintetico(lon)

    def marea(station_id, yyyymm, **kw):
        return MAREA_REAL

    monkeypatch.setattr(sources, "fetch_forecast", forecast)
    monkeypatch.setattr(sources, "fetch_marine", marine)
    monkeypatch.setattr(sources, "fetch_tide_month", marea)
    return contador


def test_construye_todos_los_spots_del_fichero(sin_red, tmp_path, monkeypatch):
    spots_cfg, alas_cfg = build_data.load_configs()
    defaults = spots_cfg["defaults"]

    for spot in spots_cfg["spots"]:
        salida = build_data.build_spot(spot, defaults, alas_cfg, 75, offline=False)
        assert salida["id"] == spot["id"]
        assert len(salida["dias"]) == build_data.DIAS, spot["id"]
        for d in salida["dias"]:
            assert d["estado"] in ("si", "justo", "no")
            assert d["titular"] and len(d["titular"]) > 4
            assert d["fiabilidad"] in ("alta", "media", "baja")


def test_ningun_spot_sin_calibrar_llega_a_si(sin_red):
    """La red de seguridad: si falta conocimiento local, no decimos que sí."""
    spots_cfg, alas_cfg = build_data.load_configs()
    for spot in spots_cfg["spots"]:
        salida = build_data.build_spot(spot, spots_cfg["defaults"], alas_cfg, 75, False)
        if not salida["calibracion"]["completo"]:
            estados = {d["estado"] for d in salida["dias"]}
            assert "si" not in estados, f"{spot['id']} dice 'sí' sin estar calibrado"


def test_el_json_no_contiene_marcadores_pendientes(sin_red, tmp_path, monkeypatch):
    monkeypatch.setattr(build_data, "CACHE", tmp_path / "cache")
    salida = tmp_path / "data.json"
    monkeypatch.setattr("sys.argv", ["build_data.py", "--salida", str(salida)])
    assert build_data.main() == 0
    texto = salida.read_text(encoding="utf-8")
    assert "PENDIENTE_ROBE" not in texto, \
        "los marcadores internos no deben filtrarse al sitio publicado"
    datos = json.loads(texto)
    assert datos["generado"] and datos["spots"] and not datos["fallos"]


def test_genera_fixture_de_render(sin_red, monkeypatch):
    """Genera el fixture que usa la prueba visual. NO se despliega."""
    monkeypatch.setattr("sys.argv",
                        ["build_data.py", "--salida", str(FIXTURE)])
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    assert build_data.main() == 0
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    datos["_AVISO"] = ("FIXTURE DE PRUEBA. Viento y oleaje SINTÉTICOS, "
                       "sólo para comprobar el render. No es una previsión.")
    FIXTURE.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def test_si_un_spot_falla_se_conservan_sus_datos_previos(sin_red, tmp_path, monkeypatch):
    """Datos viejos etiquetados como viejos son mejores que un hueco.
    Lo que nunca se hace es presentarlos como frescos."""
    monkeypatch.setattr(build_data, "CACHE", tmp_path / "cache")
    salida = tmp_path / "data.json"

    monkeypatch.setattr("sys.argv", ["build_data.py", "--salida", str(salida)])
    assert build_data.main() == 0
    n_spots = len(json.loads(salida.read_text(encoding="utf-8"))["spots"])

    # Ahora Open-Meteo se cae para todos los spots.
    def revienta(*a, **k):
        raise build_data.sources.FetchError("503 desde Open-Meteo")
    monkeypatch.setattr(build_data.sources, "fetch_forecast", revienta)

    assert build_data.main() == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert len(datos["spots"]) == n_spots, "no se pierde ningún spot"
    assert len(datos["fallos"]) == n_spots
    for s in datos["spots"]:
        assert s["obsoleto"] is True
        assert any("última actualización correcta" in i for i in s["incidencias"])


def test_sin_datos_previos_y_con_todo_caido_no_se_publica_nada(sin_red, tmp_path, monkeypatch):
    monkeypatch.setattr(build_data, "CACHE", tmp_path / "cache")
    salida = tmp_path / "nunca.json"

    def revienta(*a, **k):
        raise build_data.sources.FetchError("503 desde Open-Meteo")
    monkeypatch.setattr(build_data.sources, "fetch_forecast", revienta)
    monkeypatch.setattr("sys.argv", ["build_data.py", "--salida", str(salida)])

    assert build_data.main() == 1
    assert not salida.exists(), "mejor no publicar que publicar un sitio vacío"
