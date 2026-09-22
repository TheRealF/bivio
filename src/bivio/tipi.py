"""I tipi di domanda e di risposta di Bivio.

Una domanda diventa sempre una scelta multipla fra opzioni dichiarate: e'
questo che permette di leggere la risposta dai logit invece di generarla.
I quattro tipi qui sotto sono quattro modi di descrivere quelle opzioni.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# Le opzioni speciali. Occupano una lettera come tutte le altre, quindi
# togliendo l'astensione si guadagna un'opzione utile in piu'.
INSUFFICIENTE = "__insufficiente__"
SOTTO_SCALA = "__sotto_scala__"
SOPRA_SCALA = "__sopra_scala__"

LETTERE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

TIPI = ("si_no", "scelta", "voto", "numero")

# I nomi inglesi dell'API di TypeSafe, accettati anche dall'API italiana.
ALIAS_TIPO = {
    "noul": "si_no",
    "boolean": "si_no",
    "choice": "scelta",
    "score": "voto",
    "numeric": "numero",
}


class ErroreDomanda(ValueError):
    """La domanda e' scritta male: si risponde 422, non si indovina."""


def _testo(valore: Any) -> str:
    """Lo stato puo' arrivare come stringa o come oggetto gia' strutturato."""
    if isinstance(valore, str):
        return valore
    return json.dumps(valore, ensure_ascii=False, indent=2, sort_keys=False)


@dataclass
class Opzione:
    """Una riga della scelta multipla: una lettera, un id, una descrizione."""

    id: str
    descrizione: str = ""
    speciale: bool = False

    def riga(self, lettera: str) -> str:
        if self.descrizione:
            return f"{lettera}) {self.id}: {self.descrizione}"
        return f"{lettera}) {self.id}"


@dataclass
class Domanda:
    """Una domanda gia' ridotta a scelta multipla, pronta per il motore."""

    nome: str
    tipo: str
    istruzioni: str
    opzioni: list[Opzione]
    # Per i tipi numerici: il valore che ogni opzione rappresenta.
    valori: list[float] = field(default_factory=list)
    unita: str = ""
    astensione: bool = False
    soglia_incerta: float = 0.0
    temperatura: float = 1.0

    @property
    def utili(self) -> list[int]:
        """Gli indici delle opzioni che non sono astensioni."""
        return [i for i, o in enumerate(self.opzioni) if not o.speciale]

    def blocco(self) -> str:
        righe = [o.riga(LETTERE[i]) for i, o in enumerate(self.opzioni)]
        return "\n".join(righe)


# --------------------------------------------------------------------------
# Costruzione delle domande a partire dal dizionario che arriva dall'utente
# --------------------------------------------------------------------------

def _descrizioni(criteri: Any) -> list[tuple[str, str]]:
    """`criteri` accetta le tre forme dell'API originale: dizionario, lista,
    stringa. Torna sempre una lista ordinata di coppie (id, descrizione)."""
    if criteri is None:
        return []
    if isinstance(criteri, dict):
        return [(str(k), "" if v is None else str(v)) for k, v in criteri.items()]
    if isinstance(criteri, (list, tuple)):
        fuori = []
        for v in criteri:
            if isinstance(v, dict):
                nome = v.get("id", v.get("nome", v.get("name", v.get("valore"))))
                fuori.append((str(nome), str(v.get("descrizione", v.get("description", "")))))
            else:
                fuori.append((str(v), ""))
        return fuori
    raise ErroreDomanda("le opzioni vanno date come dizionario o come lista")


