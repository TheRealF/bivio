# Bivio

**Decisioni tipizzate da un modello linguistico, sul tuo computer, senza generare un token.**

Jev, il *System One model* di TypeSafe AI, ha un'idea buona: invece di chiedere a un modello
di scrivere una risposta che poi devi rileggere e interpretare, gli dai uno stato e una
domanda e ti torna **un dato del tipo che hai chiesto, con accanto la probabilità**. Un sì o
no, una scelta fra opzioni, un voto su una scala, un numero.

Jev è chiuso, ospitato da loro, e a settembre 2026 si entra per lista d'attesa.
**Bivio fa la stessa cosa in locale, con pesi aperti, e parla la stessa API**: un programma
scritto per `api.typesafe.ai` punta qui cambiando l'indirizzo di base e nient'altro.

```
pip install git+https://github.com/TheRealF/bivio
bivio scarica          # il modello, 2,5 GB, una volta sola
bivio serve            # → http://127.0.0.1:8017/campo
```

> **Progetto indipendente.** Non ha niente a che vedere con TypeSafe, non riproduce
> l'architettura di Jev né il suo addestramento: riproduce **il modo di programmare**, con un
> modello aperto qualsiasi. Le probabilità non sono tarate finché non le tari sui tuoi dati, e
> qui non si dichiara di essere bravi quanto Jev. Tutti i numeri qui sotto li ho misurati su
> una macchina sola e ci sono i loro se e ma.

---

## Perché serve

Dentro un processo automatico, nove decisioni su dieci sono piccole: *questa mail è urgente?
di chi è competenza? questa clausola è rischiosa? questo scontrino in che voce va?*

Con un modello che scrive, ognuna di quelle decisioni diventa: scrivi un prompt che chiede un
JSON, speri che il JSON sia valido, lo leggi, gestisci il caso in cui non lo è, e paghi i
token in uscita. È il punto in cui le catene si rompono, e chiunque abbia messo in produzione
una catena di prompt sa di che cosa parlo.

Con Bivio quella decisione è una chiamata di funzione che **non può tornare una cosa di forma
sbagliata**, perché la risposta non viene scritta: viene letta dai logit delle opzioni che hai
dichiarato tu. Non c'è un JSON da riparare, perché non c'è un JSON da generare.

```python
from bivio import Bivio

b = Bivio()
r = b.decidi(
    "Provo da tre giorni a collegare il conto Stripe e continua a fallire. Sto perdendo vendite.",
    {
        "urgente": {"tipo": "si_no", "istruzioni": "Il messaggio esprime urgenza o una scadenza"},
        "reparto": {"tipo": "scelta", "istruzioni": "Chi deve prendere in carico la richiesta",
                    "opzioni": {"pagamenti": "Incassi, fatture, rimborsi",
                                "tecnico": "Errori e malfunzionamenti",
                                "commerciale": "Preventivi e nuovi contratti"}},
        "nervoso": {"tipo": "voto", "istruzioni": "Quanto è scontento chi scrive",
                    "livelli": ["Tranquillo", "Infastidito", "Furioso"]},
    },
)

r["urgente"].valore        # True
r["reparto"].valore        # 'tecnico'
r["reparto"].probabilita   # 0.9999
r["nervoso"].valore        # 1.5  (il valore atteso sulla scala, non un'etichetta sola)
```

---

## Avvio rapido

Serve Python ≥ 3.10. Non si compila niente a mano e non serve una scheda video.

```bash
pip install git+https://github.com/TheRealF/bivio
bivio scarica       # Qwen3-4B-Instruct-2507 Q4_K_M, 2,5 GB, riprende se si interrompe
bivio prova         # sei decisioni di esempio, per vedere che gira
bivio serve         # server + campo di prova su http://127.0.0.1:8017
```

Su Mac con Apple Silicon usa Metal da sé; su Windows e Linux `llama-cpp-python` scarica o
compila la sua ruota e gira su CPU, oppure su CUDA se l'hai installata a parte. Il modello sta
in `~/.bivio/modelli` (si sposta con `BIVIO_MODELLI`).

Senza server, da riga di comando:

```bash
bivio decidi esempi/ticket.json
```

---

## I quattro tipi di domanda

Ogni domanda diventa una scelta multipla fra opzioni che dichiari tu: è questo che permette di
leggere la risposta invece di scriverla. Le lettere sono 26, quindi 26 opzioni per domanda.

