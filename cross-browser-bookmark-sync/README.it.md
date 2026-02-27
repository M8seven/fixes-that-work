# Sincronizzazione Cross-Browser di Segnalibri e Password su macOS: Merge Bidirezionale tra Safari e Chrome tramite Manipolazione Diretta dei File

*Autore: Valentino Paulon*
*Documento Tecnico — Interoperabilita' Dati Browser su macOS*

---

## Sommario

Questo documento affronta l'assenza di un meccanismo nativo di sincronizzazione bidirezionale di segnalibri e password tra Safari e Google Chrome su macOS. L'analisi dimostra che:

- Apple e Google mantengono **sistemi di archiviazione completamente isolati** per segnalibri e credenziali, senza alcuna capacita' di sync cross-browser. L'estensione iCloud Bookmarks di Apple per Chrome funziona solo su Windows, non su macOS.
- Le soluzioni di terze parti (xBrowserSync, BookMacster, Bookmark UniSync) **non supportano Safari**, richiedono intervento manuale, o introducono compromessi inaccettabili sulla privacy instradando i dati attraverso server esterni.
- Safari archivia i segnalibri in un **Property List binario** (`~/Library/Safari/Bookmarks.plist`) con struttura ad albero annidato, mentre Chrome usa un **file JSON piatto** (`~/Library/Application Support/Google/Chrome/Default/Bookmarks`). Questi formati sono strutturalmente incompatibili ma entrambi deterministicamente parsabili.
- Gli archivi password sono ancora piu' isolati: le credenziali Safari risiedono nel **Keychain di sistema macOS** (cifrato, protetto da biometria), mentre Chrome cifra le password in un **database SQLite** usando una chiave nel Keychain sotto "Chrome Safe Storage". Nessuno dei due puo' essere letto programmaticamente senza autenticazione dell'utente.
- Un workflow di sincronizzazione completo e' realizzabile attraverso una combinazione di **manipolazione diretta dei file** (segnalibri) e **import/export via CSV** (password), con logica di deduplicazione che gestisce la normalizzazione degli URL tra varianti `http/https`, `www/non-www` e parametri query.

Questo documento fornisce una soluzione testata e automatizzata per macOS che non richiede software di terze parti, estensioni browser, ne' server esterni.

---

## 1. Definizione del Problema

### 1.1 Contesto Operativo

Un utente mantiene sessioni attive su Safari e Chrome su macOS. Segnalibri e password salvate si accumulano indipendentemente in ciascun browser, causando:

- **Frammentazione dei dati** — credenziali salvate in Chrome non disponibili in Safari e viceversa
- **Overhead di gestione duplicati** — lo stesso segnalibro deve essere creato manualmente in entrambi
- **Desincronizzazione password** — aggiornamenti password in un browser non si propagano all'altro
- **Accumulo di peso morto** — segnalibri legacy (siti defunti, strumenti obsoleti) persistono per anni senza pulizia

### 1.2 Perche' Non Esiste una Soluzione Nativa

| Vendor | Ambito sync | Supporto cross-browser |
|--------|------------|----------------------|
| Apple (iCloud) | Safari ↔ Safari tra dispositivi Apple | Nessuno su macOS. L'estensione Chrome iCloud Bookmarks e' solo per Windows |
| Google (Chrome Sync) | Chrome ↔ Chrome su tutte le piattaforme | Nessuno. Chrome Sync e' proprietario e legato all'account Google |
| Estensioni terze parti | Varia | La maggior parte supporta Chrome + Firefox. Il supporto Safari e' raro per le restrizioni Apple sulle estensioni |

La causa radice e' economica: ne' Apple ne' Google hanno incentivo a facilitare la sync cross-browser. Il lock-in del browser e' un vantaggio strategico per entrambi gli ecosistemi.

---

## 2. Analisi dell'Architettura di Storage

### 2.1 Segnalibri Safari — Property List

**Posizione:** `~/Library/Safari/Bookmarks.plist`

Safari archivia i segnalibri in un Property List binario con la seguente struttura ad albero:

```
Root (WebBookmarkTypeList)
├── Cronologia (WebBookmarkTypeProxy)
├── BookmarksBar (WebBookmarkTypeList)
│   ├── Cartella A (WebBookmarkTypeList)
│   │   ├── Segnalibro 1 (WebBookmarkTypeLeaf)
│   │   └── Segnalibro 2 (WebBookmarkTypeLeaf)
│   └── Cartella B (WebBookmarkTypeList)
│       └── ...
├── BookmarksMenu (WebBookmarkTypeList)
│   └── ...
└── com.apple.ReadingList (WebBookmarkTypeProxy)
    └── ...
```

**Vincoli di accesso:**
- Safari deve essere **chiuso** prima di modificare il plist. Se Safari e' in esecuzione, mantiene un lock sul file e sovrascrivera' le modifiche esterne al prossimo ciclo di scrittura.
- Il file e' in formato plist binario, parsabile tramite il modulo Python `plistlib`.

### 2.2 Segnalibri Chrome — JSON

**Posizione:** `~/Library/Application Support/Google/Chrome/Default/Bookmarks`

**Vincoli di accesso:**
- Chrome deve essere **chiuso** prima di modificare il file.
- Se Chrome Sync e' attivo, i dati cloud possono sovrascrivere le modifiche locali. La sync deve essere temporaneamente disattivata, i dati cloud cancellati, poi riattivata dopo le modifiche.

### 2.3 Password — Archivi Cifrati

| Browser | Storage | Cifratura | Accesso programmatico |
|---------|---------|-----------|----------------------|
| Safari | macOS Keychain | AES-256, protetto da biometria | CLI `security` richiede autorizzazione per ogni voce |
| Chrome | SQLite (`Login Data`) + chiave Keychain | AES-128-CBC | Richiede accesso Keychain + decifratura SQLite |