def costruisci(nome: str, dati: dict, astensione: bool = False) -> Domanda:
    """Da un dizionario scritto da una persona a una Domanda controllata."""
    if not isinstance(dati, dict):
        raise ErroreDomanda(f"la domanda «{nome}» non e' un oggetto")

    tipo = str(dati.get("tipo") or dati.get("type") or "").strip().lower()
    tipo = ALIAS_TIPO.get(tipo, tipo)
    if tipo not in TIPI:
        raise ErroreDomanda(
            f"la domanda «{nome}» ha tipo «{tipo or 'mancante'}»: "
            f"i tipi sono {', '.join(TIPI)}"
        )

    istruzioni = str(dati.get("istruzioni") or dati.get("instructions") or "").strip()
    if not istruzioni:
        raise ErroreDomanda(f"la domanda «{nome}» non dice che cosa chiede")

    astensione = bool(dati.get("astensione", dati.get("allow_abstain", astensione)))
    criteri = dati.get("opzioni", dati.get("criteri", dati.get("criteria")))
    if criteri is None and tipo == "voto":
        criteri = dati.get("livelli")
    if criteri is None and tipo == "numero":
        criteri = dati.get("ancore", dati.get("anchors"))

    opzioni: list[Opzione] = []
    valori: list[float] = []

    if tipo == "si_no":
        coppie = dict(_descrizioni(criteri))
        vero = coppie.get("vero") or coppie.get("true") or "Si'"
        falso = coppie.get("falso") or coppie.get("false") or "No"
        opzioni = [Opzione("si", str(vero)), Opzione("no", str(falso))]

    elif tipo == "scelta":
        coppie = _descrizioni(criteri)
        if len(coppie) < 2:
            raise ErroreDomanda(f"la domanda «{nome}» ha meno di due opzioni")
        opzioni = [Opzione(i, d) for i, d in coppie]

    elif tipo == "voto":
        coppie = _descrizioni(criteri)
        if len(coppie) < 2:
            raise ErroreDomanda(f"la domanda «{nome}» ha meno di due livelli")
        for n, (etichetta, descr) in enumerate(coppie):
            opzioni.append(Opzione(str(n), (etichetta + (": " + descr if descr else "")).strip()))
            valori.append(float(n))

    elif tipo == "numero":
        grezze = criteri or []
        if not isinstance(grezze, (list, tuple)) or len(grezze) < 2:
            raise ErroreDomanda(f"la domanda «{nome}» vuole almeno due ancore")
        for a in grezze:
            if not isinstance(a, dict) or ("valore" not in a and "value" not in a):
                raise ErroreDomanda(f"l'ancora di «{nome}» vuole un campo «valore»")
            v = float(a.get("valore", a.get("value")))
            d = str(a.get("descrizione", a.get("description", "")))
            valori.append(v)
            opzioni.append(Opzione(_numero_leggibile(v), d))
        if valori != sorted(valori):
            raise ErroreDomanda(f"le ancore di «{nome}» vanno dalla piu' piccola alla piu' grande")

    unita = str(dati.get("unita", dati.get("unit", "")))

    if astensione:
        opzioni.append(Opzione(INSUFFICIENTE, "Lo stato non basta per rispondere", speciale=True))
        if tipo == "numero":
            opzioni.append(Opzione(SOTTO_SCALA, f"Meno di {opzioni[0].id}", speciale=True))
            opzioni.append(Opzione(SOPRA_SCALA, f"Piu' di {opzioni[len(valori) - 1].id}", speciale=True))

    if len(opzioni) > len(LETTERE):
        raise ErroreDomanda(
            f"la domanda «{nome}» ha {len(opzioni)} opzioni e le lettere sono {len(LETTERE)}: "
            "spezzala in due passi"
        )

    return Domanda(
        nome=nome,
        tipo=tipo,
        istruzioni=istruzioni,
        opzioni=opzioni,
        valori=valori,
        unita=unita,
        astensione=astensione,
        soglia_incerta=float(dati.get("soglia_incerta", dati.get("uncertain_below", 0.0))),
        temperatura=float(dati.get("temperatura", dati.get("temperature", 1.0))),
    )


