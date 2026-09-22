"""Quali modelli conosce Bivio, e come se li scarica.

Sono modelli di altri, pinnati a un file preciso: non si aggiornano da soli.
Un modello che cambia sotto i piedi cambia le probabilita' di un processo che
gira in produzione, e nessuno se ne accorge.
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass

CARTELLA = os.environ.get(
    "BIVIO_MODELLI",
    os.path.join(os.path.expanduser("~"), ".bivio", "modelli"),
)


@dataclass
class Scheda:
    chiave: str
    file: str
    url: str
    byte: int
    licenza: str
    nota: str


CATALOGO: dict[str, Scheda] = {
    "4b": Scheda(
        chiave="4b",
        file="Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        url=(
            "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/"
            "resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
        ),
        byte=2497281120,
        licenza="Apache-2.0",
        nota="Il modello di partenza. 2,5 GB, sta in memoria su qualunque macchina recente.",
    ),
    "1.7b": Scheda(
        chiave="1.7b",
        file="Qwen3-1.7B-Q8_0.gguf",
        url="https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q8_0.gguf",
        byte=1834426016,
        licenza="Apache-2.0",
        nota="Circa il doppio piu' veloce e visibilmente meno preciso. Va provato sui propri dati.",
    ),
}

PREDEFINITO = "4b"


def percorso(chiave: str = PREDEFINITO) -> str:
    """Dove sta (o dove andra') il file di quel modello."""
    if os.path.sep in chiave or chiave.endswith(".gguf"):
        return os.path.abspath(os.path.expanduser(chiave))
    if chiave not in CATALOGO:
        raise KeyError(
            f"modello «{chiave}» sconosciuto: " + ", ".join(CATALOGO) +
            " (oppure il percorso di un file .gguf tuo)"
        )
    return os.path.join(CARTELLA, CATALOGO[chiave].file)


def presente(chiave: str = PREDEFINITO) -> bool:
    p = percorso(chiave)
    if not os.path.exists(p):
        return False
    if chiave in CATALOGO:
        return os.path.getsize(p) == CATALOGO[chiave].byte
    return True


def scarica(chiave: str = PREDEFINITO, forza: bool = False, mostra=print) -> str:
    """Scarica il file, riprendendo da dove si era interrotto."""
    if chiave not in CATALOGO:
        raise KeyError(f"modello «{chiave}» sconosciuto")
    scheda = CATALOGO[chiave]
    destinazione = percorso(chiave)
    os.makedirs(os.path.dirname(destinazione), exist_ok=True)

    if presente(chiave) and not forza:
        mostra(f"{scheda.file} c'e' gia' ({_giga(scheda.byte)}).")
        return destinazione

    parziale = destinazione + ".parziale"
    da = os.path.getsize(parziale) if os.path.exists(parziale) else 0
    if da >= scheda.byte:
        da = 0

    richiesta = urllib.request.Request(scheda.url, headers={"User-Agent": "bivio"})
    if da:
        richiesta.add_header("Range", f"bytes={da}-")
        mostra(f"Riprendo da {_giga(da)} di {_giga(scheda.byte)}.")
    else:
        mostra(f"Scarico {scheda.file} ({_giga(scheda.byte)}) da huggingface.co.")

    with urllib.request.urlopen(richiesta) as risposta, open(parziale, "ab" if da else "wb") as f:
        fatti = da
        ultimo = -1
        while True:
            pezzo = risposta.read(1 << 20)
            if not pezzo:
                break
            f.write(pezzo)
            fatti += len(pezzo)
            percento = int(fatti * 100 / scheda.byte)
            if percento != ultimo and sys.stderr.isatty():
                sys.stderr.write(f"\r  {percento}%  {_giga(fatti)}")
                sys.stderr.flush()
                ultimo = percento
    if sys.stderr.isatty():
        sys.stderr.write("\n")

    vera = os.path.getsize(parziale)
    if vera != scheda.byte:
        raise RuntimeError(
            f"il file scaricato fa {vera} byte invece di {scheda.byte}: riprova"
        )
    shutil.move(parziale, destinazione)
    mostra(f"Fatto: {destinazione}")
    return destinazione


def _giga(n: int) -> str:
    return f"{n / (1 << 30):.2f} GB"