**Conclusione:** La manipolazione programmatica diretta delle password non e' praticabile senza autenticazione ripetuta. L'unico percorso pratico e' l'export/import via CSV attraverso l'interfaccia di ciascun browser.

---

## 3. Metodologia di Sincronizzazione

### 3.1 Sync Segnalibri — Automatizzata

Il processo opera in tre fasi:

```
Fase 1: LETTURA
  Safari plist + Chrome JSON → Parse cartelle e segnalibri

Fase 2: DIFF
  Confronto per URL esatto all'interno di ogni cartella
  → Mancanti in Safari / Mancanti in Chrome

Fase 3: SCRITTURA
  Aggiunta segnalibri mancanti al file di ciascun browser
```

### 3.2 Merge Password — Semi-Automatizzato

```
1. Export password Safari  →  CSV (Impostazioni di Sistema > Password > File > Esporta)
2. Export password Chrome  →  CSV (chrome://password-manager/settings > Scarica file)
3. Merge CSV programmatico:
   a. Deduplicazione per (dominio, username)
   b. Per duplicati stessa password: mantieni variante https://
   c. Per password diverse: segnala per revisione manuale
   d. Identifica voci esclusive di un browser
4. Import CSV unificato in entrambi i browser via UI
5. Cancellazione immediata dei file CSV in chiaro
```

### 3.3 Logica di Deduplicazione

Safari crea comunemente voci duplicate per la stessa credenziale su varianti URL:

| Variante | Esempio |
|----------|---------|
| Protocollo | `http://` vs `https://` |
| Prefisso WWW | `www.example.com` vs `example.com` |
| Path finale | `https://example.com/` vs `https://example.com` |
| Parametri query | `?utm_source=...` aggiunto |

L'algoritmo normalizza estraendo il dominio (rimuovendo `www.`) e raggruppando per `(dominio, username)`. All'interno di ogni gruppo:
- Se tutte le password sono identiche → mantieni una voce (preferisci `https://`, preferisci senza `www.`)
- Se le password differiscono → mantieni tutte le voci (segnala per revisione manuale)

---

## 4. Implementazione

### 4.1 Prerequisiti

- macOS (testato su macOS Sequoia 15.x)
- Python 3.9+ (incluso con Xcode Command Line Tools)
- Safari e Chrome installati
- Nessuna dipendenza esterna richiesta

### 4.2 Script

| File | Scopo |
|------|-------|
| `sync_bookmarks.py` | Sync bidirezionale segnalibri |
| `merge_passwords.py` | Merge e deduplicazione password via CSV |

Uso:
```bash
# Sync segnalibri (chiudi entrambi i browser prima)
python3 sync_bookmarks.py

# Merge password
python3 merge_passwords.py <safari_export.csv> <chrome_export.csv>
```

---

## 5. Interazione con Chrome Sync

Se Chrome Sync e' attivo, i segnalibri nel cloud Google sovrascrivono le modifiche locali. Il reset richiede:

1. **Disattiva Chrome Sync** — `chrome://settings/syncSetup` → Disattiva (senza spuntare "Rimuovi dati da questo dispositivo")
2. **Cancella dati cloud** — `https://chrome.google.com/sync` → "Cancella dati"
3. **Modifica segnalibri locali** — Con sync disattivata e cloud vuoto, le modifiche locali sono sicure
4. **Riattiva Chrome Sync** — Lo stato locale pulito viene caricato sul cloud come nuova copia canonica

---

## 6. Risultati

### 6.1 Sync Segnalibri

**Prima:**
| Browser | Segnalibri | Cartelle | Link morti |
|---------|-----------|----------|-----------|
| Safari | 42 | 3 | ~5 |
| Chrome | 77 | 12 | ~50 |

**Dopo:**
| Browser | Segnalibri | Cartelle | Link morti |
|---------|-----------|----------|-----------|
| Safari | 39 | 8 (categorizzate) | 0 |
| Chrome | 39 | 8 (identiche) | 0 |

### 6.2 Merge Password

**Prima:**
| Browser | Password | Duplicati interni |
|---------|----------|------------------|
| Safari | 355 | 23 gruppi |
| Chrome | 22 | 0 |

**Dopo:**
| Browser | Password | Sovrapposizione |
|---------|----------|----------------|
| Safari | 343 | 100% |
| Chrome | 339 | 98.8% |

---

## 7. Confronto con Soluzioni Esistenti

| Soluzione | Supporto Safari | Bidirezionale | Privacy | Costo | Automazione |
|-----------|----------------|--------------|---------|-------|------------|
| iCloud Bookmarks (est. Chrome) | macOS: No | N/A | Server Apple | Gratis | N/A |
| xBrowserSync | No | N/A | Self-hosted | Gratis | N/A |
| BookMacster | Si | Si | Locale | $29 | Manuale |
| EverSync | No | N/A | Server esterni | Gratis/Pagamento | Auto |
| **Questa soluzione** | **Si** | **Si** | **Completamente locale** | **Gratis** | **Script** |

Vantaggio chiave: nessun server esterno, nessuna estensione browser, nessun abbonamento, nessun compromesso sulla privacy. I dati non lasciano mai la macchina locale.

---

## Licenza

MIT

## Disclaimer

Questo documento descrive la manipolazione di file dati browser locali su hardware di proprieta' dell'autore. Non e' stato effettuato alcun accesso non autorizzato a sistemi Apple, Google o di terze parti. La gestione delle password segue le best practice di sicurezza: i file CSV in chiaro vengono creati solo temporaneamente e cancellati immediatamente dopo l'import.
