import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from lib.tides import TZ, TideCurve, TideExtreme


@pytest.fixture(scope="session")
def alas_cfg():
    return yaml.safe_load((RAIZ / "config" / "alas.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def spots_cfg():
    return yaml.safe_load((RAIZ / "config" / "spots.yaml").read_text(encoding="utf-8"))


def madrid(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


@pytest.fixture
def curva_chipiona():
    """Extremos reales devueltos por la API del IHM para Chipiona (id 39),
    14 de agosto de 2026. Verificados, no inventados."""
    return TideCurve([
        TideExtreme(madrid(2026, 8, 14, 3, 3), 3.441, "pleamar"),
        TideExtreme(madrid(2026, 8, 14, 8, 52), 0.451, "bajamar"),
        TideExtreme(madrid(2026, 8, 14, 15, 19), 3.745, "pleamar"),
        TideExtreme(madrid(2026, 8, 14, 21, 25), 0.379, "bajamar"),
    ])


@pytest.fixture
def spot_base():
    """Spot totalmente calibrado, para poder probar la lógica sin que la
    degradación por 'sin calibrar' enmascare los resultados."""
    return {
        "id": "test",
        "nombre": "Spot de prueba",
        "viento": {
            "minimo_nudos": 12,
            "maximo_nudos": 33,
            "justo_bajo_nudos": 14,
            "justo_alto_nudos": 28,
            "racha_ratio_malo": 1.6,
            "racha_ratio_justo": 1.4,
            "direcciones": {
                "buenas": [[180, 300]],
                "regulares": [[150, 180], [300, 330]],
                "malas": [[330, 360], [0, 150]],
            },
            "malas_notas": [
                {"rango": [0, 150],
                 "motivo": "Offshore, te aleja de la costa"},
            ],
        },
        "mar": {"ola_max_m": 1.5, "ola_justo_m": 1.0},
        "marea": {"ventana": {"tipo": "altura_minima", "altura_min_m": 1.8}},
    }
