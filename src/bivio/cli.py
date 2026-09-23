"""La riga di comando: `bivio <comando>`."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__, modelli


def _cervello(args, **extra):
    from .decisione import Bivio
    from .taratura import carica
    avvio = time.perf_counter()
    b = Bivio(
        modello=getattr(args, "modello", modelli.PREDEFINITO),
        contesto=getattr(args, "contesto", 8192),
        gpu=getattr(args, "gpu", -1),
        thread=getattr(args, "thread", None),
        verboso=getattr(args, "verboso", False),
        giri=getattr(args, "giri", 1),
        **extra,
    )
    percorso = getattr(args, "taratura", None)
    if percorso:
        b.taratura = carica(percorso, b.impronta())
        print(f"Taratura: {b.taratura.get('temperature')}", file=sys.stderr)
    print(f"Modello caricato in {time.perf_counter() - avvio:.1f} s.", file=sys.stderr)
    return b


# ---------------------------------------------------------------- comandi

def c_modelli(args):
    for chiave, s in modelli.CATALOGO.items():
        segno = "scaricato" if modelli.presente(chiave) else "da scaricare"
        print(f"{chiave:>6}  {s.file}  {s.byte / (1 << 30):.2f} GB  [{segno}]")
        print(f"        {s.nota}  Licenza {s.licenza}")
    print(f"\nCartella: {modelli.CARTELLA}")
    return 0


def c_scarica(args):
    modelli.scarica(args.modello, forza=args.forza)
    return 0


def c_serve(args):
    from .server import avvia
    if not modelli.presente(args.modello):
        print("Il modello non c'e'. Lo scarico adesso.", file=sys.stderr)
        modelli.scarica(args.modello)
    b = _cervello(args)
    chiave = args.chiave or os.environ.get("BIVIO_API_KEY")
    avvia(b, porta=args.porta, indirizzo=args.indirizzo, chiave=chiave)
    return 0


def c_mcp(args):
    """Bivio come server MCP, su stdio."""
    from .mcp.servitore import avvia
    return avvia(modello=args.modello, contesto=args.contesto, gpu=args.gpu,
                 thread=args.thread, giri=args.giri, verboso=False)


ESEMPIO_PORTINERIA = {
    "server": {
        "github": {"comando": "npx", "argomenti": ["-y", "@modelcontextprotocol/server-github"],
                   "ambiente": {"GITHUB_TOKEN": "mettilo qui o lascialo nell'ambiente"}},
        "file": {"comando": "npx", "argomenti": ["-y", "@modelcontextprotocol/server-filesystem",
                                                 "/Users/tu/Documents"]},
    },
    "quanti": 5,
    "soglia": 0.1,
    "sempre_permessi": ["*.search_*", "*.list_*", "*.read_*", "*.get_*"],
    "mai_permessi": ["*delete*", "*force_push*", "*.write_file"],
    "regole": {
        "fuori_italia": "La chiamata manda del testo a un servizio fuori dall'Unione Europea",
    },
}


def c_portineria(args):
    """La portineria MCP: meno strumenti in contesto, e un cancello sulle chiamate."""
    if args.esempio:
        print(json.dumps(ESEMPIO_PORTINERIA, ensure_ascii=False, indent=2))
        return 0
    if not args.configurazione:
        print("Serve un file di configurazione. Per vederne uno:\n"
              "  bivio portineria --esempio > portineria.json", file=sys.stderr)
        return 2
    with open(args.configurazione, encoding="utf-8") as f:
        conf = json.load(f)
    from .mcp.portineria import avvia
    from .mcp.servitore import Cervello
    cervello = Cervello(modello=args.modello, contesto=args.contesto, gpu=args.gpu,
                        thread=args.thread, verboso=False)
    return avvia(conf, cervello)


def c_griglie(args):
    from .griglie import carica, elenco
    if args.nome:
        g = carica(args.nome)
        print(json.dumps(g, ensure_ascii=False, indent=2))
        return 0
    for g in elenco():
        print(f"{g['nome']:<14} {g['titolo']}  ({g['domande']} domande)")
        print(f"               {g['per']}")
    print("\nSi usa cosi':  bivio decidi --griglia assistenza messaggio.txt")
    print("Per copiarne una e cambiarla:  bivio griglie assistenza > mia.json")
    return 0


def c_decidi(args):
    if args.griglia:
        from .griglie import carica
        domande = carica(args.griglia)["domande"]
        if os.path.exists(args.file):
            with open(args.file, encoding="utf-8") as f:
                stato = f.read()
        else:
            stato = args.file          # il testo dato direttamente sulla riga
    else:
        with open(args.file, encoding="utf-8") as f:
            corpo = json.load(f)
        stato = corpo.get("stato", corpo.get("state"))
        domande = corpo.get("domande", corpo.get("questions"))
    if stato is None or not domande:
        print("Il file vuole «stato» e «domande», oppure usa --griglia.", file=sys.stderr)
        return 2
    b = _cervello(args)
    fuori = b.grezzo(stato, domande, astensione=args.astensione)
    print(json.dumps(fuori, ensure_ascii=False, indent=2))
    return 0


def c_molti(args):
    """Tante righe, la stessa griglia, una riga di risposta per ognuna.

    ⚠️ Il modello si carica UNA volta sola: e' tutto il senso di questo
    comando. Chiamare `bivio decidi` in un ciclo della shell ricarica 2,5 GB
    a ogni riga, e su cinquecento ticket vuol dire un'ora buttata.
    """
    from .griglie import carica
    domande = carica(args.griglia)["domande"] if args.griglia else None
    righe = []
    with open(args.file, encoding="utf-8") as f:
        for n, riga in enumerate(f, 1):
            riga = riga.strip()
            if not riga:
                continue
            if args.griglia and not riga.startswith("{"):
                righe.append({"stato": riga, "domande": domande, "riga": n})
                continue
            d = json.loads(riga)
            righe.append({"stato": d.get("stato", d.get("state", d.get("testo"))),
                          "domande": d.get("domande") or domande,
                          "id": d.get("id"), "riga": n})
    if not righe:
        print("Il file e' vuoto.", file=sys.stderr)
        return 2
    if any(r["domande"] is None for r in righe):
        print("Serve --griglia, oppure «domande» dentro a ogni riga.", file=sys.stderr)
        return 2

    b = _cervello(args)
    uscita = open(args.uscita, "w", encoding="utf-8") if args.uscita else sys.stdout
    fatti = errori = 0
    avvio = time.perf_counter()
    try:
        for r in righe:
            try:
                fuori = b.grezzo(r["stato"], r["domande"],
                                 astensione=args.astensione)
                out = {"id": r.get("id") or r["riga"],
                       "risposte": {k: v.get("valore") for k, v in fuori["risposte"].items()},
                       "confidenza": {k: v.get("confidenza")
                                      for k, v in fuori["risposte"].items()},
                       "ms": fuori["misure"]["ms_totali"]}
                if args.tutto:
                    out["grezzo"] = fuori
                fatti += 1
            except Exception as e:      # una riga storta non ferma le altre
                out = {"id": r.get("id") or r["riga"], "errore": f"{type(e).__name__}: {e}"}
                errori += 1
            uscita.write(json.dumps(out, ensure_ascii=False) + "\n")
            uscita.flush()
            if fatti % 25 == 0:
                print(f"  {fatti}/{len(righe)}", file=sys.stderr)
    finally:
        if args.uscita:
            uscita.close()
    secondi = time.perf_counter() - avvio
    print(f"\n{fatti} righe in {secondi:.1f} s ({secondi / max(fatti, 1) * 1000:.0f} ms l'una)"
          + (f", {errori} saltate" if errori else ""), file=sys.stderr)
    return 1 if errori else 0


def c_prova(args):
    """Una prova che si vede a occhio: sei decisioni su tre stati."""
    b = _cervello(args)
    casi = [
        ("Provo da tre giorni a collegare il conto Stripe e continua a fallire. "
         "Sto perdendo vendite, aiutatemi subito.",
         {"urgente": {"tipo": "si_no", "istruzioni": "Il messaggio esprime urgenza o una scadenza"},
          "reparto": {"tipo": "scelta", "istruzioni": "Chi deve prendere in carico la richiesta",
                      "opzioni": {"pagamenti": "Incassi, fatture, rimborsi",
                                  "tecnico": "Errori e malfunzionamenti",
                                  "commerciale": "Preventivi e nuovi contratti"}}}),
        ("Buongiorno, volevo sapere se il corso di Excel parte anche di sabato. Grazie.",
         {"urgente": {"tipo": "si_no", "istruzioni": "Il messaggio esprime urgenza o una scadenza"},
          "tono": {"tipo": "voto", "istruzioni": "Quanto e' scontento chi scrive",
                   "livelli": ["Tranquillo", "Infastidito", "Furioso"]}}),
        ("Il cliente ha scritto solo: «ok».",
         {"reparto": {"tipo": "scelta", "istruzioni": "Chi deve prendere in carico la richiesta",
                      "opzioni": {"pagamenti": "Incassi e fatture", "tecnico": "Errori",
                                  "commerciale": "Preventivi"}}}),
    ]
    tempi = []
    for stato, domande in casi:
        avvio = time.perf_counter()
        risposte = b.decidi(stato, domande)
        tempi.append((time.perf_counter() - avvio) * 1000)
        print("\n" + stato[:80] + ("..." if len(stato) > 80 else ""))
        for nome, r in risposte.items():
            print(f"   {nome:<10} {str(r.valore):<14} p={r.probabilita:.3f}  "
                  f"conf={r.confidenza:.3f}  [{r.stato}]")
    print(f"\n{sum(len(d) for _, d in casi)} decisioni, "
          f"{sum(tempi):.0f} ms in tutto, 0 token generati.")
    return 0


def c_taratura(args):
    from .taratura import leggi_jsonl, tara
    voci = leggi_jsonl(args.dati)
    b = _cervello(args)
    fuori = tara(b, voci)
    with open(args.uscita, "w", encoding="utf-8") as f:
        json.dump(fuori, f, ensure_ascii=False, indent=2)
    for tipo in fuori["temperature"]:
        print(f"{tipo}: temperatura {fuori['temperature'][tipo]}")
        print(f"   prima {fuori['prima'][tipo]}")
        print(f"   dopo  {fuori['dopo'][tipo]}")
    print(f"\nScritto in {args.uscita}. Si usa con: bivio serve --taratura {args.uscita}")
    return 0


# ------------------------------------------------------------------ argomenti

def principale(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="bivio",
        description="Decisioni tipizzate da un modello linguistico, in locale, "
                    "senza generare un token.",
    )
    p.add_argument("--versione", action="version", version=f"bivio {__version__}")
    sotto = p.add_subparsers(dest="comando")

    def comuni(s, modello=True):
        if modello:
            s.add_argument("-m", "--modello", default=modelli.PREDEFINITO,
                           help="4b (predefinito), 1.7b, oppure il percorso di un .gguf")
        s.add_argument("--contesto", type=int, default=8192,
                       help="token massimi per domanda (stato compreso)")
        s.add_argument("--gpu", type=int, default=-1,
                       help="strati sulla scheda video: -1 tutti, 0 nessuno")
        s.add_argument("--thread", type=int, default=None)
        s.add_argument("--taratura", default=None, help="il file scritto da «bivio taratura»")
        s.add_argument("--giri", type=int, default=1, metavar="N",
                       help="chiede N volte con le opzioni in ordine diverso e fa la "
                            "media: toglie il vantaggio della prima lettera. Costa solo "
                            "la seconda meta' del prompt, perche' lo stato resta in cache")
        s.add_argument("--verboso", action="store_true")

    s = sotto.add_parser("modelli", help="che modelli conosce e quali ci sono gia'")
    s.set_defaults(fai=c_modelli)

    s = sotto.add_parser("scarica", help="scarica il modello")
    s.add_argument("-m", "--modello", default=modelli.PREDEFINITO)
    s.add_argument("--forza", action="store_true")
    s.set_defaults(fai=c_scarica)

    s = sotto.add_parser("serve", help="accende il server e il campo di prova")
    comuni(s)
    s.add_argument("--porta", type=int, default=8017)
    s.add_argument("--indirizzo", default="127.0.0.1")
    s.add_argument("--chiave", default=None, help="chiede Bearer su /v1 (o BIVIO_API_KEY)")
    s.set_defaults(fai=c_serve)

    s = sotto.add_parser("mcp", help="Bivio come server MCP, dentro al tuo agente")
    comuni(s)
    s.set_defaults(fai=c_mcp)

    s = sotto.add_parser("portineria",
                         help="sta fra l'agente e i server MCP: tre strumenti invece "
                              "di duecento, e un cancello sulle chiamate")
    comuni(s)
    s.add_argument("configurazione", nargs="?", help="il .json dei server di dietro")
    s.add_argument("--esempio", action="store_true", help="stampa una configurazione di esempio")
    s.set_defaults(fai=c_portineria)

    s = sotto.add_parser("griglie", help="le domande gia' scritte per i lavori italiani")
    s.add_argument("nome", nargs="?", help="stampa quella griglia in JSON")
    s.set_defaults(fai=c_griglie)

    s = sotto.add_parser("decidi", help="una richiesta da file, senza server")
    comuni(s)
    s.add_argument("file", help="un .json con stato e domande, oppure (con --griglia) un file di testo o il testo stesso")
    s.add_argument("--griglia", default=None,
                   help="usa una griglia pronta: assistenza, spese, contratto, moderazione")
    s.add_argument("--astensione", action="store_true",
                   help="aggiunge l'opzione «lo stato non basta». ⚠️ Spenta di "
                        "default: sui casi misurati fa perdere 6 risposte giuste su 31")
    s.set_defaults(fai=c_decidi)

    s = sotto.add_parser("molti", help="tante righe in un colpo, col modello caricato una volta")
    comuni(s)
    s.add_argument("file", help="un .jsonl (una riga per caso) oppure un .txt (una riga per stato)")
    s.add_argument("--griglia", default=None, help="la griglia da usare per tutte le righe")
    s.add_argument("--uscita", default=None, help="dove scrivere (predefinito: a schermo)")
    s.add_argument("--tutto", action="store_true", help="scrivi anche probabilita' e misure")
    s.add_argument("--astensione", action="store_true",
                   help="aggiunge l'opzione «lo stato non basta». ⚠️ Spenta di "
                        "default: sui casi misurati fa perdere 6 risposte giuste su 31")
    s.set_defaults(fai=c_molti)

    s = sotto.add_parser("prova", help="sei decisioni di esempio, per vedere se gira")
    comuni(s)
    s.set_defaults(fai=c_prova)

    s = sotto.add_parser("taratura", help="cerca la temperatura sui tuoi dati etichettati")
    comuni(s)
    s.add_argument("dati", help="file .jsonl con stato, domanda, attesa")
    s.add_argument("--uscita", default="taratura.json")
    s.set_defaults(fai=c_taratura)

    args = p.parse_args(argv)
    if not getattr(args, "fai", None):
        p.print_help()
        return 0
    try:
        return args.fai(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError) as e:
        print(f"\n{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(principale())
