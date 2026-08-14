"""Motor de veredicto.

Tres condiciones —viento, marea y mar— evaluadas por separado. El veredicto
de una hora es SIEMPRE el más restrictivo de los tres, y arrastra consigo el
motivo. Un "No" sin porqué no vale.

Estados: "si" > "justo" > "no".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .tides import TideCurve
from .wings import WingRecommendation, recommend_wing

SI, JUSTO, NO = "si", "justo", "no"
_ORDER = {NO: 0, JUSTO: 1, SI: 2}

PENDIENTE = "PENDIENTE_ROBE"

RUMBOS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


def cardinal(degrees: float) -> str:
    return RUMBOS[int((degrees % 360) / 22.5 + 0.5) % 16]


def worst(*estados: str) -> str:
    return min(estados, key=lambda e: _ORDER[e])


def is_pending(value) -> bool:
    return isinstance(value, str) and value.strip() == PENDIENTE


def in_range(degrees: float, rango) -> bool:
    """¿Está `degrees` dentro de [a, b]? Soporta rangos que cruzan el norte."""
    a, b = float(rango[0]) % 360, float(rango[1]) % 360
    d = float(degrees) % 360
    if a <= b:
        return a <= d <= b
    return d >= a or d <= b


def in_any_range(degrees: float, rangos) -> bool:
    return any(in_range(degrees, r) for r in (rangos or []))


@dataclass(frozen=True)
class Check:
    clave: str          # "viento" | "marea" | "mar"
    estado: str
    razon: str          # frase corta, en lenguaje de rider
    # False cuando el dato local que hace falta para juzgar esta condición
    # todavía no existe. Un check sin confianza NO estrecha la franja
    # navegable (sería ruido uniforme), pero SÍ impide que el día llegue a
    # "Sí": no afirmamos lo que no sabemos.
    confianza: bool = True


@dataclass
class HourAssessment:
    hora: datetime
    estado: str
    checks: list[Check]
    viento_nudos: float
    racha_nudos: float
    direccion_grados: float
    ola_m: float | None
    marea_m: float | None
    ala: WingRecommendation | None = None

    @property
    def limitantes(self) -> list[Check]:
        return [c for c in self.checks if c.estado == self.estado]

    @property
    def sin_confianza(self) -> list[Check]:
        return [c for c in self.checks if not c.confianza]


# ---------------------------------------------------------------------------
# Condición 1: viento
# ---------------------------------------------------------------------------

def evaluate_wind(speed_kn: float, gust_kn: float, direction_deg: float,
                  cfg: dict) -> Check:
    v = cfg["viento"]
    rumbo = cardinal(direction_deg)

    if speed_kn < float(v["minimo_nudos"]):
        return Check("viento", NO,
                     f"viento flojo, {speed_kn:.0f} nudos")
    if speed_kn > float(v["maximo_nudos"]):
        return Check("viento", NO,
                     f"demasiado viento, {speed_kn:.0f} nudos del {rumbo}")

    dirs = v.get("direcciones") or {}
    estado_dir, razon_dir = SI, None

    if in_any_range(direction_deg, dirs.get("malas")):
        motivo = _direction_note(cfg, direction_deg)
        return Check("viento", NO,
                     f"viento del {rumbo}" + (f", {motivo}" if motivo else ", dirección mala en este spot"))

    if in_any_range(direction_deg, dirs.get("regulares")):
        estado_dir = JUSTO
        razon_dir = f"viento del {rumbo}, dirección regular aquí"
    elif not in_any_range(direction_deg, dirs.get("buenas")):
        # No clasificada: no la damos por buena.
        estado_dir = JUSTO
        razon_dir = f"viento del {rumbo}, dirección sin clasificar en este spot"

    estado_fuerza, razon_fuerza = SI, None
    if speed_kn < float(v["justo_bajo_nudos"]):
        estado_fuerza = JUSTO
        razon_fuerza = f"justo de viento, {speed_kn:.0f} nudos"
    elif speed_kn > float(v["justo_alto_nudos"]):
        estado_fuerza = JUSTO
        razon_fuerza = f"viento fuerte, {speed_kn:.0f} nudos"

    estado_racha, razon_racha = SI, None
    if speed_kn > 0:
        ratio = gust_kn / speed_kn
        if ratio >= float(v["racha_ratio_malo"]):
            estado_racha = NO
            razon_racha = f"muy racheado ({speed_kn:.0f} nudos con rachas de {gust_kn:.0f})"
        elif ratio >= float(v["racha_ratio_justo"]):
            estado_racha = JUSTO
            razon_racha = f"racheado ({speed_kn:.0f} con rachas de {gust_kn:.0f})"

    estado = worst(estado_dir, estado_fuerza, estado_racha)
    if estado == SI:
        return Check("viento", SI, f"{speed_kn:.0f} nudos del {rumbo}")

    for est, raz in ((estado_racha, razon_racha), (estado_dir, razon_dir),
                     (estado_fuerza, razon_fuerza)):
        if est == estado and raz:
            return Check("viento", estado, raz)
    return Check("viento", estado, f"{speed_kn:.0f} nudos del {rumbo}")


def _direction_note(cfg: dict, direction_deg: float) -> str | None:
    for nota in cfg["viento"].get("malas_notas") or []:
        if in_range(direction_deg, nota["rango"]):
            texto = (nota.get("motivo") or "").strip()
            texto = " ".join(texto.split())
            return texto[0].lower() + texto[1:] if texto else None
    return None


# ---------------------------------------------------------------------------
# Condición 2: marea
# ---------------------------------------------------------------------------

def evaluate_tide(when: datetime, curve: TideCurve | None, cfg: dict) -> Check:
    ventana = (cfg.get("marea") or {}).get("ventana") or {}
    tipo = ventana.get("tipo")

    if is_pending(tipo) or tipo is None:
        return Check("marea", SI,
                     "ventana de marea sin calibrar en este spot",
                     confianza=False)

    if tipo == "siempre":
        return Check("marea", SI, "la marea no limita aquí")

    if curve is None or not curve.covers(when):
        return Check("marea", SI, "sin datos de marea para esa hora",
                     confianza=False)

    altura = curve.height_at(when)
    if altura is None:
        return Check("marea", SI, "sin datos de marea para esa hora",
                     confianza=False)

    if tipo == "altura_minima":
        minimo = float(ventana["altura_min_m"])
        maximo = ventana.get("altura_max_m")
        if altura < minimo:
            return Check("marea", NO,
                         f"marea baja, {altura:.1f} m (hacen falta {minimo:.1f})")
        if maximo is not None and altura > float(maximo):
            return Check("marea", NO,
                         f"demasiada agua, {altura:.1f} m (máximo {float(maximo):.1f})")
        margen = float(ventana.get("margen_justo_m", 0.3))
        if altura < minimo + margen:
            return Check("marea", JUSTO, f"marea justa, {altura:.1f} m")
        return Check("marea", SI, f"marea {altura:.1f} m")

    if tipo == "horas_alrededor":
        referencia = ventana.get("referencia", "pleamar")
        antes = float(ventana["horas_antes"])
        despues = float(ventana["horas_despues"])
        ext = curve.nearest_extreme(when, referencia)
        if ext is None:
            return Check("marea", SI, "sin datos de marea para esa hora",
                         confianza=False)
        delta_h = (when - ext.when).total_seconds() / 3600.0
        if -antes <= delta_h <= despues:
            return Check("marea", SI,
                         f"dentro de la ventana de {referencia} ({ext.when:%H:%M})")
        return Check("marea", NO,
                     f"fuera de la ventana de {referencia}, que es a las {ext.when:%H:%M}")

    raise ValueError(f"Tipo de ventana de marea desconocido: {tipo!r}")


# ---------------------------------------------------------------------------
# Condición 3: mar
# ---------------------------------------------------------------------------

def evaluate_sea(wave_m: float | None, cfg: dict) -> Check:
    mar = cfg.get("mar") or {}
    umbral = mar.get("ola_max_m")

    if is_pending(umbral) or umbral is None:
        return Check("mar", SI, "límite de ola sin calibrar en este spot",
                     confianza=False)

    if wave_m is None:
        return Check("mar", SI, "sin datos de oleaje", confianza=False)

    umbral = float(umbral)
    justo = float(mar.get("ola_justo_m", umbral * 0.7))

    if wave_m > umbral:
        return Check("mar", NO, f"mar gruesa, {wave_m:.1f} m de ola")
    if wave_m > justo:
        return Check("mar", JUSTO, f"ola de {wave_m:.1f} m")
    return Check("mar", SI, f"ola de {wave_m:.1f} m")


# ---------------------------------------------------------------------------
# Combinación
# ---------------------------------------------------------------------------

def assess_hour(hora: datetime, *, speed_kn: float, gust_kn: float,
                direction_deg: float, wave_m: float | None,
                curve: TideCurve | None, spot_cfg: dict,
                alas_cfg: dict, rider_kg: float) -> HourAssessment:
    checks = [
        evaluate_wind(speed_kn, gust_kn, direction_deg, spot_cfg),
        evaluate_tide(hora, curve, spot_cfg),
        evaluate_sea(wave_m, spot_cfg),
    ]
    estado = worst(*(c.estado for c in checks))

    ala = recommend_wing(speed_kn, rider_kg, alas_cfg)
    altura = curve.height_at(hora) if curve is not None else None

    return HourAssessment(
        hora=hora,
        estado=estado,
        checks=checks,
        viento_nudos=speed_kn,
        racha_nudos=gust_kn,
        direccion_grados=direction_deg,
        ola_m=wave_m,
        marea_m=altura,
        # El ala se calcula siempre, también en horas descartadas: sirve para
        # que la franja del día pueda decir con qué ala se sale aunque el día
        # esté bloqueado por otra condición.
        ala=ala,
    )
