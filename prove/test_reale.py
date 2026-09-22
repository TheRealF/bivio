"""Le prove che hanno bisogno dei pesi. Si accendono con BIVIO_REALE=1:

    BIVIO_REALE=1 pytest -q prove/test_reale.py
"""

import os

import pytest

reale = pytest.mark.skipif(not os.environ.get("BIVIO_REALE"),
                           reason="serve il modello scaricato: BIVIO_REALE=1")


@pytest.fixture(scope="module")
def cervello():
    from bivio import Bivio
    return Bivio()


@reale
def test_risponde_a_una_domanda_facile(cervello):
    r = cervello.chiedi("Il cielo e' azzurro e il sole splende.", "Il testo parla del tempo")
    assert r.valore is True
    assert r.probabilita > 0.5


@reale
def test_le_lettere_sono_token_singoli(cervello):
    assert len(cervello.motore._lettere) == 26


@reale
def test_lo_stato_si_legge_una_volta_sola(cervello):
    stato = "Contratto lungo. " * 200
    domande = {f"d{i}": {"tipo": "si_no", "istruzioni": "Il testo parla di un contratto"}
               for i in range(4)}
    g = cervello.grezzo(stato, domande)
    # quattro domande, ma lo stato compare una volta sola nel conto dei token
    assert g["consumo"]["token_stato"] > 100
    assert g["misure"]["ms_stato"] > 0
    assert g["consumo"]["token_uscita"] == 0


@reale
def test_stesso_stato_stesse_risposte(cervello):
    stato = "Il pagamento avverra' a sessanta giorni data fattura."
    d = {"q": {"tipo": "si_no", "istruzioni": "Il termine supera i 30 giorni"}}
    a = cervello.grezzo(stato, d)["risposte"]["q"]
    b = cervello.grezzo(stato, d)["risposte"]["q"]
    assert a["probabilita"] == b["probabilita"]
