from bivio import prompt
from bivio.tipi import costruisci


def test_lo_stato_sta_solo_nel_prefisso():
    d = costruisci("q", {"tipo": "si_no", "istruzioni": "e' urgente"})
    pre = prompt.prefisso("il gatto e' sul tetto")
    suf = prompt.suffisso(d)
    assert "il gatto e' sul tetto" in pre
    assert "il gatto e' sul tetto" not in suf


def test_il_prefisso_non_dipende_dalla_domanda():
    a = costruisci("a", {"tipo": "si_no", "istruzioni": "prima"})
    b = costruisci("b", {"tipo": "si_no", "istruzioni": "seconda"})
    assert prompt.intero("x", a).startswith(prompt.prefisso("x"))
    assert prompt.intero("x", b).startswith(prompt.prefisso("x"))


def test_finisce_con_la_chiusura():
    d = costruisci("q", {"tipo": "si_no", "istruzioni": "x"})
    assert prompt.intero("s", d).endswith(prompt.CHIUSURA)


def test_stato_oggetto_diventa_json():
    pre = prompt.prefisso({"vita": 40, "pozioni": 1})
    assert '"vita": 40' in pre
