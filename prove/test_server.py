"""La traduzione fra la risposta di Bivio e la forma dell'API di TypeSafe.
Non serve il modello: si parte da una risposta gia' calcolata."""

from bivio.server import _in_inglese


def test_noul():
    r = _in_inglese({"tipo": "si_no", "probabilita_si": 0.87, "probabilita": {"si": 0.87, "no": 0.13},
                     "confidenza": 0.74})
    assert r == {"type": "noul", "noul": 0.87}


def test_choice():
    r = _in_inglese({"tipo": "scelta", "valore": "billing",
                     "probabilita": {"billing": 0.9, "sales": 0.1}, "confidenza": 0.8})
    assert r["type"] == "choice" and r["choice"] == "billing"
    assert r["probabilities"]["billing"] == 0.9
    assert r["confidence"] == 0.8


def test_score_porta_la_legenda():
    r = _in_inglese({"tipo": "voto", "valore": 1.4, "legenda": {"0": "Calm", "1": "Angry"},
                     "probabilita": {"0": 0.3, "1": 0.7}, "confidenza": 0.4})
    assert r["type"] == "score" and r["score"] == 1.4
    assert r["legend"]["1"] == "Angry"
