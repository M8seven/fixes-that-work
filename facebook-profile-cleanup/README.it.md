# Pulizia Profilo Facebook: Eliminazione Automatica di Post, Foto e Attivita' tramite Script Console del Browser

*Autore: Valentino Paulon*
*Documento Tecnico — Privacy Social Media & Gestione Account*

---

## Sommario

Questo documento affronta il problema della cancellazione in blocco dei contenuti da un profilo Facebook personale — un'operazione che Facebook rende deliberatamente difficile tramite la sua interfaccia e non supporta tramite API per account personali.

Risultati principali:

- Le Graph API di Facebook **non permettono** la cancellazione di post personali. L'endpoint `DELETE /{post-id}` funziona solo per contenuti creati dalla stessa app richiedente, rendendo impossibile la pulizia programmatica tramite canali ufficiali.
- Tutti gli strumenti di terze parti esistenti (Redact.dev, Social Erase, ecc.) sono **servizi a pagamento** o **estensioni browser non mantenute** che si rompono ad ogni aggiornamento dell'interfaccia Facebook.
- La pagina "Gestisci Attivita'" di Facebook permette la selezione multipla ma fallisce su molti tipi di contenuto, richiede interazione manuale e non offre alcun percorso di automazione.
- La soluzione documentata qui usa **JavaScript nella console del browser** che interagisce direttamente con il DOM renderizzato di Facebook, automatizzando il ciclo click-attesa-conferma che un umano eseguirebbe manualmente.
- Vengono forniti due script: uno per i **post nel Registro Attivita'** e uno per le **foto del profilo**. Ciascuno gestisce le strutture di menu inconsistenti di Facebook (alcuni elementi mostrano "Delete", altri "Move to trash", altri solo "Add to profile"). L'approccio e' estensibile ad altri tipi di contenuto (commenti, reazioni, ecc.) adattando i selettori.

Tutti gli script girano nel browser, non richiedono installazione, nessuna chiave API, nessun accesso di terze parti, e funzionano sulla sessione autenticata dell'utente.

---

## 1. Definizione del Problema

### 1.1 Scenario

Un utente vuole pulire il proprio profilo Facebook — cancellare tutti i post, foto e attivita' — per motivi di privacy, per riutilizzare l'account per una pagina business, o semplicemente per ricominciare da zero.

### 1.2 Perche' E' Difficile

Facebook ha un interesse commerciale nel trattenere i contenuti degli utenti. La piattaforma fornisce:

- **Nessuna API di cancellazione in blocco** per account personali
- **Nessun pulsante "cancella tutto"** nell'interfaccia
- **Solo cancellazione manuale**: ogni post richiede 3-4 click (menu -> cancella -> conferma)
- **Opzioni di menu inconsistenti**: a seconda del tipo di contenuto, l'opzione di cancellazione puo' essere etichettata "Delete", "Move to trash", o potrebbe non esistere affatto (sostituita da "Add to profile" o "Hidden from profile")
- **Frammentazione per tipo di contenuto**: post, foto, video, commenti, reazioni, check-in e post nei gruppi sono tutti gestiti in sezioni UI separate

### 1.3 Perche' le Soluzioni Esistenti Falliscono

| Soluzione | Problema |
|-----------|----------|
| Facebook Graph API | Non puo' cancellare post personali — solo contenuti creati dall'app |
| Redact.dev | Versione gratuita limitata a 30 giorni; pulizia completa richiede abbonamento |
| Social Erase (estensione Chrome) | Richiede Facebook in inglese (US); si rompe con i cambiamenti UI |
| DeleteFB (Python/Selenium) | Non mantenuto dal 2021; incompatibile con il DOM attuale di Facebook |
| facebook-post-bulk-deleter (GitHub) | Richiede scoperta manuale dell'aria-label; singolo scopo (solo post) |
| Cancellazione manuale | Fattibile per 10-20 elementi; impraticabile per centinaia o migliaia |

---

## 2. Architettura della Soluzione

### 2.1 Approccio

Gli script operano automatizzando le stesse interazioni UI che un umano eseguirebbe:

