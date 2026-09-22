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


def c_decidi(args):
    with open(args.file, encoding="utf-8") as f:
        corpo = json.load(f)
    stato = corpo.get("stato", corpo.get("state"))
    domande = corpo.get("domande", corpo.get("questions"))
    if stato is None or not domande:
        print("Il file vuole «stato» e «domande».", file=sys.stderr)
        return 2
    b = _cervello(args)
    fuori = b.grezzo(stato, domande, astensione=not args.senza_astensione)
    print(json.dumps(fuori, ensure_ascii=False, indent=2))
    return 0


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

    s = sotto.add_parser("decidi", help="una richiesta da file, senza server")
    comuni(s)
    s.add_argument("file")
    s.add_argument("--senza-astensione", action="store_true")
    s.set_defaults(fai=c_decidi)

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
