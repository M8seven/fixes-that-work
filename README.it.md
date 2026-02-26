# fixes-that-work

Soluzioni reali a problemi reali. Testate, documentate, e funzionanti — non i soliti "hai provato a riavviare?".

Ogni paper documenta un problema dove le soluzioni mainstream falliscono, fornisce un'analisi delle cause tramite test live, e offre un fix funzionante con script di automazione.

---

## Paper

| # | Paper | Problema | Stato |
|---|-------|----------|-------|
| 1 | [Captive Portal Bypass](captive-portal-bypass/) | Bypass autenticazione captive portal basata su MAC tramite debolezza nel binding dell'identita' | Pubblicato |
| 2 | [eSIM Tethering Bypass](esim-tethering-bypass/) | Hotspot iPhone con eSIM bloccato dal carrier via DPI/TTL/QUIC — fix a 5 livelli per macOS | Pubblicato |

---

## Cos'e'

Una raccolta di paper tecnici nati da problemi che non avevano soluzioni funzionanti online. Ogni paper segue una struttura coerente:

- **Problema** — definito chiaramente, riproducibile
- **Analisi delle cause** — non supposizioni, diagnosi reale con evidenze a livello di pacchetto
- **Soluzione** — fix testato con automazione dove possibile
- **Confronto** — perche' le soluzioni esistenti non funzionano

## Cosa NON e'

- Non e' un toolkit di hacking
- Non e' ricerca teorica
- Non e' una raccolta di risposte non testate da Stack Overflow

## Lingue

Ogni paper e' disponibile in inglese e italiano.

- `README.md` — English
- `README.it.md` — Italiano

## Licenza

MIT

## Disclaimer

Tutta la ricerca e' stata condotta su apparecchiature di proprieta' dell'autore a scopo educativo e di analisi architetturale. Non e' stato effettuato alcun accesso non autorizzato a sistemi di terze parti.
