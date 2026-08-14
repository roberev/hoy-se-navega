"""Marea: extremos oficiales del IHM -> curva horaria.

La API del Instituto Hidrográfico de la Marina devuelve SÓLO los extremos
(pleamares y bajamares) de cada día, no una serie horaria. Para saber la
altura a una hora concreta hay que interpolar entre extremos consecutivos.

MÉTODO: interpolación semi-cosenoidal (el equivalente continuo de la
"regla de los doceavos" que se usa en náutica):

    h(t) = (H1+H2)/2 + (H1-H2)/2 * cos( pi * (t-t1)/(t2-t1) )

Es exacta en los extremos y aproxima bien una marea semidiurna como la
gaditana. NO es una predicción armónica completa: el error típico en el
tramo central es de pocos centímetros, suficiente para decidir si se
navega, insuficiente para navegación náutica.

DATUM: las alturas del IHM van referidas al cero del puerto (aprox. la
bajamar máxima viva equinoccial), no al nivel medio del mar. Es el mismo
cero que usan las tablas de marea en papel, que es lo que quiere el rider.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


@dataclass(frozen=True)
class TideExtreme:
    when: datetime          # aware, Europe/Madrid
    height_m: float
    kind: str               # "pleamar" | "bajamar"


class TideCurve:
    """Curva de marea interpolada a partir de extremos ordenados."""

    def __init__(self, extremes: list[TideExtreme]):
        self.extremes = sorted(extremes, key=lambda e: e.when)
        self._times = [e.when for e in self.extremes]

    def __len__(self) -> int:
        return len(self.extremes)

    def covers(self, when: datetime) -> bool:
        if len(self.extremes) < 2:
            return False
        return self._times[0] <= when <= self._times[-1]

    def height_at(self, when: datetime) -> float | None:
        """Altura interpolada en metros sobre el cero del puerto.

        Devuelve None si `when` cae fuera del rango cubierto por los
        extremos conocidos: preferimos no dar dato a dar un dato inventado.
        """
        if not self.covers(when):
            return None

        idx = bisect_left(self._times, when)
        if self._times[idx] == when:
            return self.extremes[idx].height_m

        a = self.extremes[idx - 1]
        b = self.extremes[idx]

        span = (b.when - a.when).total_seconds()
        if span <= 0:
            return a.height_m

        frac = (when - a.when).total_seconds() / span
        mid = (a.height_m + b.height_m) / 2.0
        amp = (a.height_m - b.height_m) / 2.0
        return mid + amp * math.cos(math.pi * frac)

    def next_extreme_after(self, when: datetime, kind: str | None = None) -> TideExtreme | None:
        for e in self.extremes:
            if e.when > when and (kind is None or e.kind == kind):
                return e
        return None

    def nearest_extreme(self, when: datetime, kind: str) -> TideExtreme | None:
        candidates = [e for e in self.extremes if e.kind == kind]
        if not candidates:
            return None
        return min(candidates, key=lambda e: abs((e.when - when).total_seconds()))

    def range_on(self, day: date) -> tuple[float, float] | None:
        """(mínimo, máximo) de los extremos de ese día. Útil para contexto."""
        vals = [e.height_m for e in self.extremes if e.when.date() == day]
        if not vals:
            return None
        return (min(vals), max(vals))


def parse_ihm_month(payload: dict, tz: ZoneInfo = TZ, offset_minutes: int = 0) -> list[TideExtreme]:
    """Parsea la respuesta JSON de ideihm.covam.es (request=gettide).

    Acepta tanto la forma de un día (`fecha` en la cabecera, sin `fecha` en
    cada registro) como la forma mensual (`fecha` dentro de cada registro).

    `offset_minutes` permite corregir un desfase horario sistemático sin
    tocar el código, si se comprobara que la API no publica en hora local.
    """
    mareas = payload.get("mareas")
    if not mareas:
        raise ValueError("Respuesta IHM sin clave 'mareas'")

    datos = mareas.get("datos") or {}
    registros = datos.get("marea") or []
    if isinstance(registros, dict):
        registros = [registros]

    fecha_cabecera = mareas.get("fecha")
    out: list[TideExtreme] = []

    for r in registros:
        fecha_txt = r.get("fecha") or fecha_cabecera
        if not fecha_txt:
            raise ValueError("Registro de marea sin fecha ni fecha de cabecera")

        hora_txt = r["hora"]
        # Formatos observados: "03:03" y, por prudencia, "03:03:00"
        partes = [int(p) for p in hora_txt.split(":")]
        hh, mm = partes[0], partes[1]

        d = datetime.strptime(fecha_txt, "%Y-%m-%d").date()
        when = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        if offset_minutes:
            when = when + timedelta(minutes=offset_minutes)

        kind = (r.get("tipo") or "").strip().lower()
        if kind not in ("pleamar", "bajamar"):
            raise ValueError(f"Tipo de marea inesperado: {r.get('tipo')!r}")

        out.append(TideExtreme(when=when, height_m=float(r["altura"]), kind=kind))

    return out
