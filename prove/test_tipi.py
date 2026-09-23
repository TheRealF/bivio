"""Prove che non hanno bisogno del modello: la parte che si puo' sbagliare
senza accorgersene, cioe' come una domanda diventa scelta multipla e come
una distribuzione diventa una risposta."""

import math

import pytest

from bivio.tipi import (INSUFFICIENTE, Domanda, ErroreDomanda, confidenza, ruota, ruotabile,
                        costruisci, leggi)


def test_si_no_ha_due_opzioni():
    d = costruisci("urgente", {"tipo": "si_no", "istruzioni": "e' urgente"})
    assert [o.id for o in d.opzioni] == ["si", "no"]


def test_alias_inglesi():
    d = costruisci("q", {"type": "noul", "instructions": "x"})
    assert d.tipo == "si_no"
    d = costruisci("q", {"type": "choice", "instructions": "x",
                         "criteria": {"a": "prima", "b": None}})
    assert d.tipo == "scelta" and [o.id for o in d.opzioni] == ["a", "b"]


def test_astensione_aggiunge_una_opzione():
    senza = costruisci("q", {"tipo": "scelta", "istruzioni": "x",
                             "opzioni": {"a": "", "b": ""}}, astensione=False)
    con = costruisci("q", {"tipo": "scelta", "istruzioni": "x",
                           "opzioni": {"a": "", "b": ""}}, astensione=True)
    assert len(con.opzioni) == len(senza.opzioni) + 1
    assert con.opzioni[-1].id == INSUFFICIENTE
    assert con.opzioni[-1].speciale


def test_troppe_opzioni():
    tante = {f"o{i}": "" for i in range(30)}
    with pytest.raises(ErroreDomanda, match="lettere"):
        costruisci("q", {"tipo": "scelta", "istruzioni": "x", "opzioni": tante})


def test_ancore_in_ordine():
    with pytest.raises(ErroreDomanda, match="piu' piccola"):
        costruisci("q", {"tipo": "numero", "istruzioni": "x",
                         "ancore": [{"valore": 10}, {"valore": 2}]})


def test_domanda_senza_istruzioni():
    with pytest.raises(ErroreDomanda):
        costruisci("q", {"tipo": "si_no"})


def test_tipo_sconosciuto():
    with pytest.raises(ErroreDomanda, match="tipo"):
        costruisci("q", {"tipo": "indovina", "istruzioni": "x"})


def test_lettere_nel_blocco():
    d = costruisci("q", {"tipo": "scelta", "istruzioni": "x",
                         "opzioni": {"a": "prima", "b": "seconda"}})
    righe = d.blocco().splitlines()
    assert righe[0].startswith("A) a: prima")
    assert righe[1].startswith("B) b: seconda")


def test_confidenza():
    assert confidenza([1.0, 0.0, 0.0]) == pytest.approx(1.0)
    assert confidenza([1 / 3, 1 / 3, 1 / 3]) == pytest.approx(0.0)
    assert 0 < confidenza([0.6, 0.3, 0.1]) < 1


def test_leggi_si_no():
    d = costruisci("q", {"tipo": "si_no", "istruzioni": "x"}, astensione=False)
    r = leggi(d, [0.8, 0.2])
    assert r["valore"] is True
    assert r["probabilita_si"] == pytest.approx(0.8)
    r = leggi(d, [0.2, 0.8])
    assert r["valore"] is False


def test_leggi_voto_e_valore_atteso():
    d = costruisci("q", {"tipo": "voto", "istruzioni": "x",
                         "livelli": ["basso", "medio", "alto"]}, astensione=False)
    r = leggi(d, [0.0, 1.0, 0.0])
    assert r["valore"] == pytest.approx(1.0)
    r = leggi(d, [0.5, 0.0, 0.5])
    assert r["valore"] == pytest.approx(1.0)      # la media sta in mezzo
    assert r["dispersione"] == pytest.approx(1.0)  # ma la dispersione lo dice


def test_leggi_numero_media_e_mediana():
    d = costruisci("q", {"tipo": "numero", "istruzioni": "x", "unita": "ore",
                         "ancore": [{"valore": 1}, {"valore": 10}, {"valore": 100}]},
                   astensione=False)
    r = leggi(d, [0.5, 0.5, 0.0])
    assert r["valore"] == pytest.approx(5.5)
    assert r["mediana"] == pytest.approx(1)
    assert r["unita"] == "ore"


def test_astensione_annulla_il_valore():
    d = costruisci("q", {"tipo": "scelta", "istruzioni": "x",
                         "opzioni": {"a": "", "b": ""}}, astensione=True)
    r = leggi(d, [0.1, 0.1, 0.8])
    assert r["stato"] == "prove_insufficienti"
    assert r["valore"] is None
    # le probabilita' pubblicate restano leggibili, rinormalizzate sulle vere
    assert sum(r["probabilita"].values()) == pytest.approx(1.0)


def test_soglia_incerta():
    d = costruisci("q", {"tipo": "scelta", "istruzioni": "x", "soglia_incerta": 0.9,
                         "opzioni": {"a": "", "b": ""}}, astensione=False)
    assert leggi(d, [0.6, 0.4])["stato"] == "incerto"
    assert leggi(d, [0.95, 0.05])["stato"] == "ok"


# ---------------------------------------------------------------- rotazione

def test_ruota_gira_solo_le_utili():
    d = costruisci("r", {"tipo": "scelta", "istruzioni": "x",
                         "opzioni": {"a": "", "b": "", "c": ""}}, astensione=True)
    speciali_prima = [o.id for o in d.opzioni if o.speciale]
    girata, indici = ruota(d, 1)
    assert [o.id for o in girata.opzioni][:3] == ["b", "c", "a"]
    # l'astensione resta in fondo: la sua posizione fa parte di cosa vuol dire
    assert [o.id for o in girata.opzioni if o.speciale] == speciali_prima
    assert [o.id for o in girata.opzioni][3:] == speciali_prima
    # gli indici riportano ogni probabilita' al suo posto
    assert [d.opzioni[i].id for i in indici] == [o.id for o in girata.opzioni]


def test_ruota_a_giro_zero_non_tocca_niente():
    d = costruisci("r", {"tipo": "scelta", "istruzioni": "x",
                         "opzioni": {"a": "", "b": ""}}, astensione=False)
    girata, indici = ruota(d, 0)
    assert girata is d and indici == [0, 1]


def test_voto_e_numero_non_si_ruotano():
    voto = costruisci("v", {"tipo": "voto", "istruzioni": "x",
                            "livelli": ["basso", "medio", "alto"]}, astensione=False)
    assert ruotabile(voto) is False
    scelta = costruisci("s", {"tipo": "scelta", "istruzioni": "x",
                              "opzioni": {"a": "", "b": ""}}, astensione=False)
    assert ruotabile(scelta) is True


def test_una_opzione_sola_non_e_ruotabile():
    d = costruisci("s", {"tipo": "si_no", "istruzioni": "x"}, astensione=False)
    assert ruotabile(d) is True          # si_no ha due opzioni
    girata, _ = ruota(d, 1)
    assert [o.id for o in girata.opzioni][:2] == ["no", "si"]