1. **Localizzare** il pulsante azione per ogni elemento (identificato da `aria-label`)
2. **Cliccare** per aprire il menu contestuale
3. **Trovare** l'opzione cancella/cestina nel menu
4. **Cliccare** l'opzione di cancellazione
5. **Attendere** la finestra di conferma
6. **Confermare** la cancellazione
7. **Attendere** l'aggiornamento della pagina
8. **Ripetere** per l'elemento successivo, scrollando quando necessario

### 2.2 Sfide Tecniche Chiave

**Etichette di menu inconsistenti**: Facebook usa etichette diverse a seconda del tipo di contenuto e del suo stato di visibilita':

| Stato Contenuto | Opzione Menu | Dialog di Conferma |
|-----------------|-------------|-------------------|
| Post normale | "Delete" | "Delete?" -> "Delete" |
| Post nascosto | "Move to trash" | "Move to Trash?" -> "Move to Trash" |
| Aggiornamento profilo | Solo "Add to profile" | Cancellazione non disponibile |
| Foto | "Delete photo" | "Delete Photo" -> "Delete" |

**DOM dinamico**: Facebook usa nomi di classi CSS offuscati che cambiano ad ogni deployment. Gli script si basano su **attributi semantici** (`role`, `aria-label`) anziche' nomi di classi, rendendoli resistenti ai frequenti aggiornamenti UI di Facebook.

**Rate limiting**: Cliccare troppo velocemente causa il ritardo dell'interfaccia di Facebook. Ogni script include ritardi configurabili tra le azioni.

**Scroll infinito**: Il contenuto si carica dinamicamente mentre l'utente scrolla. Gli script devono scrollare periodicamente per caricare elementi aggiuntivi.

**Throttling dei tab in background**: Chrome (e altri browser basati su Chromium) rallenta aggressivamente i timer JavaScript nei tab in background — dopo 5 minuti di inattivita', i timer sono limitati a una volta al minuto. Questo causa il blocco degli script quando l'utente passa a un altro tab. Gli script includono un **meccanismo anti-throttle**: un oscillatore audio quasi silenzioso (`gain: 0.001`) che mantiene il tab classificato come "con audio", impedendo a Chrome di rallentarlo. Questo permette agli script di girare in autonomia mentre l'utente lavora in altri tab.

---

## 3. Prerequisiti

### 3.1 Supporto Browser

| Browser | Scorciatoia Console | Restrizione Incolla |
|---------|--------------------|--------------------|
| Chrome (macOS) | `Cmd + Option + J` | Scrivere `allow pasting` prima |
| Chrome (Windows/Linux) | `Ctrl + Shift + J` | Scrivere `allow pasting` prima |
| Firefox (macOS) | `Cmd + Option + K` | Nessuna |
| Firefox (Windows/Linux) | `Ctrl + Shift + K` | Nessuna |
| Safari (macOS) | `Cmd + Option + C` (abilitare prima il menu Sviluppo) | Nessuna |
| Edge (Windows) | `Ctrl + Shift + J` | Scrivere `allow pasting` prima |

### 3.2 Restrizione Incolla di Chrome

Chrome blocca l'incolla nella console con un avviso "Stop!" sugli attacchi self-XSS. Per aggirarlo:

1. Apri la Console
2. Scrivi `allow pasting` manualmente (a mano, non incollato) e premi Invio
3. Vedrai un `SyntaxError` — e' normale
4. Ora puoi incollare codice

**Alternativa (raccomandata)**: Usare gli **Snippets** invece della Console:

1. Apri DevTools -> tab **Sources** -> **Snippets** (pannello sinistro)
2. Clicca **+ New snippet**
3. Incolla lo script
4. Click destro sullo snippet -> **Run**

Gli Snippets aggirano completamente la restrizione sull'incolla e possono essere salvati per riuso.

### 3.3 Lingua di Facebook