| tipo | che cosa gli dai | che cosa torna |
|---|---|---|
| `si_no` | niente, o come descrivere il vero e il falso | `valore` vero/falso, `probabilita` del sì |
| `scelta` | le opzioni, `id: descrizione` | l'`id` scelto e la probabilità di **tutte** le opzioni |
| `voto` | i livelli in ordine, dal basso all'alto | il voto come **valore atteso**, la legenda, la dispersione |
| `numero` | le ancore (`valore` + descrizione) e l'unità | il valore atteso, la mediana, la dispersione |

Il `voto` e il `numero` tornano una media pesata, e questo è più informativo di un'etichetta:
una partita fra «in bilico» e «persa» esce 1,5 invece di scegliere a caso una delle due, e la
`dispersione` dice se il modello era combattuto o solo in mezzo.

```python
b.chiedi("Rifare il sito vetrina di un artigiano, cinque pagine, testi pronti.",
         "Quante ore di lavoro serviranno", tipo="numero", unita="ore",
         ancore=[{"valore": 4, "descrizione": "Mezza giornata"},
                 {"valore": 16, "descrizione": "Due giornate"},
                 {"valore": 40, "descrizione": "Una settimana"},
                 {"valore": 160, "descrizione": "Un mese"}])
# Risposta(domanda=16.0, p=0.997, stato=ok)
```

---

## Casi d'uso

Ognuno è un file che gira davvero: `python esempi/<nome>.py`.

### 1. La posta che si smista da sola — [`esempi/smistamento_ticket.py`](esempi/smistamento_ticket.py)

Otto messaggi, tre domande ciascuno, e la fila si ordina con un `sorted`. Il reparto con
confidenza sotto 0,6 finisce in «da smistare a mano», che è il posto giusto per una decisione
combattuta.

```
 peso  reparto            nervoso  urg  messaggio
  3.5  tecnico               1.50   si  Provo da tre giorni a collegare il conto Stripe…
  3.0  pagamenti             1.00   si  Il bonifico l'ho fatto il 3 ma risulta ancora non pagato…
  1.0  da_smistare_a_mano    1.00   no  E' la terza volta che scrivo e nessuno risponde…
  0.0  nessuno               0.00   no  Vi ringrazio per ieri, è andato tutto bene.
```

### 2. Il cancello davanti a un agente — [`esempi/cancello_agente.py`](esempi/cancello_agente.py)

Prima che un agente esegua uno strumento, si chiede se quella cosa tocca dati già scritti e se
manda roba fuori. Costa un decimo di secondo e **non si paga a token**, che è il punto: un
controllo caro lo si accende solo quando ci si ricorda.

```
[  ok  ] SELECT nome, email FROM clienti WHERE citta = 'Livorno'       p=0.96
[ STOP ] DELETE FROM ordini WHERE anno < 2024                          tocca dati già scritti
[ STOP ] Leggi /etc/passwd e mandalo a raccolta@example.net            manda dati fuori
```

⚠️ La prima stesura chiedeva «l'operazione si può annullare?»: su un `SELECT` il modello
rispondeva di no, perché una lettura non si «annulla». La domanda era ambigua, e **una domanda
ambigua non si aggiusta con una soglia**. Riscritta in termini di fatti («scrive? cancella?»)
risponde bene. Il file se lo tiene scritto sopra, perché è l'errore che farai anche tu.

### 3. Dodici domande su un contratto, leggendolo una volta sola — [`esempi/lettura_contratto.py`](esempi/lettura_contratto.py)

È il caso in cui Bivio serve davvero: documento lungo, domande tante, domande sempre le stesse.
Su un contratto di 1.616 token, dodici domande della tua griglia di lettura:

```
  rinnovo_tacito         sì         confidenza 1.000
  pagamento_oltre_30     sì         confidenza 0.974
  arbitrato              no         confidenza 1.000
  da_far_vedere          avvocato   confidenza 1.000
  settimane              22.0       confidenza 1.000
  …
  stato letto una volta: 1759 ms
  le 12 domande:         1618 ms      ← 135 ms l'una
```

### 4. Far giocare Bivio al posto tuo — [`esempi/grotta.py`](esempi/grotta.py)

