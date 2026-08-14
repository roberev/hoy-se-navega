import copy

import pytest
from lib.verdict import (
    JUSTO,
    NO,
    PENDIENTE,
    SI,
    assess_hour,
    cardinal,
    evaluate_sea,
    evaluate_tide,
    evaluate_wind,
    in_range,
    worst,
)

from tests.conftest import madrid

# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def test_worst_devuelve_el_mas_restrictivo():
    assert worst(SI, SI, SI) == SI
    assert worst(SI, JUSTO, SI) == JUSTO
    assert worst(SI, JUSTO, NO) == NO
    assert worst(NO, NO) == NO


def test_rangos_de_direccion_que_cruzan_el_norte():
    assert in_range(350, [330, 30]) is True
    assert in_range(10, [330, 30]) is True
    assert in_range(180, [330, 30]) is False
    assert in_range(200, [180, 300]) is True
    assert in_range(170, [180, 300]) is False


def test_rumbos_cardinales():
    assert cardinal(0) == "N"
    assert cardinal(90) == "E"
    assert cardinal(225) == "SO"
    assert cardinal(359) == "N"


# --------------------------------------------------------------------------
# Viento
# --------------------------------------------------------------------------

def test_viento_flojo_es_no_y_dice_cuanto(spot_base):
    c = evaluate_wind(9, 12, 240, spot_base)
    assert c.estado == NO
    assert "9 nudos" in c.razon


def test_viento_excesivo_es_no(spot_base):
    assert evaluate_wind(40, 45, 240, spot_base).estado == NO


def test_direccion_mala_es_no_y_explica_el_motivo_del_spot(spot_base):
    c = evaluate_wind(20, 24, 90, spot_base)
    assert c.estado == NO
    assert "offshore" in c.razon.lower()
    assert "E" in c.razon


def test_direccion_buena_y_viento_medio_es_si(spot_base):
    c = evaluate_wind(20, 24, 240, spot_base)
    assert c.estado == SI
    assert "20 nudos del OSO" in c.razon   # 240° es OSO, no SO


def test_direccion_regular_baja_a_justo(spot_base):
    c = evaluate_wind(20, 24, 165, spot_base)
    assert c.estado == JUSTO


def test_rachas_muy_desiguales_son_no(spot_base):
    c = evaluate_wind(20, 34, 240, spot_base)   # ratio 1.7
    assert c.estado == NO
    assert "racheado" in c.razon


def test_rachas_moderadamente_desiguales_son_justo(spot_base):
    c = evaluate_wind(20, 29, 240, spot_base)   # ratio 1.45
    assert c.estado == JUSTO


def test_viento_en_el_limite_inferior_es_justo(spot_base):
    assert evaluate_wind(13, 15, 240, spot_base).estado == JUSTO


def test_direccion_no_clasificada_no_se_da_por_buena(spot_base):
    spot = copy.deepcopy(spot_base)
    spot["viento"]["direcciones"] = {"buenas": [[200, 260]],
                                     "regulares": [], "malas": []}
    assert evaluate_wind(20, 24, 100, spot).estado == JUSTO


# --------------------------------------------------------------------------
# Marea
# --------------------------------------------------------------------------

def test_marea_por_debajo_del_minimo_es_no_y_da_las_cifras(spot_base, curva_chipiona):
    c = evaluate_tide(madrid(2026, 8, 14, 9, 0), curva_chipiona, spot_base)
    assert c.estado == NO
    assert "marea baja" in c.razon
    assert "1.8" in c.razon


def test_marea_alta_es_si(spot_base, curva_chipiona):
    c = evaluate_tide(madrid(2026, 8, 14, 15, 19), curva_chipiona, spot_base)
    assert c.estado == SI


def test_marea_justo_por_encima_del_minimo_es_justo(spot_base, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "altura_minima", "altura_min_m": 0.4,
                                "margen_justo_m": 0.3}
    c = evaluate_tide(madrid(2026, 8, 14, 8, 52), curva_chipiona, spot)
    assert c.estado == JUSTO


def test_ventana_pendiente_de_calibrar_no_estrecha_la_franja_pero_pierde_confianza(
        spot_base, curva_chipiona):
    """Una ventana sin calibrar no debe teñir todas las horas por igual: eso
    haría inútil la franja. Se marca sin confianza y el techo se aplica luego
    a nivel de día."""
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": PENDIENTE}
    c = evaluate_tide(madrid(2026, 8, 14, 15, 0), curva_chipiona, spot)
    assert c.estado == SI
    assert c.confianza is False
    assert "sin calibrar" in c.razon


def test_ventana_siempre_no_limita(spot_base, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "siempre"}
    assert evaluate_tide(madrid(2026, 8, 14, 9, 0), curva_chipiona, spot).estado == SI


def test_ventana_por_horas_alrededor_de_pleamar(spot_base, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "horas_alrededor", "referencia": "pleamar",
                                "horas_antes": 2, "horas_despues": 2}
    assert evaluate_tide(madrid(2026, 8, 14, 14, 0), curva_chipiona, spot).estado == SI
    fuera = evaluate_tide(madrid(2026, 8, 14, 11, 0), curva_chipiona, spot)
    assert fuera.estado == NO
    assert "15:19" in fuera.razon


