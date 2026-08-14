import json

import pytest
from lib.tides import TideCurve, parse_ihm_month

from tests.conftest import madrid

# Respuesta REAL de https://ideihm.covam.es/api-ihm/getmarea
# (request=gettide&format=json&id=39&date=20260814), verificada en sesión.
RESPUESTA_REAL_UN_DIA = json.loads("""
{"mareas": {"copyright":"© Instituto Hidrográfico de la Marina (2026)",
 "id":"39", "puerto": "Chipiona", "fecha": "2026-08-14", "ndatos": "4",
 "lat": "36.746667", "lon": "-6.428333",
 "datos": { "marea": [
   {"hora": "03:03", "altura": "3.441", "tipo": "pleamar"},
   {"hora": "08:52", "altura": "0.451", "tipo": "bajamar"},
   {"hora": "15:19", "altura": "3.745", "tipo": "pleamar"},
   {"hora": "21:25", "altura": "0.379", "tipo": "bajamar"}]}}}
""")


def test_parsea_la_respuesta_real_del_ihm():
    extremos = parse_ihm_month(RESPUESTA_REAL_UN_DIA)
    assert len(extremos) == 4
    assert extremos[0].kind == "pleamar"
    assert extremos[0].height_m == pytest.approx(3.441)
    assert extremos[0].when == madrid(2026, 8, 14, 3, 3)
    assert extremos[-1].height_m == pytest.approx(0.379)


def test_parsea_formato_mensual_con_fecha_en_cada_registro():
    payload = {"mareas": {"datos": {"marea": [
        {"fecha": "2026-08-01", "hora": "03:38", "altura": "3.160", "tipo": "pleamar"},
        {"fecha": "2026-08-01", "hora": "09:32", "altura": "0.771", "tipo": "bajamar"},
    ]}}}
    extremos = parse_ihm_month(payload)
    assert len(extremos) == 2
    assert extremos[1].when == madrid(2026, 8, 1, 9, 32)


def test_rechaza_tipos_de_marea_desconocidos():
    payload = {"mareas": {"fecha": "2026-08-01", "datos": {"marea": [
        {"hora": "03:38", "altura": "3.16", "tipo": "mediamar"},
    ]}}}
    with pytest.raises(ValueError):
        parse_ihm_month(payload)


def test_la_curva_es_exacta_en_los_extremos(curva_chipiona):
    assert curva_chipiona.height_at(madrid(2026, 8, 14, 3, 3)) == pytest.approx(3.441)
    assert curva_chipiona.height_at(madrid(2026, 8, 14, 8, 52)) == pytest.approx(0.451)
    assert curva_chipiona.height_at(madrid(2026, 8, 14, 15, 19)) == pytest.approx(3.745)


def test_a_media_marea_da_el_punto_medio(curva_chipiona):
    """Mitad de camino entre pleamar 03:03 y bajamar 08:52 -> ~05:57."""
    altura = curva_chipiona.height_at(madrid(2026, 8, 14, 5, 57))
    assert altura == pytest.approx((3.441 + 0.451) / 2, abs=0.02)


def test_la_curva_es_monotona_entre_extremos(curva_chipiona):
    alturas = [
        curva_chipiona.height_at(madrid(2026, 8, 14, 9 + i // 60, i % 60))
        for i in range(0, 360, 20)
    ]
    assert alturas == sorted(alturas), "de bajamar 08:52 a pleamar 15:19 debe subir"


def test_no_inventa_altura_fuera_del_rango_conocido(curva_chipiona):
    assert curva_chipiona.height_at(madrid(2026, 8, 14, 1, 0)) is None
    assert curva_chipiona.height_at(madrid(2026, 8, 14, 23, 0)) is None


def test_curva_vacia_no_revienta():
    curva = TideCurve([])
    assert curva.height_at(madrid(2026, 8, 14, 12)) is None
    assert curva.covers(madrid(2026, 8, 14, 12)) is False


def test_desfase_horario_configurable():
    extremos = parse_ihm_month(RESPUESTA_REAL_UN_DIA, offset_minutes=-60)
    assert extremos[0].when == madrid(2026, 8, 14, 2, 3)
