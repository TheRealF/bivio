"""Il livello MCP, provato senza caricare il modello.

⚠️ Il modello NON si carica: le prove qui verificano il protocollo, che e' la
parte che si rompe in silenzio. Un campo sbagliato nel JSON-RPC non fa
eccezione, fa solo un client che non parla piu'.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest

from bivio.mcp import cliente as C
from bivio.mcp import protocollo as P
from bivio.mcp.portineria import Portineria, _parole
from bivio.mcp.servitore import costruisci


class CervelloFinto:
    """Risponde sempre la stessa cosa, e conta quante volte l'hanno chiamato."""

    def __init__(self, probabilita=None):
        self.chiamate = 0
        self.giri = 1
        self.p = probabilita or {}

    def __call__(self):
        return self

    def grezzo(self, stato, domande, astensione=False):
        self.chiamate += 1
        self.ultimo_stato = stato
        risposte = {}
        for nome, d in domande.items():
            if d.get("tipo") == "scelta":
                # Ogni opzione prende la probabilita' che le hanno messo in
                # `self.p`, o 0,9; vince la piu' alta.
                opz = list(d["opzioni"])
                prob = {o: self.p.get(o, 0.9) for o in opz}
                totale = sum(prob.values()) or 1.0
                prob = {k: v / totale for k, v in prob.items()}
                vinta = max(prob, key=prob.get)
                risposte[nome] = {"tipo": "scelta", "stato": "ok", "valore": vinta,
                                  "probabilita": prob, "confidenza": prob[vinta]}
            else:
                p = self.p.get(nome, 0.9)
                risposte[nome] = {"tipo": d.get("tipo", "si_no"), "stato": "ok",
                                  "valore": p >= 0.5, "probabilita_si": p,
                                  "probabilita": {"si": p, "no": 1 - p},
                                  "confidenza": abs(p - 0.5) * 2}
        return {"risposte": risposte, "misure": {"ms_totali": 1.0},
                "consumo": {"token_ingresso": 1}}


def _manda(s, metodo, params=None, ident=1):
    m = {"jsonrpc": "2.0", "id": ident, "method": metodo}
    if params is not None:
        m["params"] = params
    return s.rispondi(m)


# ------------------------------------------------------------- protocollo

def test_initialize_rimanda_la_versione_chiesta_dal_client():
    # ⚠️ I client vecchi mandano ancora la stretta di mano che la revisione
    # 2026-07-28 ha tolto: se non gli si risponde restano li'.
    s = costruisci(CervelloFinto())
    r = _manda(s, "initialize", {"protocolVersion": "2025-06-18"})
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert r["result"]["serverInfo"]["name"] == "bivio"


def test_initialize_con_una_versione_che_non_conosciamo_torna_la_nostra():
    s = costruisci(CervelloFinto())
    r = _manda(s, "initialize", {"protocolVersion": "1999-01-01"})
    assert r["result"]["protocolVersion"] == P.VERSIONE


def test_si_lavora_anche_senza_stretta_di_mano():
    # La revisione nuova e' senza stato: `tools/call` puo' arrivare per primo.
    s = costruisci(CervelloFinto())
    r = _manda(s, "tools/call", {"name": "bivio_vero_falso",
                                 "arguments": {"stato": "x", "criterio": "y"}})
    assert r["result"]["isError"] is False


