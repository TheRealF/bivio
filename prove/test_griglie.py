"""Le griglie sono dati, e i dati sbagliati si scoprono quando serve. Qui si
controlla che ogni griglia si costruisca davvero, senza bisogno del modello."""

import pytest

from bivio.griglie import carica, elenco
from bivio.tipi import costruisci


def test_ci_sono_le_quattro():
    nomi = {g["nome"] for g in elenco()}
    assert {"assistenza", "spese", "contratto", "moderazione"} <= nomi


@pytest.mark.parametrize("nome", [g["nome"] for g in elenco()])
def test_ogni_griglia_si_costruisce(nome):
    g = carica(nome)
    assert g["titolo"] and g["per"] and g["stato"]
    for chiave, dati in g["domande"].items():
        d = costruisci(chiave, dati)
        assert len(d.opzioni) >= 2
        assert d.istruzioni


def test_griglia_sconosciuta_dice_quali_ci_sono():
    with pytest.raises(KeyError, match="assistenza"):
        carica("inventata")
