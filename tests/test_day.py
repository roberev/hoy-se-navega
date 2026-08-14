"""Tests de la agregación diaria: franja, veredicto del día y explicación."""

import copy
from datetime import date

from lib.day import summarise_day
from lib.verdict import JUSTO, NO, SI, assess_hour

from tests.conftest import madrid


def _dia(spot, alas_cfg, curva, perfil):
    """perfil: dict hora -> (viento, racha, direccion, ola)"""
    horas = []
    for h in sorted(perfil):
        v, g, d, w = perfil[h]
        horas.append(assess_hour(madrid(2026, 8, 14, h), speed_kn=v, gust_kn=g,
                                 direction_deg=d, wave_m=w, curve=curva,
                                 spot_cfg=spot, alas_cfg=alas_cfg, rider_kg=75))
    return summarise_day(date(2026, 8, 14), 0, horas, spot)


def test_detecta_la_franja_navegable(spot_base, alas_cfg, curva_chipiona):
    # Marea sube desde 08:52; a partir de ~12h supera 1.8 m.
    perfil = {h: (20, 24, 240, 0.5) for h in range(8, 21)}
    v = _dia(spot_base, alas_cfg, curva_chipiona, perfil)
    assert v.estado == SI
    assert v.franja is not None
    inicio, fin = v.franja.split("–")
    assert inicio >= "11:00" and fin <= "19:00"


def test_dia_sin_viento_es_no_y_lo_dice(spot_base, alas_cfg, curva_chipiona):
    perfil = {h: (6, 8, 240, 0.4) for h in range(8, 21)}
    v = _dia(spot_base, alas_cfg, curva_chipiona, perfil)
    assert v.estado == NO
    assert v.franja is None
    assert v.titular.startswith("No:")
    assert "viento flojo" in v.titular


def test_cuando_la_marea_es_lo_unico_que_falla_el_texto_lo_seniala(
        spot_base, alas_cfg, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "altura_minima", "altura_min_m": 3.9}
    perfil = {h: (20, 24, 240, 0.4) for h in range(8, 21)}
    v = _dia(spot, alas_cfg, curva_chipiona, perfil)
    assert v.estado == NO
    assert "marea" in v.titular.lower()
    assert any("viento sí acompaña" in d for d in v.detalle)


def test_el_titular_de_un_no_nunca_es_solo_no(spot_base, alas_cfg, curva_chipiona):
    escenarios = [
        {h: (6, 8, 240, 0.4) for h in range(8, 21)},
        {h: (45, 50, 240, 0.4) for h in range(8, 21)},
        {h: (20, 24, 90, 0.4) for h in range(8, 21)},
        {h: (20, 24, 240, 3.0) for h in range(8, 21)},
    ]
    for perfil in escenarios:
        v = _dia(spot_base, alas_cfg, curva_chipiona, perfil)
        assert v.estado == NO
        assert len(v.titular) > len("No: ")


def test_la_fiabilidad_baja_con_el_horizonte(spot_base, alas_cfg, curva_chipiona):
    horas = [assess_hour(madrid(2026, 8, 14, h), speed_kn=20, gust_kn=24,
                         direction_deg=240, wave_m=0.5, curve=curva_chipiona,
                         spot_cfg=spot_base, alas_cfg=alas_cfg, rider_kg=75)
             for h in range(8, 21)]
    assert summarise_day(date(2026, 8, 14), 0, horas, spot_base).fiabilidad == "alta"
    assert summarise_day(date(2026, 8, 14), 2, horas, spot_base).fiabilidad == "media"
    assert summarise_day(date(2026, 8, 14), 4, horas, spot_base).fiabilidad == "baja"


def test_prefiere_la_franja_de_mejor_calidad_no_la_mas_larga(
        spot_base, alas_cfg, curva_chipiona):
    """6 horas de 'justo' por la mañana y 3 de 'sí' por la tarde -> el día es Sí."""
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "siempre"}
    perfil = {h: (13, 15, 240, 0.4) for h in range(8, 14)}       # justo
    perfil.update({h: (20, 23, 240, 0.4) for h in range(15, 18)})  # sí
    perfil[14] = (5, 6, 240, 0.4)                                 # corte
    v = _dia(spot, alas_cfg, curva_chipiona, perfil)
    assert v.estado == SI
    assert v.franja == "15:00–17:00"


def test_devuelve_viento_de_la_franja_para_recalcular_ala_en_el_navegador(
        spot_base, alas_cfg, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "siempre"}
    perfil = {15: (18, 21, 240, 0.4), 16: (24, 28, 240, 0.4)}
    v = _dia(spot, alas_cfg, curva_chipiona, perfil)
    assert v.viento_franja == (18.0, 24.0)


def test_la_serie_horaria_completa_va_en_el_json(spot_base, alas_cfg, curva_chipiona):
    perfil = {h: (20, 24, 240, 0.5) for h in range(24)}
    v = _dia(spot_base, alas_cfg, curva_chipiona, perfil)
    assert len(v.horas) == 24
    assert all("motivos" in h and h["motivos"] for h in v.horas)


def test_un_spot_sin_calibrar_no_llega_a_si_pero_conserva_la_franja(
        spot_base, alas_cfg, curva_chipiona):
    """La falta de dato local pone techo al veredicto, pero NO debe ensanchar
    la franja hasta hacerla inútil."""
    import copy

    from lib.verdict import PENDIENTE

    calibrado = copy.deepcopy(spot_base)
    calibrado["marea"]["ventana"] = {"tipo": "siempre"}
    sin_calibrar = copy.deepcopy(calibrado)
    sin_calibrar["marea"]["ventana"] = {"tipo": PENDIENTE}

    perfil = {h: (6, 8, 240, 0.4) for h in range(8, 13)}
    perfil.update({h: (20, 23, 240, 0.4) for h in range(13, 18)})
    perfil.update({h: (6, 8, 240, 0.4) for h in range(18, 22)})

    a = _dia(calibrado, alas_cfg, curva_chipiona, perfil)
    b = _dia(sin_calibrar, alas_cfg, curva_chipiona, perfil)

    assert a.estado == SI and b.estado == JUSTO
    assert a.franja == b.franja == "13:00–17:00"
    assert b.sin_calibrar
    # el porqué físico manda en el titular; el "sin calibrar" es del spot,
    # no del día, y la interfaz lo muestra una sola vez
    assert "nudos" in b.titular
    assert "calibrar" not in b.titular
    assert any("calibrar" in d for d in b.detalle)