def test_sin_curva_de_marea_no_afirma_nada(spot_base):
    c = evaluate_tide(madrid(2026, 8, 14, 12, 0), None, spot_base)
    assert c.confianza is False
    assert "sin datos" in c.razon


def test_tipo_de_ventana_desconocido_falla_ruidosamente(spot_base, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": "cuando_amanezca"}
    with pytest.raises(ValueError):
        evaluate_tide(madrid(2026, 8, 14, 12, 0), curva_chipiona, spot)


# --------------------------------------------------------------------------
# Mar
# --------------------------------------------------------------------------

def test_ola_por_encima_del_umbral_es_no(spot_base):
    c = evaluate_sea(2.0, spot_base)
    assert c.estado == NO and "2.0 m" in c.razon


def test_ola_intermedia_es_justo(spot_base):
    assert evaluate_sea(1.2, spot_base).estado == JUSTO


def test_ola_pequena_es_si(spot_base):
    assert evaluate_sea(0.4, spot_base).estado == SI


def test_umbral_de_ola_sin_calibrar_pierde_confianza(spot_base):
    spot = copy.deepcopy(spot_base)
    spot["mar"]["ola_max_m"] = PENDIENTE
    c = evaluate_sea(0.4, spot)
    assert c.confianza is False and "sin calibrar" in c.razon


def test_sin_datos_de_oleaje_no_afirma_nada(spot_base):
    assert evaluate_sea(None, spot_base).confianza is False


# --------------------------------------------------------------------------
# Combinación: la regla del más restrictivo
# --------------------------------------------------------------------------

def _hora(spot, alas_cfg, curva, **kw):
    args = {"speed_kn": 20, "gust_kn": 24, "direction_deg": 240, "wave_m": 0.5}
    args.update(kw)
    return assess_hour(madrid(2026, 8, 14, 15, 0), curve=curva, spot_cfg=spot,
                       alas_cfg=alas_cfg, rider_kg=75, **args)


def test_todo_bien_da_si(spot_base, alas_cfg, curva_chipiona):
    ev = _hora(spot_base, alas_cfg, curva_chipiona)
    assert ev.estado == SI


def test_un_solo_no_tumba_el_veredicto_completo(spot_base, alas_cfg, curva_chipiona):
    """Viento perfecto y marea perfecta, pero mar gruesa -> No."""
    ev = _hora(spot_base, alas_cfg, curva_chipiona, wave_m=2.5)
    assert ev.estado == NO
    assert any(c.clave == "mar" and c.estado == NO for c in ev.limitantes)


def test_la_marea_manda_aunque_el_viento_sea_ideal(spot_base, alas_cfg, curva_chipiona):
    ev = assess_hour(madrid(2026, 8, 14, 9, 0), speed_kn=20, gust_kn=24,
                     direction_deg=240, wave_m=0.5, curve=curva_chipiona,
                     spot_cfg=spot_base, alas_cfg=alas_cfg, rider_kg=75)
    assert ev.estado == NO
    assert [c.clave for c in ev.limitantes] == ["marea"]


def test_el_veredicto_siempre_lleva_motivo(spot_base, alas_cfg, curva_chipiona):
    for viento, ola in [(9, 0.5), (20, 2.5), (20, 0.5), (40, 0.5)]:
        ev = _hora(spot_base, alas_cfg, curva_chipiona, speed_kn=viento, wave_m=ola)
        assert ev.limitantes, "ninguna hora puede quedarse sin motivo"
        for c in ev.limitantes:
            assert c.razon.strip()


def test_justo_no_se_convierte_en_si_por_acumulacion(spot_base, alas_cfg, curva_chipiona):
    """Dos 'justo' siguen siendo 'justo', nunca 'sí'."""
    ev = _hora(spot_base, alas_cfg, curva_chipiona, speed_kn=13, gust_kn=16, wave_m=1.2)
    assert ev.estado == JUSTO
    assert {c.clave for c in ev.limitantes} == {"viento", "mar"}
    # y ningún motivo se pierde por el camino: los tres siguen presentes
    assert {c.clave for c in ev.checks} == {"viento", "marea", "mar"}


def test_una_hora_arrastra_la_falta_de_confianza(spot_base, alas_cfg, curva_chipiona):
    spot = copy.deepcopy(spot_base)
    spot["marea"]["ventana"] = {"tipo": PENDIENTE}
    spot["mar"]["ola_max_m"] = PENDIENTE
    ev = _hora(spot, alas_cfg, curva_chipiona)
    assert ev.estado == SI, "sin datos locales no inventamos un bloqueo horario"
    assert {c.clave for c in ev.sin_confianza} == {"marea", "mar"}


def test_el_ala_se_calcula_con_el_peso_del_rider(spot_base, alas_cfg, curva_chipiona):
    ligero = assess_hour(madrid(2026, 8, 14, 15, 0), speed_kn=20, gust_kn=24,
                         direction_deg=240, wave_m=0.5, curve=curva_chipiona,
                         spot_cfg=spot_base, alas_cfg=alas_cfg, rider_kg=60)
    pesado = assess_hour(madrid(2026, 8, 14, 15, 0), speed_kn=20, gust_kn=24,
                         direction_deg=240, wave_m=0.5, curve=curva_chipiona,
                         spot_cfg=spot_base, alas_cfg=alas_cfg, rider_kg=95)
    assert ligero.ala.ala_min < pesado.ala.ala_min