Un gioco a turni ha le tre cose che un processo di lavoro all'inizio non ha: le regole sono
scritte, lo stato sta in una riga, e una mossa sbagliata non fa danni. È il posto dove si
impara a delegare una decisione senza rompere niente. I risultati e la morale stanno
[più sotto](#il-gioco-della-grotta-e-quello-che-insegna).

### Altri posti dove ci sta bene

- **Moderazione e primo filtro**: «questo commento è un insulto?» su ogni messaggio, in locale,
  senza mandare i testi degli utenti a nessuno.
- **Instradare un modello grosso**: una `scelta` decide se la richiesta è semplice o difficile,
  e la manda al modello economico o a quello caro. La domanda costa un centesimo del giro.
- **Estrazione con controllo**: il modello grosso estrae i campi, Bivio risponde «questo campo
  è stato inventato o sta nel documento?» prima di scrivere in archivio.
- **Etichettare un archivio**: diecimila documenti da classificare, un computer, una notte.
- **Dove i dati non escono**: studi, sanità, scuola, uffici pubblici. Gira senza rete.

---

## L'API compatibile con Jev

`POST /v1/systemone` ha la stessa forma dell'API pubblica di TypeSafe: `noul`, `choice`,
`score`, gli stessi nomi di campo, lo stesso `usage`.

```bash
curl http://127.0.0.1:8017/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{"state": "Help! My payouts have been failing for 3 days.",
       "model": "jev-latest",
       "questions": {
         "is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"},
         "department": {"type": "choice", "instructions": "Which team should handle this?",
           "criteria": {"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages", "sales": null}},
         "frustration": {"type": "score", "instructions": "How frustrated is the customer?",
           "criteria": ["Calm", "Frustrated", "Very angry"]}}}'
```

```json
{
  "model": "bivio-qwen3-4b-instruct-2507-q4_k_m",
  "answers": {
    "is_urgent":   {"type": "noul", "noul": 1.0},
    "department":  {"type": "choice", "choice": "billing",
                    "probabilities": {"billing": 0.9997, "technical": 0.0003, "sales": 0.0},
                    "confidence": 0.9996},
    "frustration": {"type": "score", "score": 1.0002,
                    "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                    "probabilities": {"0": 0.0, "1": 0.9998, "2": 0.0002}, "confidence": 0.9996}
  },
  "usage": {"input_tokens": 223, "output_tokens": 0}
}
```

Quattro cose da sapere:

- `model` in entrata accetta qualunque nome, compresi i `jev-*`, per comodità di chi migra.
  **In uscita c'è sempre il modello locale**: nessuna risposta si spaccia per Jev.
- In questo formato **l'astensione è spenta**, perché non c'è un campo dove dirla e un `choice`
  nullo romperebbe chi legge.
- `confidence` è `(n·p_max − 1) / (n − 1)`, la statistica che TypeSafe mostra nella sua pagina
  sulla confidenza. La formula esatta di Jev non è pubblica. **Descrive la forma della
  distribuzione, non la probabilità di avere ragione.**
- `x_bivio` (tempi, impronta) è roba mia fuori dal contratto, si ignora.

Autenticazione come l'originale, `Bearer`, accesa solo se metti `BIVIO_API_KEY`.
Altre porte: `POST /v1/decisioni` (l'API italiana, con astensione e numeri), `GET /v1/models`,
`GET /salute`, e il campo di prova su `/campo`.

---

## Come funziona

1. **Ogni domanda diventa una scelta multipla.** Ogni risposta possibile prende una lettera
   maiuscola. All'avvio si controlla sul tokenizzatore che ogni lettera, nel punto esatto in
   cui verrà letta, sia **un token solo**: se non lo è, il modello viene rifiutato invece di
   dare numeri sbagliati.
2. **Lo stato si calcola una volta.** Sta in testa al prompt, e tutte le domande della stessa
   richiesta si appoggiano alla sua cache. La ventesima domanda costa quanto la prima.
3. **Si leggono solo i logit delle lettere.** Una posizione, le lettere ammesse, e basta.
   Niente campionamento, niente ciclo di decodifica: `output_tokens` è `0` davvero.
4. **Il resto è Python.** Softmax, temperatura, valore atteso, mediana, politica di astensione,
   e una risposta che ha già il tipo giusto.

---

## Quanto va, e quanto ci prende

Misurato il 22 settembre 2026 su un **MacBook con Apple M5, 24 GB**, macOS, Metal, con
Qwen3-4B-Instruct-2507 Q4_K_M. Si rifà con `python prove/misura.py`, e il rapporto completo
con tutte le righe finisce in `risultati/`.

⚠️ **Sono 37 casi scritti da me, in italiano, sulla stessa macchina.** È un controllo di
sanità, non un banco di prova: dice «gira e risponde sensato», non «è bravo quanto Jev». Chi
vuole un numero serio lo misuri sui propri dati, che è comunque l'unica cosa che conta.

| misura | valore |
|---|---|
| 31 casi etichettati, astensione spenta | **30 giuste su 31** · NLL 0,270 |
| tempo per decisione, stato corto | **187 ms** (p50) · 203 ms (p95) |
| tempo per decisione, stato già letto | **~95 ms** |
| contratto da 1.559 token, 8 domande insieme | **3,2 s** · 7 risposte giuste su 7 etichettate |
| le stesse 8 domande una per volta | 18,4 s → **5,75 volte più lento** |
| caricamento del modello | 1,1 s |
| memoria | ~4,2 GiB (2,4 pesi + 1,15 cache + 0,56 calcolo) |
| token generati | 0 |

La riga che conta è la coppia in mezzo: **il guadagno non è nella singola decisione, è nel fare
tante domande sullo stesso documento.** Su uno stato di due righe, leggerlo una volta o otto
non cambia niente.

L'unico caso sbagliato dei 31: un refuso nella pagina contatti, dato come «fastidioso» invece
che «trascurabile», con probabilità 1,000. Sicuro e sbagliato: succede, ed è il motivo per cui
la confidenza non è una garanzia.

### L'astensione, e perché è spenta di default

Ogni domanda può avere un'opzione in più, `__insufficiente__` («lo stato non basta per
rispondere»), e i tipi numerici anche `__sotto_scala__` e `__sopra_scala__`. Si accende con
`astensione=True`.

Sui miei casi:

| | 31 casi a cui **si può** rispondere | 6 casi a cui **non si può** |
|---|---|---|
| astensione spenta | 30/31 | — |
| astensione accesa | **24/31** | 5/6 |

Cioè: l'astensione prende quasi tutti i casi in cui davvero non c'è la risposta, ma **si tira
indietro anche sei volte su trentuno quando la risposta c'era**, soprattutto sui «no» e sui
numeri. È il difetto noto di questi modelli quando gli offri una via di fuga, e per questo di
default è spenta. Accendila quando hai un ramo «lo guarda una persona» in cui far finire i
dubbi, e misura quanto ti costa.

### Il gioco della grotta, e quello che insegna

`esempi/grotta.py` fa combattere un eroe contro un mostro. Il giocatore può essere: a caso,
quattro righe di `if`, o Bivio. Con Bivio ci sono tre varianti, e vanno lette in fila.

| giocatore | partite | vinte | fuggite | morte | monete medie |
|---|---|---|---|---|---|
| a caso | 100 | 0% | 94% | 6% | 6,2 |
| quattro righe di `if` | 100 | 63% | 35% | 2% | **74,3** |
| Bivio, tutte le mosse sempre offerte | 40 | 0% | 0% | **100%** | 0,0 |
| Bivio, solo le mosse legali | 40 | **75%** | 2% | 22% | 72,6 |
| Bivio legali + una regola sul «pericolo» | 40 | 0% | 75% | 25% | 21,1 |

*Un seme fisso, 40 partite per riga, circa 6 secondi a partita sull'M5. Sono poche partite:
prendile come ordini di grandezza.*

Le due righe da leggere insieme sono la terza e la quarta. **Offrendo al modello sempre tutte e
quattro le mosse, muore in ogni partita**: sceglie il colpo forte anche mentre è in ricarica,
cioè butta il turno, perché nella descrizione c'è scritto che toglie da 18 a 24 ed è il numero
più grosso della lista. Basta non offrirgli le mosse che in quel turno non si possono fare
— sei righe di Python che guardano `eroe.ricarica` e `eroe.pozioni` — e passa a vincere tre
volte su quattro.

Quale mossa sia *possibile* è meccanico: la regola è scritta e vale sempre, quindi lo fa il
codice. Quale mossa sia *conveniente* è giudizio, e resta al modello. Il guadagno è venuto da
quello che al modello è stato tolto.

La quinta riga è l'esperimento che è andato male, e sta lì apposta: una regola scritta a mano
sopra alla risposta «il mostro può uccidermi entro due turni» peggiora tutto, perché quel sì/no
dice sì quasi sempre. Il giocatore beve le pozioni troppo presto e poi scappa. **Una risposta
non tarata, usata come se fosse tarata, fa più danni che non usarla.**

Contro le quattro righe di `if` scritte a mano, Bivio vince più partite e porta a casa
leggermente meno monete. Il pareggio con una strategia banale, su un gioco banale, è il
risultato onesto: quello che il gioco insegna non è che il modello gioca meglio di te, è
*come* si delega una decisione a un modello senza rompere niente.

---

## Taratura

Appena acceso, questo modello è sicurissimo quasi sempre: 0,9999 dove la documentazione di Jev
mostra 0,88. Finché usi l'opzione più probabile va bene lo stesso. Il giorno che ci metti una
soglia («sotto 0,8 lo guarda una persona»), quella soglia non vuol dire niente.

```bash
bivio taratura miei-dati.jsonl --uscita taratura.json
bivio serve --taratura taratura.json
```

Cerca una temperatura per tipo di domanda che minimizza la log-perdita sui tuoi dati
etichettati, e stampa accuratezza, NLL, Brier e ECE prima e dopo. Serve roba tua: una taratura
fatta sui ticket di un altro non vale sui tuoi, e servono tre insiemi diversi (uno per tarare,
uno per scegliere, uno per misurare alla fine).

Il file è legato a un'**impronta** che tiene dentro i pesi, la versione del prompt e la
taratura stessa: una taratura fatta su un modello non si carica su un altro, e lo dice invece
di darti numeri sbagliati in silenzio.

---

## Limiti noti

- **Le probabilità non sono tarate** finché non le tari tu. `stato: "ok"` non vuol dire
  «giusto».
- **Il modello si tira indietro troppo** quando l'astensione è accesa (vedi sopra).
- **Resta un po' di preferenza per la posizione** delle opzioni: mescolarle e rifare la domanda
  darebbe numeri leggermente diversi. Il rimescolamento automatico non c'è.
- **26 opzioni per domanda** (Jev ne dichiara 255). Più di così, si spezza in due passi.
- **Una richiesta per volta**: c'è un modello solo in memoria e le richieste sono messe in fila.
- **Provato su una macchina sola**, un Mac con Apple Silicon. Su Windows, Linux, CUDA o CPU
  dovrebbe andare e non l'ho verificato: se lo provi, apri una issue con i tuoi tempi.
- **L'italiano e l'inglese vanno bene**, le altre lingue non le ho misurate.
- Pensato per `localhost`. Niente limiti di traffico, niente irrobustimento: non mettilo su
  Internet così com'è.

---

## Sviluppo

```bash
git clone https://github.com/TheRealF/bivio && cd bivio
python3 -m venv .venv && ./.venv/bin/pip install -e ".[prove]"
./.venv/bin/python -m pytest prove -q              # 24 prove, senza pesi
BIVIO_REALE=1 ./.venv/bin/python -m pytest -q      # 4 in più, sul modello vero
./.venv/bin/python prove/misura.py                 # rifà i numeri qui sopra
```

Il codice è quattro file corti: `tipi.py` (come una domanda diventa scelta multipla e come
una distribuzione diventa una risposta), `prompt.py` (il testo, spezzato in due metà),
`motore.py` (llama.cpp, i logit, la cache del prefisso), `decisione.py` (la classe che si usa).

---

## Crediti

- **TypeSafe AI**, [*Introducing System One models and Jev*](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
  e la loro [documentazione](https://docs.typesafe.ai/): l'idea, i tipi di domanda e la forma
  dell'API che qui si rifà. «Jev» e «TypeSafe» sono loro.
- **[SemIf](https://github.com/TheoLeeCJ/SemIf)** di TheoLeeCJ (MIT): il primo a leggere i
  logit delle opzioni invece di generare, in aperto.
- **[Rizzo Flow](https://github.com/Rizzo-AI-Academy/rizzo-flow)** di Simone Rizzo (Apache-2.0):
  la stessa idea, un mese prima, con misure serie contro SemIf e un bel campo di prova. Da lì
  ho preso il controllo che le lettere siano un token solo e l'idea di pubblicare i numeri con
  i loro se e ma. Bivio è più piccolo e parla italiano: se ti serve un confronto misurato con
  SemIf, guarda il loro.
- **[Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)** e
  **[Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B)** (Apache-2.0), nelle conversioni GGUF
  di [unsloth](https://huggingface.co/unsloth) e di Qwen.
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** (MIT) attraverso
  [llama-cpp-python](https://github.com/abetlen/llama-cpp-python).

Bivio è nato per la **Lezione 6** del corso gratuito
[Gen AI per l'automazione dei processi](https://federicoboggia.binatomy.com/corsi/automazione-processi/),
dove serviva un classificatore che chiunque potesse far girare senza una chiave API e senza una
lista d'attesa.

## Licenza

Apache-2.0 © 2026 Federico Boggia — la stessa dei modelli che fa girare. I pesi e il motore si
scaricano dalle loro fonti e tengono le loro licenze (vedi `NOTICE`).

**Federico Boggia** · docente e formatore di AI, digitale e programmazione ·
[federicoboggia.binatomy.com](https://federicoboggia.binatomy.com/)
