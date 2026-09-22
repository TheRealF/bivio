# I rapporti

Ogni file qui dentro e' l'uscita di `python prove/misura.py`, scritta tutta:
il riassunto, i numeri per famiglia di domanda, e **riga per riga** che cosa
e' stato chiesto, che cosa e' stato risposto e con che probabilita'.

Si rilancia cosi':

    ./.venv/bin/python prove/misura.py --modello 4b

I file che cominciano con `locale-` sono le prove che fai tu e non finiscono
nel repository (`.gitignore`). Quelli con la data davanti sono le misure
pubblicate nel README, e non si riscrivono: se ne aggiunge una nuova.

## 2026-09-22-m5-qwen3-4b-q4.json

MacBook con Apple M5, 24 GB, macOS, Metal. Qwen3-4B-Instruct-2507 Q4_K_M,
prompt v1, Bivio 0.1.0.

- 31 casi etichettati, astensione spenta: **30 giuste**, NLL 0,270
- gli stessi 31 con l'astensione accesa: 24 giuste, **6 ritirate di troppo**
- 6 casi a cui non si puo' rispondere: 5 riconosciuti
- contratto da 1.559 token, 8 domande insieme 3,2 s contro 18,4 s una per volta

⚠️ Sono 37 casi scritti da chi ha scritto anche il prompt, in italiano, su una
macchina sola. Dicono che gira e che risponde sensato. Non dicono che sia bravo
quanto Jev o quanto SemIf: per quello servirebbero le loro fixture e il loro
valutatore, e qui non e' stato fatto.

## 2026-09-22-m5-minerva-7b-q4.json

Stessa macchina, stessi 37 casi, stesso prompt: **Minerva-7B-instruct v1.0**
della Sapienza, Q4_K_M, cornice llama3 riconosciuta dal GGUF.

- 31 casi etichettati, astensione spenta: **13 giuste** (Qwen3-4B: 30)
- 6 casi a cui non si puo' rispondere: **0 riconosciuti** (Qwen3-4B: 5)
- 334 ms a decisione contro 188, e 4,5 GB di file contro 2,5

⚠️ **Il confronto e' onesto su una cosa sola: lo stesso prompt.** Quel prompt
l'ho scelto guardando come rispondeva Qwen, e Minerva-7B-instruct v1.0 e' un
modello del 2024 che non e' stato messo a punto per seguire una scelta multipla.
Con un prompt scritto per lui i numeri cambierebbero, e non so di quanto: se
qualcuno lo prova, apra una issue. Quello che il confronto mostra non e' che
l'italiano non serve; e' che per questo mestiere conta piu' quanto un modello
segue le istruzioni di quanto e' stato addestrato nella lingua giusta.
