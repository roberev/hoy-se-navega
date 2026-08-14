import pytest
from lib.wings import recommend_wing


@pytest.mark.parametrize("viento,esperado", [
    (5, "Sin viento suficiente"),
    (11.9, "Sin viento suficiente"),
    (12, "6.5–7.0 m"),
    (14.9, "6.5–7.0 m"),
    (15, "5.5–6.0 m"),
    (17.9, "5.5–6.0 m"),
    (18, "5.0 m"),
    (22, "4.5 m"),
    (26, "4.0 m"),
    (31, "3.5 m"),
])
def test_tabla_semilla_a_75_kg(viento, esperado, alas_cfg):
    assert recommend_wing(viento, 75, alas_cfg).texto() == esperado


def test_los_limites_de_tramo_son_exclusivos_por_arriba(alas_cfg):
    """15.0 nudos pertenece al tramo 15-18, no al 12-15."""
    assert recommend_wing(15.0, 75, alas_cfg).texto() == "5.5–6.0 m"


def test_rider_mas_pesado_lleva_mas_ala(alas_cfg):
    ligero = recommend_wing(20, 65, alas_cfg)
    referencia = recommend_wing(20, 75, alas_cfg)
    pesado = recommend_wing(20, 85, alas_cfg)
    assert ligero.ala_min < referencia.ala_min < pesado.ala_min


def test_escalado_es_medio_metro_cada_diez_kilos(alas_cfg):
    """La suposición documentada: ±10 kg ≈ ±0,5 m."""
    assert recommend_wing(20, 85, alas_cfg).ala_min == pytest.approx(5.5)
    assert recommend_wing(20, 65, alas_cfg).ala_min == pytest.approx(4.5)
    assert recommend_wing(20, 95, alas_cfg).ala_min == pytest.approx(6.0)


def test_no_extrapola_fuera_de_limites_de_sensatez(alas_cfg):
    """Un peso absurdo no debe producir un ala absurda."""
    r = recommend_wing(20, 250, alas_cfg)
    assert r.ala_max <= alas_cfg["escalado_peso"]["ala_max_m"]
    r = recommend_wing(20, 20, alas_cfg)
    assert r.ala_min >= alas_cfg["escalado_peso"]["ala_min_m"]


def test_sin_viento_no_hay_ala_a_ningun_peso(alas_cfg):
    for peso in (50, 75, 110):
        assert recommend_wing(8, peso, alas_cfg).navegable is False
