#!/usr/bin/env python3
"""Verificación viva de las APIs. Se ejecuta en CI antes de construir nada.

No comprueba que "el código funciona": comprueba que las APIs siguen
devolviendo lo que dijimos que devuelven. Si Open-Meteo renombra una
variable o el IHM cambia el formato, esto falla ruidosamente en vez de
publicar un sitio con datos silenciosamente rotos.

Incluye un contraste independiente de la marea: se compara la FASE de la
predicción del IHM con la serie `sea_level_height_msl` de Open-Meteo. Son
dos modelos distintos; si las pleamares no coinciden aproximadamente, hay
un problema de zona horaria o de estación y hay que mirarlo.

Uso:  python scripts/verify_apis.py            (informe legible)
      python scripts/verify_apis.py --json     (para máquinas)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import itertools

from lib import sources
from lib.tides import TZ, TideCurve, parse_ihm_month

CHIPIONA = (36.7369, -6.4386)
ESTACION_CHIPIONA = 39

resultados: list[dict] = []


def comprobar(nombre: str, fn):
    try:
        detalle = fn()
        resultados.append({"prueba": nombre, "ok": True, "detalle": detalle})
        print(f"  OK   {nombre}\n       {detalle}")
    except Exception as exc:  # noqa: BLE001
        resultados.append({"prueba": nombre, "ok": False, "detalle": str(exc)})
        print(f"  FALLA {nombre}\n       {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------

def forecast_tiene_las_variables():
    d = sources.fetch_forecast(*CHIPIONA, 5, cache_dir=None)
    h = d["hourly"]
    faltan = [v for v in sources.HOURLY_FORECAST if v not in h]
    if faltan:
        raise AssertionError(f"faltan variables: {faltan}")
    if d["hourly_units"]["wind_speed_10m"] != "kn":
        raise AssertionError(
            f"wind_speed_unit=kn no respetado: {d['hourly_units']['wind_speed_10m']}")
    if len(h["time"]) < 24 * 5:
        raise AssertionError(f"sólo {len(h['time'])} horas, esperábamos 120")
    nulos = sum(1 for v in h["wind_speed_10m"] if v is None)
    return (f"{len(h['time'])} horas, unidades {d['hourly_units']['wind_speed_10m']}, "
            f"{nulos} nulos, tz {d['timezone']}")


def marine_tiene_oleaje():
    d = sources.fetch_marine(*CHIPIONA, 5, cache_dir=None)
    h = d["hourly"]
    if "wave_height" not in h:
        raise AssertionError("no viene wave_height")
    validos = [v for v in h["wave_height"] if v is not None]
    if not validos:
        raise AssertionError(
            "wave_height llega entero a null: el punto puede caer en tierra "
            "para la malla marina. Habría que desplazar las coordenadas mar adentro.")
    return (f"{len(validos)}/{len(h['wave_height'])} horas con dato, "
            f"rango {min(validos):.2f}–{max(validos):.2f} m")


def ihm_lista_las_estaciones():
    d = sources.fetch_tide_stations(cache_dir=None)
    puertos = d["estaciones"]["puertos"]
    ids = {int(p["id"]) for p in puertos}
    if ESTACION_CHIPIONA not in ids:
        raise AssertionError("la estación de Chipiona (39) ya no está en la lista")
    return f"{len(puertos)} estaciones, Chipiona presente"


def ihm_devuelve_extremos():
    mes = date.today().strftime("%Y%m")
    d = sources.fetch_tide_month(ESTACION_CHIPIONA, mes, cache_dir=None)
    extremos = parse_ihm_month(d)
    if len(extremos) < 100:
        raise AssertionError(f"sólo {len(extremos)} extremos en el mes")
    alturas = [e.height_m for e in extremos]
    if min(alturas) < -1 or max(alturas) > 6:
        raise AssertionError(f"alturas fuera de lo razonable: {min(alturas)}–{max(alturas)}")
    tipos = {e.kind for e in extremos}
    if tipos != {"pleamar", "bajamar"}:
        raise AssertionError(f"tipos inesperados: {tipos}")
    return (f"{len(extremos)} extremos en {mes}, "
            f"alturas {min(alturas):.2f}–{max(alturas):.2f} m sobre el cero del puerto")


def las_pleamares_se_alternan():
    """Sanidad interna: pleamar y bajamar deben alternarse siempre."""
    mes = date.today().strftime("%Y%m")
    extremos = parse_ihm_month(sources.fetch_tide_month(ESTACION_CHIPIONA, mes, cache_dir=None))
    for a, b in itertools.pairwise(extremos):
        if a.kind == b.kind:
            raise AssertionError(f"dos {a.kind} seguidas: {a.when} y {b.when}")
        if b.when <= a.when:
            raise AssertionError(f"extremos desordenados: {a.when} y {b.when}")
    return f"{len(extremos)} extremos alternando correctamente"


def la_fase_de_marea_cuadra_con_open_meteo():
    """Contraste independiente contra otro modelo.

    Open-Meteo sirve `sea_level_height_msl` (modelo SMOC de Copernicus, malla
    de ~8 km). Su AMPLITUD no es fiable en la costa y su datum es distinto,
    por eso NO se usa como fuente. Pero su FASE sirve para detectar un
    desfase horario groso en la lectura del IHM.
    """
    d = sources._get(sources.MARINE_URL, {
        "latitude": f"{CHIPIONA[0]:.4f}", "longitude": f"{CHIPIONA[1]:.4f}",
        "hourly": "sea_level_height_msl", "timezone": "Europe/Madrid",
        "forecast_days": 3,
    }, cache_dir=None, ttl=0)

    serie = d["hourly"].get("sea_level_height_msl")
    if not serie or all(v is None for v in serie):
        return ("Open-Meteo no da sea_level_height_msl en este punto; "
                "no se puede contrastar la fase (no es bloqueante)")

    tiempos = [datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=TZ)
               for t in d["hourly"]["time"]]
    pares = [(t, v) for t, v in zip(tiempos, serie) if v is not None]

    mes = date.today().strftime("%Y%m")
    curva = TideCurve(parse_ihm_month(sources.fetch_tide_month(
        ESTACION_CHIPIONA, mes, cache_dir=None)))

    # Máximo local de Open-Meteo en el segundo día, contra la pleamar del IHM.
    manana = date.today() + timedelta(days=1)
    delelia = [(t, v) for t, v in pares if t.date() == manana]
    if not delelia:
        raise AssertionError("Open-Meteo no cubre mañana")
    t_pico = max(delelia, key=lambda x: x[1])[0]

    pleamar = curva.nearest_extreme(t_pico, "pleamar")
    if pleamar is None:
        raise AssertionError("el IHM no da pleamar cerca de esa hora")

    desfase_h = abs((t_pico - pleamar.when).total_seconds()) / 3600.0
    texto = (f"pico Open-Meteo {t_pico:%d/%m %H:%M} vs pleamar IHM "
             f"{pleamar.when:%d/%m %H:%M} → {desfase_h:.1f} h de diferencia")
    if desfase_h > 2.0:
        raise AssertionError(
            texto + ". Más de 2 h de desfase: revisa la zona horaria del IHM "
            "o el parámetro offset_minutes en lib/tides.py")
    return texto + " (dentro de lo esperable para una malla de 8 km)"


def los_spots_tienen_estacion_valida():
    import yaml
    raiz = Path(__file__).resolve().parent.parent
    spots = yaml.safe_load((raiz / "config" / "spots.yaml").read_text(encoding="utf-8"))
    disponibles = {int(p["id"]): p["puerto"]
                   for p in sources.fetch_tide_stations(cache_dir=None)["estaciones"]["puertos"]}
    malos = []
    for s in spots["spots"]:
        sid = ((s.get("marea") or {}).get("estacion_ihm") or {}).get("id")
        if sid is None or int(sid) not in disponibles:
            malos.append(s["id"])
    if malos:
        raise AssertionError(f"spots con estación de marea inválida: {malos}")
    return f"{len(spots['spots'])} spots, todos con estación IHM existente"


PRUEBAS = [
    ("Open-Meteo Forecast: variables y unidades", forecast_tiene_las_variables),
    ("Open-Meteo Marine: oleaje en el punto", marine_tiene_oleaje),
    ("IHM: lista de estaciones", ihm_lista_las_estaciones),
    ("IHM: extremos de marea del mes", ihm_devuelve_extremos),
    ("IHM: coherencia interna de la serie", las_pleamares_se_alternan),
    ("Contraste de fase de marea entre modelos", la_fase_de_marea_cuadra_con_open_meteo),
    ("spots.yaml: estaciones de marea existentes", los_spots_tienen_estacion_valida),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    print("Verificando APIs contra las fuentes reales…\n")
    for nombre, fn in PRUEBAS:
        comprobar(nombre, fn)

    fallos = [r for r in resultados if not r["ok"]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")

    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=1))
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