def _numero_leggibile(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


# --------------------------------------------------------------------------
# Dalle probabilita' alla risposta tipizzata
# --------------------------------------------------------------------------

def confidenza(probabilita: list[float]) -> float:
    """(n·p_max − 1) / (n − 1): quanto la distribuzione e' lontana dal caso.

    E' la statistica che TypeSafe mostra nella sua pagina sulla confidenza.
    Descrive la forma della distribuzione, non la probabilita' di aver
    ragione: un modello puo' essere sicurissimo e sbagliato.
    """
    n = len(probabilita)
    if n < 2:
        return 1.0
    return max(0.0, (n * max(probabilita) - 1.0) / (n - 1.0))


def _mediana(valori: list[float], pesi: list[float]) -> float:
    """Il quantile 0,5 della distribuzione discreta sulle ancore."""
    somma = 0.0
    totale = sum(pesi) or 1.0
    for v, p in zip(valori, pesi):
        somma += p / totale
        if somma >= 0.5:
            return v
    return valori[-1]


def leggi(domanda: Domanda, probabilita: list[float]) -> dict:
    """Traduce la distribuzione sulle lettere nella risposta del tipo giusto."""
    per_id = {o.id: float(p) for o, p in zip(domanda.opzioni, probabilita)}
    speciali = {o.id: float(p) for o, p in zip(domanda.opzioni, probabilita) if o.speciale}
    utili = domanda.utili
    p_utili = [probabilita[i] for i in utili]
    massa = sum(p_utili)

    # Chi vince fra tutte le opzioni, astensioni comprese.
    vincitore = max(range(len(probabilita)), key=lambda i: probabilita[i])
    opzione_vincente = domanda.opzioni[vincitore]

    stato = "ok"
    if opzione_vincente.id == INSUFFICIENTE:
        stato = "prove_insufficienti"
    elif opzione_vincente.id in (SOTTO_SCALA, SOPRA_SCALA):
        stato = "fuori_scala"
    elif domanda.soglia_incerta and max(p_utili) < domanda.soglia_incerta:
        stato = "incerto"

    # Le probabilita' pubblicate sono rinormalizzate sulle opzioni vere,
    # cosi' «il 70% e' billing» resta leggibile anche con l'astensione accesa.
    if massa > 0:
        normali = {domanda.opzioni[i].id: probabilita[i] / massa for i in utili}
    else:
        normali = {domanda.opzioni[i].id: 0.0 for i in utili}

    fuori: dict[str, Any] = {
        "tipo": domanda.tipo,
        "stato": stato,
        "probabilita": {k: round(v, 6) for k, v in normali.items()},
        "confidenza": round(confidenza(list(normali.values())), 6),
    }
    if speciali:
        fuori["speciali"] = {k: round(v, 6) for k, v in speciali.items()}

    buona = stato == "ok"

    if domanda.tipo == "si_no":
        p_si = normali.get("si", 0.0)
        fuori["probabilita_si"] = round(p_si, 6)
        fuori["valore"] = bool(p_si >= 0.5) if buona else None

    elif domanda.tipo == "scelta":
        fuori["valore"] = max(normali, key=normali.get) if buona else None

    elif domanda.tipo == "voto":
        pesi = [normali[domanda.opzioni[i].id] for i in utili]
        atteso = sum(v * p for v, p in zip(domanda.valori, pesi))
        massimo = domanda.valori[-1] or 1.0
        fuori["valore"] = round(atteso, 4) if buona else None
        fuori["voto_normalizzato"] = round(atteso / massimo, 4) if buona else None
        fuori["legenda"] = {o.id: o.descrizione for i, o in enumerate(domanda.opzioni) if not o.speciale}
        fuori["dispersione"] = round(_dispersione(domanda.valori, pesi), 4)

    elif domanda.tipo == "numero":
        pesi = [normali[domanda.opzioni[i].id] for i in utili]
        atteso = sum(v * p for v, p in zip(domanda.valori, pesi))
        fuori["valore"] = round(atteso, 4) if buona else None
        fuori["mediana"] = round(_mediana(domanda.valori, pesi), 4) if buona else None
        fuori["dispersione"] = round(_dispersione(domanda.valori, pesi), 4)
        fuori["unita"] = domanda.unita

    fuori["_grezze"] = {k: round(v, 6) for k, v in per_id.items()}
    return fuori


def _dispersione(valori: list[float], pesi: list[float]) -> float:
    """Scarto quadratico medio della distribuzione discreta."""
    totale = sum(pesi) or 1.0
    media = sum(v * p for v, p in zip(valori, pesi)) / totale
    var = sum(p * (v - media) ** 2 for v, p in zip(valori, pesi)) / totale
    return math.sqrt(max(var, 0.0))