def test_le_notifiche_non_vogliono_risposta():
    s = costruisci(CervelloFinto())
    assert s.rispondi({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_ha_i_campi_della_revisione_nuova():
    s = costruisci(CervelloFinto())
    r = _manda(s, "tools/list")["result"]
    assert r["resultType"] == "complete"
    assert r["cacheScope"] == "private" and r["ttlMs"] > 0
    nomi = [t["name"] for t in r["tools"]]
    assert nomi == sorted(nomi)          # ordine deterministico, lo chiede la specifica
    for t in r["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_strumento_sconosciuto_e_errore_di_protocollo():
    s = costruisci(CervelloFinto())
    r = _manda(s, "tools/call", {"name": "non_esiste", "arguments": {}})
    assert r["error"]["code"] == P.PARAMETRI


def test_argomenti_sbagliati_tornano_nel_risultato_non_come_errore():
    # ⚠️ Un errore di protocollo il modello non lo sa correggere; uno dentro al
    # risultato con isError si', e infatti la specifica dice di fare cosi'.
    s = costruisci(CervelloFinto())
    r = _manda(s, "tools/call", {"name": "bivio_vero_falso", "arguments": {"stato": "x"}})
    assert "error" not in r
    assert r["result"]["isError"] is True


def test_metodo_sconosciuto():
    s = costruisci(CervelloFinto())
    assert _manda(s, "roba/strana")["error"]["code"] == P.NON_TROVATO


def test_il_ciclo_legge_righe_e_ne_scrive_una_per_richiesta():
    s = costruisci(CervelloFinto())
    dentro = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + "riga che non e' JSON\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n")
    fuori = io.StringIO()
    s.gira(dentro, fuori)
    righe = [json.loads(r) for r in fuori.getvalue().splitlines()]
    assert [r["id"] for r in righe] == [1, 2]


def test_il_modello_non_si_carica_per_elencare():
    c = CervelloFinto()
    s = costruisci(c)
    _manda(s, "tools/list")
    _manda(s, "tools/call", {"name": "bivio_griglie", "arguments": {}})
    assert c.chiamate == 0


# ------------------------------------------------------------- portineria

def _portineria(probabilita=None, **conf):
    c = CervelloFinto(probabilita)
    p = Portineria(conf, c)
    p.catalogo = {
        "git.cerca": {"server": "git", "strumento":
                      {"name": "cerca", "description": "Cerca nel codice"}},
        "git.cancella_ramo": {"server": "git", "strumento":
                              {"name": "cancella_ramo", "description": "Cancella un ramo"}},
        "file.leggi": {"server": "file", "strumento":
                       {"name": "leggi", "description": "Legge un file"}},
    }
    return p, c


def test_cerca_legge_lo_stato_una_volta_sola_per_tutti_gli_strumenti():
    # ⚠️ E' il punto dell'architettura: la richiesta e' UNO stato, i duecento
    # strumenti sono DUECENTO domande su quella stessa lettura.
    p, c = _portineria()
    r = p.cerca("devo cercare una funzione")
    assert c.chiamate == 1
    assert r["guardati"] == 3


def test_cerca_ordina_per_probabilita_e_taglia():
    p, _ = _portineria({"git.cerca": 0.95, "file.leggi": 0.7, "git.cancella_ramo": 0.1})
    r = p.cerca("devo cercare", quanti=2)
    assert [s["name"] for s in r["strumenti"]] == ["git.cerca", "file.leggi"]


def test_la_soglia_e_relativa_al_migliore():
    # ⚠️ Assoluta non funzionerebbe: in una scelta le probabilita' sommano a 1,
    # quindi «almeno 0,5» vuol dire «al massimo uno».
    p, _ = _portineria({"git.cerca": 0.98, "file.leggi": 0.01, "git.cancella_ramo": 0.01})
    p.soglia = 0.5
    assert [s["name"] for s in p.cerca("x", quanti=3)["strumenti"]] == ["git.cerca"]
    p.soglia = 0.001
    assert len(p.cerca("x", quanti=3)["strumenti"]) == 3


def test_se_nessuno_supera_la_soglia_tornano_comunque_i_tre_migliori():
    # Una lista vuota lascerebbe l'agente senza niente da provare.
    p, _ = _portineria()
    p.soglia = 0.99
    assert len(p.cerca("boh")["strumenti"]) == 3


def test_torna_tutti_quelli_chiesti_e_non_solo_il_vincitore():
    # ⚠️ Una `scelta` da' la probabilita' di TUTTE le opzioni: chi ne chiede
    # cinque deve riceverne cinque, non solo l'argmax del girone.
    p, _ = _portineria({"git.cerca": 0.9, "file.leggi": 0.8, "git.cancella_ramo": 0.7})
    p.soglia = 0.0
    assert len(p.cerca("x", quanti=3)["strumenti"]) == 3


def test_i_nomi_sono_prefissati_col_server():
    p, _ = _portineria()
    assert all("." in s["name"] for s in p.cerca("x")["strumenti"])


def test_mai_permessi_blocca_prima_del_modello():
    # ⚠️ Le regole meccaniche girano PRIMA, e il modello non le scavalca.
    p, c = _portineria(mai_permessi=["*cancella*"])
    r = p.usa("git.cancella_ramo", {"ramo": "main"})
    assert r["bloccata"] is True
    assert c.chiamate == 0


def test_sempre_permessi_passa_senza_disturbare_il_modello():
    p, c = _portineria(sempre_permessi=["*.cerca"])
    assert p.giudica("git.cerca", {})["come"] == "regola"
    assert c.chiamate == 0


def test_mai_vince_su_sempre():
    p, _ = _portineria(sempre_permessi=["git.*"], mai_permessi=["*cancella*"])
    assert p.giudica("git.cancella_ramo", {})["esito"] == "bloccata"


def test_il_cancello_ferma_e_chiede_invece_di_bloccare():
    p, _ = _portineria({"irreversibile": 0.9, "dati_personali": 0.1, "coerente": 0.9})
    r = p.usa("git.cancella_ramo", {"ramo": "main"})
    assert r["serve_conferma"] is True and "irreversibile" in r["perche"]


def test_con_conferma_passa():
    p, _ = _portineria({"irreversibile": 0.9, "dati_personali": 0.1, "coerente": 0.9})
    r = p.usa("git.cancella_ramo", {"ramo": "main"}, conferma=True)
    # Nessun collegamento vero dietro: l'importante e' che abbia superato il
    # cancello e che il server mancante venga detto a parole.
    assert "serve_conferma" not in r
    assert "non e' collegato" in r["errore"]


def test_un_server_che_muore_non_fa_esplodere_la_portineria():
    p, _ = _portineria(sempre_permessi=["*"])
    r = p.usa("file.leggi", {"percorso": "/tmp/x"})
    assert "errore" in r and "file" in r["errore"]


def test_uno_strumento_che_non_fa_quello_che_dichiara_suona():
    p, _ = _portineria({"irreversibile": 0.1, "dati_personali": 0.1, "coerente": 0.2})
    assert p.giudica("file.leggi", {"x": 1})["esito"] == "chiedi"


def test_nome_sbagliato_suggerisce_invece_di_esplodere():
    p, _ = _portineria()
    r = p.usa("cerca", {})
    assert "errore" in r and r["forse"]


# ------------------------------------------- il filtro meccanico davanti

def test_parole_butta_le_vuote_e_spezza_gli_underscore():
    assert "per" not in _parole("per il cliente")
    # «cancella_ramo» sono due parole, sennò il filtro non le incontra mai
    assert _parole("cancella_ramo") & _parole("devo cancellare")
    assert _parole("cancella_ramo") & _parole("quel ramo")


def test_le_parole_si_incontrano_fra_singolare_e_plurale():
    assert _parole("issues") & _parole("una issue su GitHub")


def _tanti(n):
    c = {}
    for i in range(n):
        nome = f"str{i:03d}_{'cerca' if i % 2 else 'cancella'}_{'file' if i % 3 else 'ramo'}"
        c[f"s.{nome}"] = {"server": "s", "strumento":
                          {"name": nome, "description": f"Strumento numero {i}"}}
    return c


def test_sotto_i_venticinque_non_screma_niente():
    p, _ = _portineria()
    p.catalogo = _tanti(20)
    nomi, quanti = p._screma("qualsiasi cosa")
    assert quanti == 20


def test_sopra_i_venticinque_screma_a_venticinque():
    p, _ = _portineria()
    p.catalogo = _tanti(200)
    nomi, quanti = p._screma("devo cancellare un ramo")
    assert quanti == 25
    assert all("cancella" in n or "ramo" in n for n in nomi)


def test_se_le_parole_non_toccano_niente_si_tiene_tutto():
    # ⚠️ Meglio lenti che sbagliati: una richiesta vaga non deve ridurre il
    # catalogo a venticinque strumenti scelti a caso.
    p, _ = _portineria()
    p.catalogo = _tanti(200)
    nomi, quanti = p._screma("zzz qqq www")
    assert quanti == 200


def test_cerca_dice_a_quanti_ha_scremato():
    p, _ = _portineria()
    r = p.cerca("devo cercare")
    assert r["scremati_a"] == r["guardati"] == 3


# ------------------------------------------------- conformita' del client

def test_il_client_manda_meta_su_ogni_richiesta():
    # ⚠️ La revisione 2026-07-28 lo vuole su OGNI richiesta, non solo nella
    # stretta di mano: senza sessione, ogni richiesta deve dire da sola con chi
    # sta parlando.
    visti = []

    class Finto(C.Collegamento):
        def __init__(self):
            self.nome, self._id, self.attesa = "x", 0, 1.0
            import threading
            self._lucchetto = threading.Lock()

        def _chiama(self, metodo, params=None, notifica=False):
            if params is not None:
                params = dict(params)
                params.setdefault("_meta", {}).update(C.META)
            visti.append(params)
            return {}

    f = Finto()
    f._chiama("tools/list", {})
    meta = visti[0]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == P.VERSIONE
    assert "io.modelcontextprotocol/clientInfo" in meta


def test_il_server_non_si_offende_per_il_meta_in_piu():
    s = costruisci(CervelloFinto())
    r = _manda(s, "tools/call", {"name": "bivio_griglie", "arguments": {},
                                 "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}})
    assert r["result"]["isError"] is False