Gli script gestiscono le etichette dei menu in **inglese** e **italiano**. Se il tuo Facebook e' in un'altra lingua, dovrai aggiungere le traduzioni corrispondenti negli array di corrispondenza testo degli script (vedi [Sezione 6: Personalizzazione](#6-personalizzazione)).

---

## 4. Script

### 4.1 Script 1: Cancellare i Post dal Registro Attivita'

**Pagina target**: Registro Attivita' -> La tua attivita' su Facebook -> Post -> I tuoi post, foto e video

**URL**: `https://www.facebook.com/allactivity` -> espandere "Your Facebook activity" -> "Posts"

**Cosa cancella**: Tutti i post visibili nel Registro Attivita' che hanno un'opzione "Delete" o "Move to trash".

**Cosa salta**: Elementi che hanno solo "Add to profile" (sono post di altre persone sulla tua timeline, gia' nascosti e non cancellabili dal Registro Attivita').

```javascript
(async function() {
  // Anti-throttle: impedisce a Chrome di mettere in pausa lo script nei tab in background
  var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  var oscillator = audioCtx.createOscillator();
  var gain = audioCtx.createGain();
  gain.gain.value = 0.001;
  oscillator.connect(gain);
  gain.connect(audioCtx.destination);
  oscillator.start();

  var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };
  var deleted = 0;
  var skip = 0;

  while(true) {
    var btns = document.querySelectorAll('div[aria-label="More options"]');
    if(skip >= btns.length) {
      window.scrollBy(0, 500);
      await sleep(4000);
      var newBtns = document.querySelectorAll('div[aria-label="More options"]');
      if(skip >= newBtns.length) { console.log("Finito! Eliminati: " + deleted); break; }
      btns = newBtns;
    }

    var btn = btns[skip];
    if(!btn) { console.log("Finito! Eliminati: " + deleted); break; }

    btn.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(1000);

    btn.click();
    await sleep(2000);

    var found = false;
    var menuItems = document.querySelectorAll('div[role="menuitem"], div[role="option"]');
    for(var i = 0; i < menuItems.length; i++) {
      var text = (menuItems[i].textContent || "").trim().toLowerCase();
      if(text === "delete" || text === "elimina" || text === "move to trash" || text === "sposta nel cestino") {
        menuItems[i].click();
        found = true;
        break;
      }
    }

    if(!found) {
      document.body.click();
      await sleep(500);
      skip++;
      console.log("Nessuna opzione delete, salto (" + skip + ")");
      continue;
    }

    await sleep(3000);

    var dialog = document.querySelector('div[role="dialog"]');
    if(dialog) {
      var dialogBtns = dialog.querySelectorAll('div[role="button"], button');
      for(var j = 0; j < dialogBtns.length; j++) {
        var btnText = (dialogBtns[j].textContent || "").trim().toLowerCase();
        if(btnText === "delete" || btnText === "elimina" || btnText === "move to trash" || btnText === "sposta nel cestino" || btnText === "confirm" || btnText === "conferma") {
          dialogBtns[j].click();
          break;
        }
      }
    }

    deleted++;
    console.log("Eliminato #" + deleted);
    await sleep(4000);
  }
})();
```

**Output atteso nella console**:
```
Nessuna opzione delete, salto (1)
Nessuna opzione delete, salto (2)
Eliminato #1
Eliminato #2
Eliminato #3
...
Finito! Eliminati: 47
```

### 4.2 Script 2: Cancellare le Foto

**Pagina target**: Il tuo profilo -> Foto -> tab **Le tue foto**

**URL**: `https://www.facebook.com/{tuo-username}/photos_by`

**Cosa cancella**: Tutte le foto nella sezione "Le tue foto". La cancellazione di ogni foto elimina anche il post associato.

**Importante**: Assicurati di essere sul tab **"Le tue foto" / "Your photos"**, non "Foto con te" / "Photos of You".

```javascript
(async function() {
  // Anti-throttle: impedisce a Chrome di mettere in pausa lo script nei tab in background
  var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  var oscillator = audioCtx.createOscillator();
  var gain = audioCtx.createGain();
  gain.gain.value = 0.001;
  oscillator.connect(gain);
  gain.connect(audioCtx.destination);
  oscillator.start();

  var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };
  var deleted = 0;
  var maxLoop = 500;

  for(var loop = 0; loop < maxLoop; loop++) {
    var pencils = document.querySelectorAll('div[aria-label="More options for this photo"]');

    if(pencils.length === 0) {
      window.scrollBy(0, 500);
      await sleep(4000);
      pencils = document.querySelectorAll('div[aria-label="More options for this photo"]');
      if(pencils.length === 0) { console.log("Finito! Foto eliminate: " + deleted); break; }
    }

    var pencil = pencils[0];
    if(!pencil) { console.log("Finito! Foto eliminate: " + deleted); break; }

    pencil.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(1500);

    pencil.click();
    await sleep(2500);

    var found = false;
    var menuItems = document.querySelectorAll('div[role="menuitem"]');
    for(var i = 0; i < menuItems.length; i++) {
      var text = (menuItems[i].textContent || "").trim().toLowerCase();
      if(text.includes("delete photo") || text.includes("elimina foto")) {
        menuItems[i].click();
        found = true;
        break;
      }
    }

    if(!found) {
      var closeBtn = document.querySelector('div[aria-label="Close"], div[aria-label="Chiudi"]');
      if(closeBtn) closeBtn.click();
      else document.body.click();
      await sleep(1000);
      console.log("Delete photo non trovato, salto...");
      continue;
    }

    await sleep(3000);

    var clicked = false;
    var allBtns = document.querySelectorAll('div[role="button"], button, span[role="button"], a[role="button"]');
    for(var j = allBtns.length - 1; j >= 0; j--) {
      var btnText = (allBtns[j].textContent || "").trim();
      if(btnText === "Delete" || btnText === "Elimina") {
        allBtns[j].click();
        clicked = true;
        break;
      }
    }

    if(!clicked) {
      var allElements = document.querySelectorAll('div[role="button"], button');
      for(var k = allElements.length - 1; k >= 0; k--) {
        var inner = (allElements[k].innerText || "").trim();
        if(inner === "Delete" || inner === "Elimina") {
          allElements[k].click();
          clicked = true;
          break;
        }
      }
    }

    if(clicked) {
      deleted++;
      console.log("Foto eliminata #" + deleted);
    } else {
      console.log("Conferma non trovata");
      var closeBtn = document.querySelector('div[aria-label="Close"], div[aria-label="Chiudi"]');
      if(closeBtn) closeBtn.click();
    }

    await sleep(5000);
  }

  console.log("Script terminato. Foto eliminate: " + deleted);
})();
```

### 4.3 Come Trovare gli aria-label (Quando gli Script Smettono di Funzionare)

Facebook puo' cambiare i valori degli `aria-label` in aggiornamenti futuri. Per scoprire le etichette attuali:

1. Naviga alla pagina target (Registro Attivita' o Foto)
2. Apri DevTools (vedi [Sezione 3.1](#31-supporto-browser))
3. Click destro sul pulsante target (tre puntini, icona matita, ecc.) -> **Ispeziona**
4. Nel pannello Elements, cerca `aria-label="..."` sull'elemento evidenziato o il suo genitore

In alternativa, esegui questo nella console per elencare tutti gli elementi con label:

```javascript
document.querySelectorAll('[aria-label]').forEach(function(el) {
  console.log("LABEL:", el.getAttribute('aria-label'), "| ROLE:", el.getAttribute('role'));
});
```

Aggiorna le stringhe `querySelectorAll('div[aria-label="..."]')` negli script con i nuovi valori.

---

## 5. Guida all'Esecuzione

### 5.1 Passo-Passo: Cancellare i Post

1. Vai a `https://www.facebook.com/allactivity`
2. Clicca **"Your Facebook activity"** (espandi la sezione)
3. Clicca **"Posts"** -> **"Your posts, photos and videos"**
4. Apri DevTools -> Sources -> Snippets -> New snippet
5. Incolla lo **Script 1** -> Click destro -> Run
6. Osserva la console per il progresso
7. Se lo script si ferma (la pagina non ha caricato in tempo), ricarica la pagina e riesegui — ripartira' dal contenuto rimanente

### 5.2 Passo-Passo: Cancellare le Foto

1. Vai sul tuo profilo -> **Foto** -> tab **"Le tue foto"**
2. Apri DevTools -> Sources -> Snippets -> New snippet
3. Incolla lo **Script 2** -> Click destro -> Run
4. Osserva la console per il progresso

### 5.3 Fermare uno Script

Per fermare uno script in esecuzione in qualsiasi momento:

- **Ricarica la pagina** (`Cmd+R` / `Ctrl+R` / `F5`) — questo termina immediatamente lo script

---

## 6. Personalizzazione

### 6.1 Regolare la Velocita'

Se lo script va troppo veloce per la tua connessione, aumenta i valori `sleep()` (in millisecondi):

```javascript
await sleep(4000);  // 4 secondi — aumentare a 6000 o 8000 per connessioni lente
```

Se lo script e' troppo lento, diminuiscili — ma non scendere sotto `1000` o l'interfaccia di Facebook non stara' al passo.

### 6.2 Aggiungere Lingue

Gli script corrispondono al testo dei menu in inglese e italiano. Per aggiungere un'altra lingua, trova le sezioni di corrispondenza testo e aggiungi le tue traduzioni:

```javascript
// Esempio: aggiungere francese e tedesco
if(text === "delete" || text === "elimina" || text === "supprimer" || text === "loschen" ||
   text === "move to trash" || text === "sposta nel cestino" || text === "mettre a la corbeille") {
```

### 6.3 Gestire Nuove Opzioni di Menu

Se Facebook aggiunge nuove strutture di menu, l'approccio diagnostico e' sempre lo stesso:

1. Clicca il pulsante azione manualmente
2. Ispeziona gli elementi del menu che appaiono
3. Annota il testo esatto e l'attributo `role` dell'elemento
4. Aggiorna i selettori e la corrispondenza testo dello script di conseguenza

---

## 7. Limitazioni

- **Gli elementi "Add to profile" non possono essere cancellati** dal Registro Attivita'. Sono post di altre persone sulla tua timeline gia' nascosti. Possono essere gestiti solo dal lato del poster originale.
- **Foto profilo e copertina** possono richiedere gestione separata attraverso la sezione Album.
- **Facebook puo' limitare** le cancellazioni rapide. Se lo script inizia a fallire dopo molte cancellazioni riuscite, attendi 10-15 minuti e riavvia.
- **La struttura DOM cambia** con gli aggiornamenti di Facebook. Gli script si basano sugli attributi `aria-label` che sono piu' stabili dei nomi delle classi CSS, ma possono comunque cambiare. Vedi [Sezione 4.3](#43-come-trovare-gli-aria-label-quando-gli-script-smettono-di-funzionare) per come adattarsi.
- **Il contenuto nel Cestino** viene automaticamente eliminato dopo 30 giorni. Per cancellare immediatamente, vai in Registro Attivita' -> Cestino -> seleziona tutto -> Elimina permanentemente.

---

## 8. Confronto con le Alternative

| Caratteristica | Questa Soluzione | Redact.dev | Social Erase | Manuale |
|---------------|:---------------:|:----------:|:------------:|:-------:|
| Costo | Gratuito | 8+$/mese | Gratuito (limitato) | Gratuito |
| Cancellazione post | Si | Si | Si | Si |
| Cancellazione foto | Si | Si | Parziale | Si |
| Nessuna installazione | Si | No (app) | No (estensione) | Si |
| Gestisce "Move to trash" | Si | Si | No | Si |
| Personalizzabile | Si (sorgente) | No | No | N/A |
| Sopravvive aggiornamenti FB | Adattabile | Dipende dal vendor | Spesso si rompe | Sempre |
| Velocita' (100 elementi) | ~8 minuti | ~5 minuti | ~10 minuti | ~2 ore |

---

## Licenza

MIT

## Disclaimer

Questo strumento automatizza azioni che un utente puo' eseguire manualmente attraverso l'interfaccia standard di Facebook. Non aggira alcun meccanismo di autenticazione, controllo accesso o sicurezza. Non accede ai dati di altri utenti. Opera interamente all'interno della sessione browser autenticata dell'utente sul proprio account.

Tutti i test sono stati condotti sull'account Facebook dell'autore. Non e' stato effettuato alcun accesso non autorizzato a sistemi di terze parti.
