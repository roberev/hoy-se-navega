#!/usr/bin/env python3
"""Construye site/data.json: previsión + veredictos para todos los spots.

Se ejecuta por cron (GitHub Actions). El sitio es estático y sólo lee ese
JSON. Si este script falla, NO se escribe nada: el sitio sigue sirviendo el
último JSON válido, y la interfaz muestra su hora de actualización para que
nadie confunda datos viejos con datos frescos.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from lib import sources
from lib.day import summarise_day
from lib.tides import TZ, TideCurve, parse_ihm_month
from lib.verdict import assess_hour, is_pending

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
SALIDA = RAIZ / "site" / "data.json"
CACHE = RAIZ / ".cache"

DIAS = 5
PESO_POR_DEFECTO = 75.0


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_configs():
    spots = yaml.safe_load((CONFIG / "spots.yaml").read_text(encoding="utf-8"))
    alas = yaml.safe_load((CONFIG / "alas.yaml").read_text(encoding="utf-8"))
    return spots, alas


def months_needed(start: date, days: int) -> list[str]:
    """Meses YYYYMM que hay que pedir al IHM, con un día de margen por lado."""
    vistos: list[str] = []
    d = start - timedelta(days=1)
    end = start + timedelta(days=days + 1)
    while d <= end:
        m = d.strftime("%Y%m")
        if m not in vistos:
            vistos.append(m)
        d += timedelta(days=1)
    return vistos


def build_tide_curve(spot: dict, start: date, days: int, offline: bool) -> tuple[TideCurve | None, str | None]:
    estacion = ((spot.get("marea") or {}).get("estacion_ihm")) or {}
    sid = estacion.get("id")
    if sid is None:
        return None, "spot sin estación de marea asignada"
    if offline:
        return None, "modo offline"

    extremos = []
    for mes in months_needed(start, days):
        payload = sources.fetch_tide_month(int(sid), mes, cache_dir=CACHE)
        extremos.extend(parse_ihm_month(payload))
    if not extremos:
        return None, "el IHM no devolvió extremos de marea"
    return TideCurve(extremos), None


def spot_calibration(spot: dict) -> dict:
    """Qué le falta a este spot para dar su máximo."""
    faltan = []
    if is_pending(((spot.get("marea") or {}).get("ventana") or {}).get("tipo")):
        faltan.append("ventana de marea")
    if is_pending((spot.get("mar") or {}).get("ola_max_m")):
        faltan.append("límite de ola")
    if is_pending(spot.get("nivel_recomendado")):
        faltan.append("nivel recomendado")
    log = spot.get("logistica") or {}
    if is_pending(log.get("aparcamiento")) or is_pending(log.get("acceso_al_agua")):
        faltan.append("acceso y aparcamiento")
    dirs = (spot.get("viento") or {}).get("direcciones") or {}
    if dirs.get("origen") == "geometria":
        faltan.append("direcciones de viento (deducidas del mapa, sin calibrar)")
    return {"completo": not faltan, "faltan": faltan}


def build_spot(spot: dict, defaults: dict, alas_cfg: dict, rider_kg: float,
               offline: bool) -> dict:
    cfg = deep_merge(defaults, spot)
    lat = spot["coordenadas"]["lat"]
    lon = spot["coordenadas"]["lon"]

    forecast = sources.fetch_forecast(lat, lon, DIAS, cache_dir=CACHE)
    marine = None
    marine_error = None
    try:
        marine = sources.fetch_marine(lat, lon, DIAS, cache_dir=CACHE)
    except sources.FetchError as exc:
        marine_error = str(exc)

    horas_txt = forecast["hourly"]["time"]
    velocidad = forecast["hourly"]["wind_speed_10m"]
    racha = forecast["hourly"]["wind_gusts_10m"]
    direccion = forecast["hourly"]["wind_direction_10m"]

    olas_por_hora: dict[str, float | None] = {}
    if marine:
        for t, w in zip(marine["hourly"]["time"], marine["hourly"]["wave_height"]):
            olas_por_hora[t] = w

    inicio = datetime.strptime(horas_txt[0], "%Y-%m-%dT%H:%M").date()
    curva, tide_error = build_tide_curve(spot, inicio, DIAS, offline)

    por_dia: dict[date, list] = {}
    for i, t in enumerate(horas_txt):
        if velocidad[i] is None or direccion[i] is None:
            continue
        hora = datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=TZ)
        ev = assess_hour(
            hora,
            speed_kn=float(velocidad[i]),
            gust_kn=float(racha[i] if racha[i] is not None else velocidad[i]),
            direction_deg=float(direccion[i]),
            wave_m=olas_por_hora.get(t),
            curve=curva,
            spot_cfg=cfg,
            alas_cfg=alas_cfg,
            rider_kg=rider_kg,
        )
        por_dia.setdefault(hora.date(), []).append(ev)

    dias = []
    for indice, fecha in enumerate(sorted(por_dia)[:DIAS]):
        v = summarise_day(fecha, indice, por_dia[fecha], cfg)
        dias.append({
            "fecha": v.fecha.isoformat(),
            "indice": v.indice,
            "estado": v.estado,
            "titular": v.titular,
            "franja": v.franja,
            "ala": v.ala,
            "viento_franja": (
                [round(v.viento_franja[0], 1), round(v.viento_franja[1], 1)]
                if v.viento_franja else None
            ),
            "fiabilidad": v.fiabilidad,
            "viento": v.viento_resumen,
            "marea": v.marea_resumen,
            "detalle": v.detalle,
            "sin_calibrar": v.sin_calibrar,
            "horas": v.horas,
        })

    return {
        "id": spot["id"],
        "nombre": spot["nombre"],
        "zona": spot.get("zona"),
        "orden": spot.get("orden", 999),
        "coordenadas": {"lat": lat, "lon": lon},
        "estacion_marea": ((spot.get("marea") or {}).get("estacion_ihm") or {}).get("nombre"),
        "calibracion": spot_calibration(spot),
        "seguridad": [
            {"aviso": " ".join(str(a.get("aviso")).split()),
             "severidad": a.get("severidad", "media")}
            for a in (spot.get("seguridad") or [])
            if a.get("aviso") and not is_pending(a.get("aviso"))
        ],
        "logistica": {
            k: (None if is_pending(v) else v)
            for k, v in (spot.get("logistica") or {}).items()
            if k in ("aparcamiento", "acceso_al_agua")
        },
        "nivel_recomendado": None if is_pending(spot.get("nivel_recomendado")) else spot.get("nivel_recomendado"),
        "incidencias": [x for x in (tide_error, marine_error) if x],
        "dias": dias,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--peso", type=float, default=PESO_POR_DEFECTO,
                   help="peso del rider en kg para el JSON base")
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--offline", action="store_true",
                   help="no consultar el IHM (para pruebas)")
    p.add_argument("--solo", type=str, default=None, help="id de un único spot")
    args = p.parse_args()

    spots_cfg, alas_cfg = load_configs()
    defaults = spots_cfg.get("defaults") or {}

    spots = spots_cfg["spots"]
    if args.solo:
        spots = [s for s in spots if s["id"] == args.solo]
        if not spots:
            print(f"No existe el spot {args.solo!r}", file=sys.stderr)
            return 2

    # Datos ya publicados, si los hay: sirven de red para los spots que fallen.
    previo = {}
    previo_generado = None
    if args.salida.exists():
        try:
            anterior = json.loads(args.salida.read_text(encoding="utf-8"))
            previo = {s["id"]: s for s in anterior.get("spots", [])}
            previo_generado = anterior.get("generado_texto")
        except (json.JSONDecodeError, KeyError):
            pass

    resultados, fallos = [], []
    for spot in spots:
        try:
            resultados.append(
                build_spot(spot, defaults, alas_cfg, args.peso, args.offline)
            )
            print(f"  ok  {spot['id']}")
        except Exception as exc:  # noqa: BLE001
            fallos.append({"spot": spot["id"], "error": str(exc)})
            print(f"  FALLO {spot['id']}: {exc}", file=sys.stderr)
            # Antes que borrar el spot del sitio, conservamos lo último válido
            # marcándolo como obsoleto. La interfaz lo dirá; nunca se hace
            # pasar un dato viejo por fresco.
            if spot["id"] in previo:
                viejo = dict(previo[spot["id"]])
                viejo["obsoleto"] = True
                viejo["obsoleto_desde"] = previo_generado
                viejo["incidencias"] = (viejo.get("incidencias") or []) + [
                    ("No se han podido actualizar los datos de este spot; "
                    f"se muestran los de la última actualización correcta ({previo_generado}).")
                ]
                resultados.append(viejo)
                print(f"        -> se conservan los datos previos de {spot['id']}")

    if not resultados:
        print("Ningún spot se pudo construir. No se escribe nada: "
              "el sitio conserva los últimos datos válidos.", file=sys.stderr)
        return 1

    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    salida = {
        "version": 1,
        "generado": ahora.isoformat(timespec="seconds"),
        "generado_texto": ahora.strftime("%d/%m/%Y %H:%M"),
        "dias_prevision": DIAS,
        "peso_base_kg": args.peso,
        "alas": alas_cfg,
        "fuentes": [
            {"nombre": "Open-Meteo (viento)", "url": "https://open-meteo.com/",
             "licencia": "CC-BY 4.0, uso no comercial"},
            {"nombre": "Open-Meteo Marine (oleaje)", "url": "https://open-meteo.com/",
             "licencia": "CC-BY 4.0, uso no comercial"},
            {"nombre": "Instituto Hidrográfico de la Marina (mareas)",
             "url": "https://ideihm.covam.es/",
             "licencia": "Reutilización con licencia para uso no comercial (RD 1495/2011)"},
        ],
        "fallos": fallos,
        "spots": sorted(resultados, key=lambda s: s["orden"]),
    }

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Escrito {args.salida} · {len(resultados)} spots · {len(fallos)} fallos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
