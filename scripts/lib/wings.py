"""Traducción viento x peso -> tamaño de ala.

Toda la tabla vive en config/alas.yaml. Aquí sólo está la mecánica de
buscar el tramo y aplicar el escalado por peso.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WingRecommendation:
    navegable: bool
    ala_min: float | None
    ala_max: float | None
    etiqueta: str

    def texto(self) -> str:
        if not self.navegable or self.ala_min is None:
            return self.etiqueta
        if self.ala_max is None or abs(self.ala_max - self.ala_min) < 1e-9:
            return f"{self.ala_min:.1f} m"
        return f"{self.ala_min:.1f}–{self.ala_max:.1f} m"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_half(value: float) -> float:
    """Redondea al medio metro más cercano: las alas se venden así."""
    return round(value * 2.0) / 2.0


def recommend_wing(wind_knots: float, rider_kg: float, config: dict) -> WingRecommendation:
    """Devuelve el ala recomendada para un viento medio y un peso de rider.

    El escalado por peso es lineal (`kg_por_paso` kg -> `metros_por_paso` m)
    y está declarado como suposición en config/alas.yaml.
    """
    tramo = _find_band(wind_knots, config["tramos"])

    if tramo is None:
        return WingRecommendation(False, None, None, "Fuera de tabla")

    if not tramo.get("navegable", True):
        return WingRecommendation(
            False, None, None, tramo.get("etiqueta", "No navegable")
        )

    escalado = config["escalado_peso"]
    peso_ref = float(config["peso_referencia_kg"])
    peso = _clamp(
        float(rider_kg), float(escalado["peso_min_kg"]), float(escalado["peso_max_kg"])
    )

    delta = ((peso - peso_ref) / float(escalado["kg_por_paso"])) * float(
        escalado["metros_por_paso"]
    )

    ala_min = _round_half(float(tramo["ala_min"]) + delta)
    ala_max = _round_half(float(tramo["ala_max"]) + delta)

    ala_min = _clamp(ala_min, float(escalado["ala_min_m"]), float(escalado["ala_max_m"]))
    ala_max = _clamp(ala_max, float(escalado["ala_min_m"]), float(escalado["ala_max_m"]))
    ala_max = max(ala_max, ala_min)

    return WingRecommendation(
        True, ala_min, ala_max, tramo.get("etiqueta", "")
    )


def _find_band(wind_knots: float, tramos: list[dict]) -> dict | None:
    for tramo in tramos:
        if float(tramo["desde"]) <= wind_knots < float(tramo["hasta"]):
            return tramo
    return None
