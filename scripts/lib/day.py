"""Agregación de horas a día: veredicto, franja navegable y el porqué."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .verdict import _ORDER, JUSTO, NO, SI, HourAssessment, cardinal

# Fiabilidad por horizonte de previsión. La previsión a 5 días no vale lo
# mismo que la de mañana y el producto tiene que decirlo.
FIABILIDAD = {0: "alta", 1: "alta", 2: "media", 3: "media", 4: "baja", 5: "baja"}


@dataclass
class DayVerdict:
    fecha: date
    indice: int                 # 0 = hoy
    estado: str
    titular: str                # el porqué, en una línea
    franja: str | None          # "11:00–15:00"
    ala: str | None
    fiabilidad: str
    viento_resumen: str | None
    marea_resumen: str | None
    detalle: list[str]          # motivos secundarios
    horas: list[dict]           # serie horaria, para el detalle desplegable
    # Viento mínimo y máximo dentro de la franja navegable. El navegador los
    # usa para recalcular el ala con el peso del usuario sin volver a la red.
    viento_franja: tuple[float, float] | None = None
    # Condiciones que no se han podido juzgar por falta de dato local.
    # Mientras haya alguna, el día no puede llegar a "Sí".
    sin_calibrar: list[str] = field(default_factory=list)


def summarise_day(fecha: date, indice: int, horas: list[HourAssessment],
                  spot: dict) -> DayVerdict:
    fiabilidad = FIABILIDAD.get(indice, "baja")
    luz = [h for h in horas if _hora_util(h, spot)]
    if not luz:
        luz = horas

    sin_calibrar = _sin_calibrar(luz)

    runs = _contiguous_runs(luz)
    mejor = _best_run(runs)

    if mejor is None:
        estado = NO
        titular, detalle = _explain_no(luz)
        return DayVerdict(fecha, indice, estado, titular, None, None, fiabilidad,
                          _wind_summary(luz), _tide_summary(luz), detalle,
                          [_hour_dict(h) for h in horas], None, sin_calibrar)

    fisico = max((h.estado for h in mejor), key=lambda e: _ORDER[e])
    nucleo = _longest_at_level(mejor, fisico)
    franja = f"{nucleo[0].hora:%H:%M}–{nucleo[-1].hora:%H:%M}"
    ala = _wing_range(nucleo)
    titular, detalle = _explain_yes(nucleo, luz, fisico)

    # Techo por falta de conocimiento local: no afirmamos lo que no sabemos.
    estado = fisico
    if sin_calibrar and estado == SI:
        estado = JUSTO
        # El titular se queda con el porqué físico. El "sin calibrar" es una
        # propiedad del spot, no del día: la interfaz lo muestra una sola vez.
        cuerpo = titular.split(":", 1)[1].strip() if ":" in titular else titular
        titular = f"Justo: {cuerpo}"
        detalle.append(f"Para poder decir «Sí» falta calibrar {_lista(sin_calibrar)}.")
    elif sin_calibrar:
        detalle.append(f"Además, falta calibrar {_lista(sin_calibrar)}.")

    viento_franja = (
        min(h.viento_nudos for h in nucleo),
        max(h.viento_nudos for h in nucleo),
    ) if nucleo else None

    return DayVerdict(fecha, indice, estado, titular, franja, ala, fiabilidad,
                      _wind_summary(nucleo), _tide_summary(luz), detalle,
                      [_hour_dict(h) for h in horas], viento_franja,
                      sin_calibrar)


# ---------------------------------------------------------------------------

ETIQUETA_CALIBRACION = {
    "marea": "la ventana de marea",
    "mar": "el límite de ola",
    "viento": "las direcciones de viento",
}


def _sin_calibrar(horas: list[HourAssessment]) -> list[str]:
    """Etiquetas legibles de lo que no se ha podido juzgar, sin repetir."""
    claves: list[str] = []
    for h in horas:
        for c in h.sin_confianza:
            if c.clave not in claves:
                claves.append(c.clave)
    return [ETIQUETA_CALIBRACION.get(k, k) for k in claves]


def _lista(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


def _hora_util(h: HourAssessment, spot: dict) -> bool:
    desde = int((spot.get("horario") or {}).get("desde", 8))
    hasta = int((spot.get("horario") or {}).get("hasta", 21))
    return desde <= h.hora.hour <= hasta


def _contiguous_runs(horas: list[HourAssessment]) -> list[list[HourAssessment]]:
    runs, actual = [], []
    for h in horas:
        if h.estado == NO:
            if actual:
                runs.append(actual)
                actual = []
        else:
            actual.append(h)
    if actual:
        runs.append(actual)
    return runs


def _best_run(runs):
    if not runs:
        return None
    return max(runs, key=lambda r: (max(_ORDER[h.estado] for h in r), len(r)))


def _longest_at_level(run: list[HourAssessment], nivel: str) -> list[HourAssessment]:
    mejor, actual = [], []
    for h in run:
        if h.estado == nivel:
            actual.append(h)
            if len(actual) > len(mejor):
                mejor = list(actual)
        else:
            actual = []
    return mejor or run


def _wing_range(horas: list[HourAssessment]) -> str | None:
    valores = [h.ala for h in horas if h.ala and h.ala.navegable and h.ala.ala_min]
    if not valores:
        return None
    lo = min(v.ala_min for v in valores)
    hi = max(v.ala_max for v in valores)
    if abs(hi - lo) < 1e-9:
        return f"{lo:.1f} m"
    return f"{lo:.1f}–{hi:.1f} m"


def _wind_summary(horas: list[HourAssessment]) -> str | None:
    if not horas:
        return None
    lo = min(h.viento_nudos for h in horas)
    hi = max(h.viento_nudos for h in horas)
    medio = sum(h.direccion_grados for h in horas) / len(horas)
    rango = f"{lo:.0f}" if round(lo) == round(hi) else f"{lo:.0f}–{hi:.0f}"
    return f"{rango} nudos del {cardinal(medio)}"


def _tide_summary(horas: list[HourAssessment]) -> str | None:
    alturas = [(h.hora, h.marea_m) for h in horas if h.marea_m is not None]
    if not alturas:
        return None
    hora_max, alto = max(alturas, key=lambda x: x[1])
    hora_min, bajo = min(alturas, key=lambda x: x[1])
    return (f"pleamar ~{alto:.1f} m a las {hora_max:%H:%M} · "
            f"bajamar ~{bajo:.1f} m a las {hora_min:%H:%M}")


def _explain_yes(nucleo: list[HourAssessment], todas: list[HourAssessment],
                 estado: str) -> tuple[str, list[str]]:
    viento = _wind_summary(nucleo) or ""
    if estado == SI:
        titular = f"Sí: {viento}"
    else:
        limitante = _dominant_reason(nucleo, JUSTO)
        titular = f"Justo: {limitante}" if limitante else f"Justo: {viento}"

    detalle = []
    for clave in ("viento", "marea", "mar"):
        razon = _dominant_reason_for(nucleo, clave, solo_con_confianza=True)
        if razon:
            detalle.append(razon)

    fuera = [h for h in todas if h.estado == NO]
    if fuera:
        razon = _dominant_reason(fuera, NO)
        if razon:
            detalle.append(f"Fuera de esa franja: {razon}")
    return titular, detalle


def _explain_no(horas: list[HourAssessment]) -> tuple[str, list[str]]:
    if not horas:
        return "No: sin datos suficientes", []

    bloqueos = [c for h in horas for c in h.checks if c.estado == NO]
    if not bloqueos:
        return "No: sin datos suficientes", []

    conteo: dict[str, int] = {}
    for c in bloqueos:
        conteo[c.clave] = conteo.get(c.clave, 0) + 1
    clave_principal = max(conteo, key=conteo.get)

    razon = _dominant_reason_for(horas, clave_principal, estado=NO)
    titular = f"No: {razon}" if razon else "No"

    # ¿Habría servido algo si no fuera por ese bloqueo?
    detalle = []
    salvables = [h for h in horas
                 if all(c.estado != NO for c in h.checks if c.clave != clave_principal)]
    if salvables and clave_principal != "viento":
        v = _wind_summary(salvables)
        if v:
            detalle.append(f"El viento sí acompaña ({v}), lo que falla es la {clave_principal}.")

    otras = [k for k in conteo if k != clave_principal]
    for k in otras:
        r = _dominant_reason_for(horas, k, estado=NO)
        if r:
            detalle.append(f"También: {r}.")
    return titular, detalle


def _dominant_reason(horas: list[HourAssessment], estado: str) -> str | None:
    razones: dict[str, int] = {}
    for h in horas:
        for c in h.checks:
            if c.estado == estado:
                razones[c.razon] = razones.get(c.razon, 0) + 1
    if not razones:
        return None
    return max(razones, key=razones.get)


def _dominant_reason_for(horas: list[HourAssessment], clave: str,
                         estado: str | None = None,
                         solo_con_confianza: bool = False) -> str | None:
    razones: dict[str, int] = {}
    for h in horas:
        for c in h.checks:
            if c.clave != clave:
                continue
            if solo_con_confianza and not c.confianza:
                continue
            if estado is not None and c.estado != estado:
                continue
            if estado is None and c.estado == SI:
                continue
            razones[c.razon] = razones.get(c.razon, 0) + 1
    if not razones:
        return None
    return max(razones, key=razones.get)


def _hour_dict(h: HourAssessment) -> dict:
    return {
        "hora": h.hora.strftime("%H:%M"),
        "estado": h.estado,
        "viento": round(h.viento_nudos, 1),
        "racha": round(h.racha_nudos, 1),
        "direccion": round(h.direccion_grados),
        "rumbo": cardinal(h.direccion_grados),
        "ola": None if h.ola_m is None else round(h.ola_m, 2),
        "marea": None if h.marea_m is None else round(h.marea_m, 2),
        "ala": h.ala.texto() if h.ala else None,
        "motivos": [
            {"clave": c.clave, "estado": c.estado, "razon": c.razon}
            for c in h.checks
        ],
    }
