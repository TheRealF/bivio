import math

import pytest

from bivio.taratura import cerca_temperatura, misura


def test_una_temperatura_alta_smussa_una_distribuzione_troppo_sicura():
    # il modello dice sempre 0,999 e sbaglia una volta su quattro
    dist = [{"a": 0.999, "b": 0.001}] * 4
    attese = ["a", "a", "a", "b"]
    t = cerca_temperatura(dist, attese)
    assert t > 1.5
    prima = misura(dist, attese, 1.0)
    dopo = misura(dist, attese, t)
    assert dopo["nll"] < prima["nll"]
    assert dopo["accuratezza"] == prima["accuratezza"]   # l'ordine non cambia


def test_una_distribuzione_gia_onesta_non_si_tocca_troppo():
    dist = [{"a": 0.75, "b": 0.25}] * 4
    attese = ["a", "a", "a", "b"]
    t = cerca_temperatura(dist, attese)
    assert 0.5 < t < 2.5


def test_ece_e_zero_quando_la_fiducia_e_giusta():
    dist = [{"a": 1.0, "b": 0.0}] * 10
    m = misura(dist, ["a"] * 10, 1.0)
    assert m["accuratezza"] == 1.0
    assert m["ece"] == pytest.approx(0.0, abs=1e-6)
