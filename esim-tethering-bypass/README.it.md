# eSIM Tethering Bypass su macOS

**Analisi tecnica del blocco tethering carrier e metodologie di ripristino della connettività**

---

## Indice

1. [Contesto e motivazione](#1-contesto-e-motivazione)
2. [Architettura della connessione tethering](#2-architettura-della-connessione-tethering)
3. [Livello 1 — Rilevamento TTL](#3-livello-1--rilevamento-ttl)
4. [Livello 2 — Fallimento MTU e PMTU Discovery](#4-livello-2--fallimento-mtu-e-pmtu-discovery)
5. [Livello 3 — Routing IPv6 non funzionante](#5-livello-3--routing-ipv6-non-funzionante)
6. [Livello 4 — Interferenza DNS](#6-livello-4--interferenza-dns)
7. [Livello 5 — Blocco UDP porta 443 (QUIC/HTTP3)](#7-livello-5--blocco-udp-porta-443-quichttp3)
8. [Rilevamento automatico del carrier](#8-rilevamento-automatico-del-carrier)
9. [Soluzione: script automatizzato](#9-soluzione-script-automatizzato)
10. [Codice sorgente: tethering-fix.sh](#10-codice-sorgente-tethering-fixsh)
11. [LaunchDaemon plist](#11-launchdaemon-plist)
12. [Risultati dei test](#12-risultati-dei-test)
13. [Riferimenti tecnici](#13-riferimenti-tecnici)
14. [Disclaimer](#14-disclaimer)

---

## 1. Contesto e motivazione

Le eSIM da viaggio e le SIM di carrier MVNO (Mobile Virtual Network Operator) rappresentano
una soluzione comune per la connettività dati all'estero. Molti di questi carrier, tuttavia,
implementano restrizioni esplicite sul tethering (Personal Hotspot), anche quando il piano
dati non lo vieta formalmente o quando il contratto non menziona tale limitazione.

Il risultato pratico per l'utente e' il seguente: il MacBook risulta connesso all'hotspot
Wi-Fi dell'iPhone, ottiene un indirizzo IP valido, ma non carica alcuna pagina web. Il
terminale mostra connettivita' parziale (alcune richieste `curl` funzionano), mentre il
browser fallisce completamente.

Questo documento descrive la diagnosi completa e i fix applicati, tutti scoperti tramite
test live su hardware reale (MacBook con macOS, iPhone con eSIM carrier MVNO da viaggio).
Non si tratta di speculazione teorica: ogni livello di blocco e' stato identificato
empiricamente e la soluzione e' stata verificata.

---

## 2. Architettura della connessione tethering

Quando un Mac si connette a Internet tramite l'hotspot di un iPhone, il flusso di rete
attraversa i seguenti strati:

```
+------------------+       Wi-Fi        +------------------+       LTE/5G        +------------------+
|                  |  (172.20.10.0/24)  |                  |    (rete carrier)   |                  |
|   MacBook        |<------------------>|   iPhone         |<------------------->|   Core Network   |
|   (client)       |                    |   (NAT + forward)|                    |   Carrier MVNO   |
|                  |                    |                  |                    |                  |
+------------------+                    +------------------+                    +------------------+
       |                                        |
       |  IP locale: 172.20.10.2/24             |  IP pubblico: assegnato dal carrier
       |  Gateway:   172.20.10.1                |  (spesso CGNAT, 10.x.x.x o 100.x.x.x)
       |  DNS:       172.20.10.1                |
```

L'iPhone funge da router NAT. Il traffico proveniente dal Mac viene incapsulato e
inoltrato verso la rete mobile del carrier. E' in questo punto di inoltro che il carrier
applica le politiche di blocco tethering.

Il carrier ha accesso a tutti i metadati dei pacchetti IP che transitano: TTL, dimensioni,
protocollo di trasporto, porta di destinazione. Non ha accesso al contenuto cifrato (TLS),
ma non ne ha bisogno: le informazioni di livello 3 e 4 sono sufficienti per identificare
traffico tethering con alta affidabilita'.

---

## 3. Livello 1 — Rilevamento TTL

### Meccanismo di detection

Il Time To Live (TTL) e' un campo a 8 bit nell'header IPv4 (hop limit in IPv6). Ogni
router che inoltra un pacchetto decrementa questo valore di 1. Se raggiunge 0, il pacchetto
viene scartato e viene inviato un messaggio ICMP "Time Exceeded" al mittente.

I sistemi operativi usano TTL iniziali standardizzati:

| OS            | TTL iniziale |
|---------------|-------------|
| Linux         | 64          |
| macOS         | 64          |
| Windows       | 128         |
| iOS           | 64          |
| Android       | 64          |

Quando un iPhone riceve traffico dal Mac via hotspot e lo inoltra verso la rete mobile, il
TTL viene decrementato di 1 dall'operazione di forwarding. Il carrier riceve quindi
pacchetti con TTL=63 (64-1) anziche' TTL=64.

```
  Mac genera pacchetto TTL=64
          |
          v
  iPhone riceve, decrementa TTL: 64 -> 63
          |
          v
  Carrier riceve pacchetto TTL=63
          |
          +--> TTL < 64 ? --> SI --> TETHERING RILEVATO --> blocca
          |
          +--> TTL = 64 ? --> Traffico diretto iPhone --> lascia passare
```

Il carrier sfrutta la semplice osservazione che il traffico generato direttamente
dall'iPhone ha sempre TTL=64 quando raggiunge la torre cellulare (o comunque un TTL
piu' alto), mentre il traffico tethering — avendo subito un hop aggiuntivo — ha TTL
inferiore.

### Diagnosi

```bash
# Verifica il TTL corrente del sistema
sysctl net.inet.ip.ttl

# Invia un ping con TTL visibile
ping -t 1 8.8.8.8   # dovrebbe fallire con ICMP Time Exceeded
ping 8.8.8.8        # TTL default del sistema
```

Se `curl https://ipinfo.io/org` fallisce con timeout mentre si e' connessi all'hotspot,
ma funziona dopo aver modificato il TTL, la detection TTL e' confermata.

### Fix

Impostare il TTL iniziale del Mac a 65. Dopo il decremento dell'iPhone, il carrier ricevera'
TTL=64, identico al traffico diretto.

```bash
sudo sysctl -w net.inet.ip.ttl=65
```

Verifica:

```bash
sysctl net.inet.ip.ttl
# output atteso: net.inet.ip.ttl: 65
```

Questa modifica e' temporanea e si azzera al riavvio del sistema.

---

## 4. Livello 2 — Fallimento MTU e PMTU Discovery

### Meccanismo di detection

Il Maximum Transmission Unit (MTU) definisce la dimensione massima di un pacchetto che
puo' essere trasmesso su un link senza frammentazione. Il valore standard per Ethernet
e Wi-Fi e' 1500 byte. Il link LTE/5G ha spesso MTU inferiore (tipicamente 1420-1460 byte
dopo incapsulamento).

Il Path MTU Discovery (PMTUD) e' il meccanismo (RFC 1191) con cui un host determina il
MTU minimo lungo tutto il percorso verso la destinazione. Funziona come segue:

1. Il mittente invia pacchetti con il bit "Don't Fragment" (DF) impostato
2. Se un router intermedio riceve un pacchetto troppo grande, invia ICMP tipo 3, codice 4
   ("Fragmentation Required") con il MTU del link successivo
3. Il mittente riduce la dimensione dei pacchetti di conseguenza

```
  Mac (MTU=1500)
        |
        | invia pacchetto 1500 byte, DF=1
        v
  iPhone (hotspot interface, MTU variabile)
        |
        | link LTE ha MTU=1460
        | pacchetto 1500 > 1460, DF=1 --> deve frammentare ma non puo'
        | DOVREBBE inviare ICMP "Fragmentation Required" al Mac
        |
        +--> alcuni carrier/implementazioni BLOCCANO o NON INOLTRANO
             i messaggi ICMP di ritorno verso il client tethering
        |
        v
  Mac non riceve mai l'ICMP --> non riduce il pacchetto
  --> i pacchetti grandi vengono silenziosamente scartati
```

Il risultato e' asimmetrico: le richieste HTTP GET (pochi byte) funzionano perfettamente.
Le risposte HTTP con corpo grande (pagine web con JavaScript, immagini, JSON pesanti)
vengono frammentate e i frammenti vengono scartati silenziosamente.

### Sintomi caratteristici

- `curl https://example.com` restituisce il body correttamente
- `curl https://google.com` restituisce l'HTML (piccolo)
- Il browser non carica Google (la pagina effettiva con JS e' molto piu' grande)
- Le API REST con risposte piccole funzionano; quelle con risposte grandi falliscono
- `ping -s 1400 8.8.8.8` fallisce; `ping -s 100 8.8.8.8` funziona

### Diagnosi

```bash
# Test con pacchetti di dimensioni diverse
ping -s 100 8.8.8.8    # deve funzionare
ping -s 800 8.8.8.8    # potrebbe iniziare a fallire
ping -s 1400 8.8.8.8   # quasi certamente fallisce se c'e' PMTUD blackhole

# Verifica MTU corrente
networksetup -getMTU en0
```

### Fix

Abbassare il MTU dell'interfaccia Wi-Fi del Mac al valore minimo garantito per IPv4/IPv6:
1280 byte (il minimo obbligatorio per IPv6 secondo RFC 2460, ampiamente supportato anche
da tutti i link IPv4 moderni).

```bash
sudo networksetup -setMTU en0 1280
```

Con MTU=1280, tutti i pacchetti generati dal Mac sono sufficientemente piccoli da passare
senza frammentazione attraverso qualsiasi link intermedio, eliminando la dipendenza dal
PMTUD.

Verifica:

```bash
networksetup -getMTU en0
# output atteso: Active MTU: 1280    (Requested MTU: 1280)

ping -s 1400 8.8.8.8
# ora funziona: pacchetto 1400 viene frammentato a livello Mac prima dell'invio
```

---

## 5. Livello 3 — Routing IPv6 non funzionante

### Meccanismo di detection

I carrier MVNO da viaggio spesso forniscono connettivita' IPv4 alla SIM ma non instradano
correttamente IPv6 sulle connessioni tethering. Questo e' distinto dalla semplice mancanza
di IPv6: il Mac potrebbe ricevere un indirizzo IPv6 link-local o persino un prefisso
globale via SLAAC, ma il traffico IPv6 viene scartato silenziosamente nella rete del
carrier.

Il comportamento Happy Eyeballs (RFC 6555) dei browser moderni tenta sempre prima una
connessione IPv6 verso i server che lo supportano (praticamente tutto il web moderno:
Google, Meta, Cloudflare, ecc.). Se IPv6 non funziona ma l'interfaccia ha un indirizzo
IPv6 configurato, il sistema non lo sa immediatamente: deve attendere il timeout della
connessione IPv6 (tipicamente 250-300ms) prima di fare fallback su IPv4.

```
  Browser tenta di caricare https://google.com

  Fase 1 — DNS (funziona):
    dig AAAA google.com --> risponde con 2001:4860:4860::8888 (IPv6)
    dig A    google.com --> risponde con 142.250.x.x (IPv4)

  Fase 2 — Connessione Happy Eyeballs:
    Tenta IPv6 prima: TCP SYN a 2001:4860:4860::8888:443
        |
        +--> pacchetto IPv6 esce dal Mac
        +--> iPhone lo inoltra
        +--> carrier MVNO scarta il pacchetto (routing IPv6 non configurato)
        +--> timeout dopo ~300ms
        |
    Fallback su IPv4: TCP SYN a 142.250.x.x:443
        |
        +--> se il fix TTL e' applicato, questo funziona
        +--> ma il ritardo di 300ms per ogni connessione rende il browser lentissimo
```

Nei casi peggiori, il carrier risponde con ICMP "No Route to Host" per l'IPv6, e il
browser interpreta questo come errore di rete permanente invece di fare fallback su IPv4.

### Diagnosi

```bash
# Test IPv6
ping6 google.com 2>&1
# se risponde "ping6: UDP connect: No route to host" --> IPv6 non funziona

ping6 -c 3 2001:4860:4860::8888 2>&1
# identico test con IP diretto (esclude problemi DNS)

# Test IPv4 (deve funzionare dopo fix TTL)
ping -c 3 8.8.8.8

# Verifica indirizzi configurati sull'interfaccia
ifconfig en0 | grep -E "inet6?"
```

### Fix

Disabilitare IPv6 sull'interfaccia Wi-Fi per forzare tutte le connessioni su IPv4, dove
il routing funziona correttamente.

```bash
sudo networksetup -setv6off "Wi-Fi"
```

Ripristino (quando si torna su rete normale):

```bash
sudo networksetup -setv6automatic "Wi-Fi"
```

Questa operazione non richiede riavvio e ha effetto immediato.

---

## 6. Livello 4 — Interferenza DNS

### Problema

I tool di networking VPN e mesh (es. client VPN, Tailscale, ZeroTier, ecc.) iniettano
spesso server DNS personalizzati nella configurazione di sistema. Questi DNS sono
raggiungibili normalmente tramite la VPN stessa, ma non sono accessibili quando la VPN
e' inattiva o quando la connettivita' di base e' limitata (come durante la fase iniziale
di un hotspot con blocchi carrier).

Esempio tipico: Tailscale imposta `100.100.100.100` come server DNS primario. Questo
indirizzo e' nel range 100.64.0.0/10 (CGNAT), raggiungibile solo attraverso la
interfaccia virtuale Tailscale. Se Tailscale e' attivo ma la sua connettivita' e'
degradata, o se il DNS di Tailscale non funziona sull'hotspot, tutte le risoluzioni DNS
falliscono silenziosamente.

```
  Mac cerca di risolvere "google.com"
        |
        v
  DNS primario: 100.100.100.100 (Tailscale)
        |
        +--> richiesta inviata via interfaccia utun (Tailscale)
        +--> Tailscale non ha connettivita' (o e' in stato degradato)
        +--> timeout dopo 5 secondi
        |
  Fallback su DNS secondario: 172.20.10.1 (gateway hotspot)
        |
        +--> il gateway hotspot potrebbe filtrare o rispondere lentamente
        +--> ulteriore delay o fallimento
        |
  Risultato: la risoluzione DNS impiega 5-10 secondi o fallisce
  Sintomo per l'utente: browser mostra "Risoluzione host..." per lunghi periodi
```

### Diagnosi

```bash
# Verifica DNS configurati
networksetup -getdnsservers "Wi-Fi"
# oppure
scutil --dns | grep nameserver

# Test di risoluzione con DNS specifici
dig @100.100.100.100 google.com +time=3
dig @1.1.1.1 google.com +time=3
dig @172.20.10.1 google.com +time=3

# Misura il tempo di risoluzione
time nslookup google.com
```

### Fix

Impostare DNS pubblici affidabili e svuotare la cache DNS di sistema.

```bash
# Imposta DNS manuali
sudo networksetup -setdnsservers "Wi-Fi" 1.1.1.1 8.8.8.8

# Svuota cache DNS
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

# Se Tailscale e' installato, spegnerlo per evitare conflitti di routing
tailscale down
```

---

## 7. Livello 5 — Blocco UDP porta 443 (QUIC/HTTP3)

### Il blocco piu' sottile e meno ovvio

Questo e' il livello di blocco piu' difficile da diagnosticare perche' produce un pattern
di fallimento apparentemente casuale: alcuni browser funzionano (parzialmente), altri
non funzionano affatto, e le applicazioni native del sistema operativo (su macOS: Meteo,
Mappe, App Store) falliscono completamente anche dopo che tutti gli altri fix sono stati
applicati.

### HTTP/3 e QUIC

HTTP/3 e' la versione piu' recente del protocollo HTTP, standardizzata in RFC 9114 (2022).
A differenza di HTTP/1.1 e HTTP/2 che girano su TCP, HTTP/3 gira su QUIC (RFC 9000):
un protocollo di trasporto multiplexato e cifrato che opera su UDP.

```
  Stack protocollare:

  HTTP/1.1, HTTP/2:          HTTP/3:
  +------------------+       +------------------+
  |   HTTP           |       |   HTTP/3         |
  +------------------+       +------------------+
  |   TLS 1.3        |       |   QUIC           |
  +------------------+       +------------------+
  |   TCP            |       |   UDP            |
  +------------------+       +------------------+
  |   IP             |       |   IP             |
  +------------------+       +------------------+

  QUIC usa UDP porta 443 (per convenzione,
  anche se la porta e' negoziabile via Alt-Svc)
```

### Comportamento per browser/applicazione

| Client             | Comportamento con UDP 443 bloccato          |
|--------------------|---------------------------------------------|
| curl               | Usa TCP di default, non tenta QUIC → funziona sempre |
| Chrome / Chromium  | Tenta QUIC, fallback aggressivo su TCP HTTP/2 → funziona lentamente |
| Firefox            | Tenta QUIC, fallback su TCP → funziona (con ritardo iniziale) |
| Safari             | Tenta QUIC aggressivamente, fallback TCP piu' lento → funziona malissimo |
| App native Apple   | Usano NSURLSession con HTTP/3 abilitato di default → falliscono quasi sempre |

La differenza tra Chrome e Safari e' significativa: Chrome implementa il meccanismo di
"QUIC broken" con un blacklist persistente per host; se QUIC fallisce ripetutamente su
un host, Chrome lo disabilita per quel host per un certo periodo. Safari e il framework
URLSession di Apple sono piu' aggressivi nell'usare QUIC e il fallback e' meno robusto.

### Diagnosi

```bash
# Verifica se UDP 443 e' bloccato
# Se tutti questi falliscono ma TCP 443 funziona, UDP e' bloccato

# Test TCP 443
nc -zv google.com 443          # deve funzionare

# Test UDP 443 (QUIC handshake)
# Non c'e' uno strumento semplice come nc per QUIC, ma si puo' usare curl con --http3
curl --http3 https://google.com 2>&1 | head -5
# se risponde "curl: (7) ... UDP" o simile --> UDP bloccato

# In alternativa, in Wireshark/tcpdump:
sudo tcpdump -i en0 -n "udp port 443" &
curl --http3 https://cloudflare.com
# se non si vedono risposte UDP --> bloccato

# Verifica che Safari non carichi nonostante browser TCP funzioni:
# - curl https://apple.com funziona
# - Safari non carica apple.com
# --> quasi certamente QUIC bloccato
```

### Fix

Bloccare UDP porta 443 in uscita a livello di firewall `pf` di macOS. Questo forza tutte
le applicazioni — incluse quelle che preferiscono QUIC — a usare TCP per HTTPS.

```bash
echo "block out proto udp from any to any port 443" | sudo pfctl -f -
sudo pfctl -e
```

Verifica:

```bash
# pfctl deve mostrare la regola
sudo pfctl -s rules
# output atteso:
# block drop out proto udp from any to any port = 443

# Verifica che pfctl sia attivo
sudo pfctl -s info | head -5
# output atteso: Status: Enabled
```

Ripristino:

```bash
sudo pfctl -d   # disattiva pfctl (rimuove tutte le regole)
```

### Perche' questo e' l'ultimo pezzo del puzzle

Prima di questo fix, il pattern diagnostico era:

```
Tentativo        | Risultato
-----------------|-----------------------------------------
curl             | OK (sempre funzionato, usa TCP)
Chrome           | OK (lentamente, fallback QUIC->TCP funziona)
Firefox          | OK (lentamente, simile a Chrome)
Safari           | NO (fallback QUIC->TCP lentissimo o fallisce)
App Meteo        | NO (usa URLSession con HTTP/3, nessun fallback robusto)
App Mappe        | NO (idem)
App Store        | NO (idem)
```

Dopo il blocco UDP 443:

```
Tentativo        | Risultato
-----------------|-----------------------------------------
curl             | OK (invariato)
Chrome           | OK (stessa velocita', nessuna differenza visibile)
Firefox          | OK (stessa velocita')
Safari           | OK (ora usa HTTP/2 su TCP direttamente)
App Meteo        | OK (funziona immediatamente)
App Mappe        | OK (funziona immediatamente)
App Store        | OK (funziona immediatamente)
```

---

## 8. Rilevamento automatico del carrier

Per applicare i fix solo quando necessario (e non su reti normali dove sarebbero
controproducenti), e' utile rilevare automaticamente se si e' connessi a un carrier
MVNO che blocca il tethering.

### Metodo: ASN lookup via ipinfo.io

Ogni carrier ha uno o piu' Autonomous System Number (ASN) assegnati dall'IANA. I carrier
MVNO da viaggio instradano tipicamente il traffico degli utenti attraverso ASN riconoscibili,
spesso quello del partner di rete o della loro sede operativa.

```bash
# Recupera l'organizzazione associata all'IP pubblico corrente
curl -4 -s --max-time 5 https://ipinfo.io/org
# esempio output: "AS12345 NOME-CARRIER-MVNO"

# Recupera informazioni complete in JSON
curl -4 -s --max-time 5 https://ipinfo.io/json
# output:
# {
#   "ip": "x.x.x.x",
#   "hostname": "...",
#   "city": "...",
#   "region": "...",
#   "country": "...",
#   "org": "AS12345 NOME-CARRIER",
#   "timezone": "..."
# }
```

Nota importante: per fare questa richiesta curl mentre si e' su hotspot con blocco
carrier, e' necessario prima applicare il fix TTL (livello 1). Il blocco TTL si applica
anche a curl. Quindi la sequenza corretta per il rilevamento automatico e':

1. Applicare TTL=65 temporaneamente
2. Fare la richiesta a ipinfo.io
3. Se il carrier e' riconosciuto come MVNO che blocca: applicare tutti i fix rimanenti
4. Se il carrier e' normale: ripristinare TTL=64 e non fare nulla

### Rilevamento del gateway hotspot

L'hotspot Personal Hotspot di iOS usa sempre il gateway `172.20.10.1` (subnet
`172.20.10.0/24`). Questo e' hard-coded in iOS e non cambia indipendentemente dal
carrier o dalla configurazione. E' quindi un identificatore affidabile per rilevare
che si e' connessi all'hotspot di un iPhone.

```bash
route -n get default 2>/dev/null | awk '/gateway:/{print $2}'
# se output == "172.20.10.1" --> connesso ad hotspot iPhone
```

---

## 9. Soluzione: script automatizzato

### Architettura

```
  /Library/LaunchDaemons/it.esim-fix.plist
          |
          | monitora cambi di rete via
          | com.apple.SystemConfiguration
          v
  /usr/local/bin/tethering-fix auto
          |
          +-- is_on_hotspot() ------------> gateway == 172.20.10.1 ?
          |         |
          |     NO  +--> fix era attivo? --> SI --> deactivate()
          |                                NO  --> exit
          |
          +-- detect_carrier() ----------> TTL=65 temporaneo
          |         |                     curl ipinfo.io/org
          |         |                     analizza ASN/org
          |         |
          |    carrier MVNO bloccante? --> SI --> activate()
          |                               NO --> TTL=64, exit
          |
          v
  activate():
    1. Tailscale down (se installato)
    2. sysctl net.inet.ip.ttl=65
    3. networksetup -setMTU en0 1280
    4. networksetup -setv6off "Wi-Fi"
    5. networksetup -setdnsservers "Wi-Fi" 1.1.1.1 8.8.8.8
    6. dscacheutil -flushcache + killall -HUP mDNSResponder
    7. pfctl block udp 443 + pfctl -e
    8. touch ~/.tethering-fix-active

  deactivate():
    1. sysctl net.inet.ip.ttl=64
    2. networksetup -setMTU en0 1500
    3. networksetup -setv6automatic "Wi-Fi"
    4. networksetup -setdnsservers "Wi-Fi" empty
    5. dscacheutil -flushcache + killall -HUP mDNSResponder
    6. pfctl -d
    7. Tailscale up (se installato)
    8. rm ~/.tethering-fix-active
```

### Trigger LaunchDaemon

macOS espone la directory `/Library/Preferences/SystemConfiguration` come punto di
notifica per i cambi di configurazione di rete. `launchd` puo' monitorare questa
directory e lanciare uno script a ogni modifica (cambio rete, aggiunta interfaccia,
cambio SSID, ecc.).

Questo e' preferibile a un cron job perche' reagisce agli eventi invece di fare
polling, e viene eseguito con privilegi di root senza richiedere interazione utente.

---

## 10. Codice sorgente: tethering-fix.sh

```bash
#!/bin/bash
# tethering-fix — Configura macOS per navigare via hotspot iPhone con eSIM carrier MVNO
#
# I carrier MVNO da viaggio bloccano il tethering tramite DPI + TTL inspection
# + blocco selettivo UDP (QUIC) + assenza routing IPv6.
# Questo script rileva automaticamente il carrier e applica i fix necessari.
#
# Uso:
#   sudo tethering-fix auto     -- rileva carrier e attiva/disattiva automaticamente
#   sudo tethering-fix on       -- forza attivazione fix
#   sudo tethering-fix off      -- ripristina tutto
#   tethering-fix status        -- mostra stato corrente
#
# Fix applicati (modalita' ON):
#   - TTL=65 (carrier vede 64 dopo decremento iPhone, sembra traffico diretto)
#   - MTU=1280 (evita drop silenzioso pacchetti grandi, fix PMTUD blackhole)
#   - IPv6 OFF (hotspot MVNO spesso non instrada IPv6, causa timeout nei browser)
#   - DNS manuali 1.1.1.1 / 8.8.8.8 (evita DNS hotspot lento/filtrato)
#   - Blocco UDP porta 443 (forza app Apple e Safari a usare HTTP/2 su TCP)
#   - Tailscale DOWN se installato (il suo DNS e routing interferiscono)
#
# Tutte le modifiche sono temporanee e si resettano al riavvio del sistema.

set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# ─── CONFIGURAZIONE ──────────────────────────────────────────
WIFI_INTERFACE="en0"
WIFI_SERVICE="Wi-Fi"
STATE_DIR="/var/run"
STATE_FILE="$STATE_DIR/tethering-fix-active"
LOG_FILE="/var/log/tethering-fix.log"
HOTSPOT_GATEWAY="172.20.10.1"

# Pattern ASN/org per rilevare carrier MVNO che bloccano il tethering.
# Personalizzare con il pattern del proprio carrier (output di ipinfo.io/org).
# Esempio: "AS12345|nomecarrier|SIGLA-ASN"
CARRIER_PATTERNS="AS8903|lyntia|nomemvno"

# ─── COLORI ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── UTILITA' ────────────────────────────────────────────────

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}Errore: questo script richiede privilegi root${NC}"
        echo "Uso: sudo tethering-fix auto|on|off|status"
        exit 1
    fi
}

is_on_hotspot() {
    local gw
    gw=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}' || true)
    [[ "$gw" == "$HOTSPOT_GATEWAY" ]]
}

detect_carrier() {
    # Ritorna "mvno-bloccante" se il carrier e' riconosciuto, altrimenti l'org dell'IP
    local info
    info=$(curl -4 -s --max-time 5 https://ipinfo.io/org 2>/dev/null || true)

    if [[ -z "$info" ]]; then
        echo "sconosciuto"
        return
    fi

    if echo "$info" | grep -iqE "$CARRIER_PATTERNS"; then
        echo "mvno-bloccante"
    else
        echo "$info"
    fi
}

# ─── ATTIVAZIONE ─────────────────────────────────────────────

activate() {
    echo -e "${GREEN}=== Tethering Fix ON ===${NC}"
    echo ""

    # 1. Tailscale down (interferisce con DNS e routing)
    if command -v tailscale &>/dev/null; then
        tailscale down 2>/dev/null \
            && echo "[OK] Tailscale DOWN" \
            || echo "[SKIP] Tailscale gia' spento"
    else
        echo "[SKIP] Tailscale non installato"
    fi

    # 2. TTL=65 (bypass rilevamento tethering via TTL)
    sysctl -w net.inet.ip.ttl=65 >/dev/null
    echo "[OK] TTL impostato a 65"

    # 3. MTU=1280 (fix PMTUD blackhole, pacchetti grandi non vengono droppati)
    networksetup -setMTU "$WIFI_INTERFACE" 1280 2>/dev/null
    echo "[OK] MTU impostato a 1280"

    # 4. IPv6 off (il routing IPv6 non funziona sui carrier MVNO da viaggio)
    networksetup -setv6off "$WIFI_SERVICE" 2>/dev/null
    echo "[OK] IPv6 disattivato"

    # 5. DNS manuali (evita DNS hotspot lento e conflitti con DNS VPN)
    networksetup -setdnsservers "$WIFI_SERVICE" 1.1.1.1 8.8.8.8
    echo "[OK] DNS impostati a 1.1.1.1 / 8.8.8.8"

    # 6. Flush cache DNS
    dscacheutil -flushcache 2>/dev/null
    killall -HUP mDNSResponder 2>/dev/null
    echo "[OK] Cache DNS svuotata"

    # 7. Blocco UDP 443 (disabilita QUIC/HTTP3, forza TCP per Safari e app Apple)
    echo "block out proto udp from any to any port 443" | pfctl -f - 2>/dev/null || true
    pfctl -e 2>/dev/null || true
    echo "[OK] UDP 443 bloccato (HTTP/3 disabilitato, tutte le app usano HTTP/2 su TCP)"

    # Salva stato
    touch "$STATE_FILE"
    log "FIX ON — attivato"

    echo ""
    echo -e "${GREEN}Pronto. Connetti il browser e verifica la connettivita'.${NC}"
}

# ─── DISATTIVAZIONE ──────────────────────────────────────────

deactivate() {
    echo -e "${YELLOW}=== Tethering Fix OFF ===${NC}"
    echo ""

    # 1. TTL di default
    sysctl -w net.inet.ip.ttl=64 >/dev/null
    echo "[OK] TTL ripristinato a 64"

    # 2. MTU standard
    networksetup -setMTU "$WIFI_INTERFACE" 1500 2>/dev/null
    echo "[OK] MTU ripristinato a 1500"

    # 3. IPv6 automatico
    networksetup -setv6automatic "$WIFI_SERVICE" 2>/dev/null
    echo "[OK] IPv6 ripristinato (automatico)"

    # 4. DNS automatici
    networksetup -setdnsservers "$WIFI_SERVICE" empty
    echo "[OK] DNS ripristinati (automatici)"

    # 5. Flush cache DNS
    dscacheutil -flushcache 2>/dev/null
    killall -HUP mDNSResponder 2>/dev/null
    echo "[OK] Cache DNS svuotata"

    # 6. Rimuovi blocco UDP 443
    pfctl -d 2>/dev/null \
        && echo "[OK] pfctl disattivato (UDP 443 sbloccato)" \
        || echo "[SKIP] pfctl gia' disattivo"

    # 7. Tailscale up (se installato)
    if command -v tailscale &>/dev/null; then
        tailscale up 2>/dev/null \
            && echo "[OK] Tailscale UP" \
            || echo "[SKIP] impossibile avviare Tailscale"
    fi

    # Rimuovi stato
    rm -f "$STATE_FILE"
    log "FIX OFF — ripristinato"

    echo ""
    echo -e "${YELLOW}Tutte le impostazioni ripristinate. Wi-Fi normale pronto.${NC}"
}

# ─── MODALITA' AUTO ──────────────────────────────────────────

auto_mode() {
    echo -e "${CYAN}=== Tethering Fix AUTO ===${NC}"
    echo ""

    # 1. Controlla se si e' sull'hotspot iPhone
    if ! is_on_hotspot; then
        echo "Gateway corrente: non hotspot iPhone (atteso: $HOTSPOT_GATEWAY)"
        if [[ -f "$STATE_FILE" ]]; then
            echo "Il fix era attivo — disattivo per la rete corrente..."
            echo ""
            deactivate
        else
            echo "Niente da fare."
        fi
        return
    fi

    echo "Hotspot iPhone rilevato (gateway: $HOTSPOT_GATEWAY)"

    # 2. Se il fix e' gia' attivo, non rieseguire
    if [[ -f "$STATE_FILE" ]]; then
        log "AUTO — fix gia' attivo, skip"
        echo "Fix gia' attivo. Niente da fare."
        return
    fi

    # 3. Segna subito come attivo per evitare race condition in caso di doppio trigger
    touch "$STATE_FILE"

    # 4. Per rilevare il carrier serve TTL=65, altrimenti curl viene bloccato
    sysctl -w net.inet.ip.ttl=65 >/dev/null 2>&1
    echo "Rilevamento carrier in corso..."

    local carrier
    carrier=$(detect_carrier)

    if [[ "$carrier" == "mvno-bloccante" ]]; then
        echo -e "Carrier: ${RED}MVNO con blocco tethering${NC} — applico tutti i fix"
        echo ""
        activate
    else
        # Carrier non bloccante: ripristina stato e TTL
        rm -f "$STATE_FILE"
        sysctl -w net.inet.ip.ttl=64 >/dev/null 2>&1
        echo -e "Carrier: ${GREEN}$carrier${NC} — nessun fix necessario"
        log "AUTO — carrier non bloccante: $carrier"
    fi
}

# ─── STATO ───────────────────────────────────────────────────

show_status() {
    echo "=== Stato Tethering Fix ==="
    echo ""

    # Fix attivo?
    if [[ -f "$STATE_FILE" ]]; then
        echo -e "Fix:       ${GREEN}ATTIVO${NC}"
    else
        echo -e "Fix:       ${YELLOW}DISATTIVO${NC}"
    fi

    # TTL
    local ttl
    ttl=$(sysctl -n net.inet.ip.ttl)
    if [[ "$ttl" == "65" ]]; then
        echo -e "TTL:       ${GREEN}$ttl (fix attivo)${NC}"
    else
        echo    "TTL:       $ttl (default)"
    fi

    # MTU
    local mtu_line
    mtu_line=$(networksetup -getMTU "$WIFI_INTERFACE" 2>/dev/null)
    if echo "$mtu_line" | grep -q "1280"; then
        echo -e "MTU:       ${GREEN}1280 (fix attivo)${NC}"
    else
        echo    "MTU:       1500 (default)"
    fi

    # DNS
    local dns
    dns=$(networksetup -getdnsservers "$WIFI_SERVICE" 2>/dev/null)
    if echo "$dns" | grep -q "1.1.1.1"; then
        echo -e "DNS:       ${GREEN}1.1.1.1 / 8.8.8.8 (fix attivo)${NC}"
    else
        echo    "DNS:       automatico (default)"
    fi

    # pfctl
    if pfctl -s rules 2>/dev/null | grep -q "udp.*443"; then
        echo -e "UDP 443:   ${GREEN}BLOCCATO — HTTP/3 disabilitato (fix attivo)${NC}"
    else
        echo    "UDP 443:   aperto (default)"
    fi

    # Tailscale
    if command -v tailscale &>/dev/null; then
        local ts_status
        ts_status=$(tailscale status 2>&1 || true)
        if echo "$ts_status" | grep -q "stopped"; then
            echo -e "Tailscale: ${GREEN}DOWN (fix attivo)${NC}"
        else
            echo    "Tailscale: UP (default)"
        fi
    else
        echo    "Tailscale: non installato"
    fi

    # Rete corrente
    echo ""
    if is_on_hotspot; then
        echo -e "Rete:      ${CYAN}Hotspot iPhone (172.20.10.0/24)${NC}"
        echo "Carrier:   $(detect_carrier 2>/dev/null || echo 'non rilevabile')"
    else
        local ssid
        ssid=$(networksetup -getairportnetwork "$WIFI_INTERFACE" 2>/dev/null \
               | sed 's/^Current Wi-Fi Network: //' || true)
        echo    "Rete:      $ssid"
    fi
}

# ─── MAIN ────────────────────────────────────────────────────

case "${1:-}" in
    auto)
        check_root
        auto_mode
        ;;
    on)
        check_root
        activate
        ;;
    off)
        check_root
        deactivate
        ;;
    status)
        show_status
        ;;
    *)
        echo "Uso: sudo tethering-fix auto|on|off|status"
        echo ""
        echo "  auto    Rileva carrier e attiva/disattiva automaticamente"
        echo "  on      Forza attivazione fix (senza rilevamento carrier)"
        echo "  off     Ripristina tutte le impostazioni di default"
        echo "  status  Mostra stato corrente di tutti i parametri"
        echo ""
        echo "Installazione:"
        echo "  sudo cp tethering-fix.sh /usr/local/bin/tethering-fix"
        echo "  sudo chmod 755 /usr/local/bin/tethering-fix"
        exit 1
        ;;
esac
```

### Installazione manuale

```bash
# Copia lo script nella directory bin di sistema
sudo cp tethering-fix.sh /usr/local/bin/tethering-fix
sudo chmod 755 /usr/local/bin/tethering-fix

# Test manuale
sudo tethering-fix status
sudo tethering-fix on
sudo tethering-fix off
```

---

## 11. LaunchDaemon plist

Il LaunchDaemon permette l'esecuzione automatica dello script a ogni cambio di rete,
senza interazione manuale. Deve essere installato in `/Library/LaunchDaemons/` con
permessi `root:wheel 644`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

    <!-- Identificatore univoco del daemon -->
    <key>Label</key>
    <string>it.esim-tethering-fix</string>

    <!-- Comando da eseguire -->
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/tethering-fix</string>
        <string>auto</string>
    </array>

    <!-- Monitora cambi nella configurazione di rete di sistema.
         launchd ri-esegue il comando ogni volta che un file in questa
         directory viene modificato (cambio SSID, nuova interfaccia, ecc.) -->
    <key>WatchPaths</key>
    <array>
        <string>/Library/Preferences/SystemConfiguration</string>
    </array>

    <!-- Esegui anche al boot (una volta caricato il daemon) -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Log stdout e stderr -->
    <key>StandardOutPath</key>
    <string>/var/log/tethering-fix.log</string>

    <key>StandardErrorPath</key>
    <string>/var/log/tethering-fix-error.log</string>

    <!-- Ambiente di esecuzione minimale -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

</dict>
</plist>
```

### Installazione del LaunchDaemon

```bash
# Copia il plist nella directory dei daemon di sistema
sudo cp it.esim-tethering-fix.plist /Library/LaunchDaemons/

# Imposta permessi corretti (root:wheel, non scrivibile da altri)
sudo chown root:wheel /Library/LaunchDaemons/it.esim-tethering-fix.plist
sudo chmod 644 /Library/LaunchDaemons/it.esim-tethering-fix.plist

# Carica e avvia il daemon
sudo launchctl load /Library/LaunchDaemons/it.esim-tethering-fix.plist

# Verifica che sia caricato
sudo launchctl list | grep esim-tethering-fix
```

### Disinstallazione

```bash
# Prima applica il fix OFF per ripristinare le impostazioni
sudo tethering-fix off

# Scarica il daemon
sudo launchctl unload /Library/LaunchDaemons/it.esim-tethering-fix.plist

# Rimuovi i file
sudo rm /Library/LaunchDaemons/it.esim-tethering-fix.plist
sudo rm /usr/local/bin/tethering-fix
```

---

## 12. Risultati dei test

I fix descritti sono stati verificati su hardware reale con la seguente configurazione:

- **Dispositivo**: MacBook Pro con macOS Sequoia
- **iPhone**: iOS 17/18, eSIM carrier MVNO da viaggio
- **Connessione**: Personal Hotspot via Wi-Fi (802.11ax)

### Tabella confronto prima/dopo

| Metrica              | Prima dei fix      | Dopo i fix             |
|----------------------|--------------------|------------------------|
| curl                 | Parziale (TTL fix) | OK                     |
| Chrome               | No / lentissimo    | OK                     |
| Firefox              | No / lentissimo    | OK                     |
| Safari               | No                 | OK                     |
| App Meteo (Apple)    | No                 | OK                     |
| App Mappe (Apple)    | No                 | OK                     |
| Risoluzione DNS      | Timeout / lenta    | < 50ms                 |
| Download speed test  | N/A (bloccato)     | ~22 Mbps               |
| Upload speed test    | N/A (bloccato)     | ~9 Mbps                |
| Latenza (ping)       | N/A (bloccato)     | ~114ms (LTE normale)   |

### Speed test di riferimento

```
Speedtest.net (via hotspot iPhone + eSIM MVNO + fix attivi):
  Download:  22.4 Mbps
  Upload:     9.1 Mbps
  Ping:     114 ms
  Jitter:    8 ms
```

I risultati riflettono la latenza tipica di LTE con routing internazionale (il carrier
MVNO da viaggio instrada attraverso la propria infrastruttura nella nazione di
registrazione, aggiungendo latenza geografica).

### Sequenza di diagnosi suggerita

Se si riscontra il problema descritto, applicare i fix nell'ordine seguente e testare
dopo ciascuno per identificare quali livelli di blocco sono attivi sul proprio carrier:

```
1. sudo sysctl -w net.inet.ip.ttl=65
   --> testa curl https://ipinfo.io/org

2. sudo networksetup -setMTU en0 1280
   --> testa caricamento pagina web pesante

3. sudo networksetup -setv6off "Wi-Fi"
   --> testa velocita' caricamento browser

4. sudo networksetup -setdnsservers "Wi-Fi" 1.1.1.1 8.8.8.8
   sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
   --> testa risoluzione DNS e caricamento pagine

5. echo "block out proto udp from any to any port 443" | sudo pfctl -f -
   sudo pfctl -e
   --> testa Safari e app native Apple
```

Non tutti i carrier implementano tutti i livelli. Alcuni potrebbero bloccare solo TTL
(livello 1), altri potrebbero usare solo il blocco QUIC (livello 5). L'applicazione
selettiva riduce l'impatto sulle prestazioni della rete.

---

## 13. Riferimenti tecnici

- RFC 791 — Internet Protocol (TTL field definition)
- RFC 1191 — Path MTU Discovery
- RFC 4821 — Packetization Layer Path MTU Discovery
- RFC 6555 — Happy Eyeballs: Success with Dual-Stack Hosts
- RFC 8200 — Internet Protocol, Version 6 (IPv6) Specification
- RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport
- RFC 9114 — HTTP/3
- Apple Developer Documentation — `networksetup(8)`, `pfctl(8)`, `sysctl(8)`
- Apple Developer Documentation — LaunchDaemon property list keys
- ipinfo.io API documentation — ASN e organizzazione lookup

---

## 14. Disclaimer

Questo documento e il codice allegato sono forniti esclusivamente a scopo educativo e
di ricerca tecnica sulla diagnostica di rete.

L'autore non si assume alcuna responsabilita' per l'utilizzo di queste tecniche in
violazione dei termini di servizio del proprio carrier o operatore telefonico. Prima di
applicare qualsiasi modifica, verificare che il proprio contratto di servizio consenta
il tethering e l'uso del Personal Hotspot.

Le modifiche descritte (TTL, MTU, IPv6, DNS, pfctl) sono standard di configurazione di
rete documentati e non alterano il traffico di terze parti. Sono temporanee e si
ripristinano automaticamente al riavvio del sistema.

Questo documento non intende facilitare la violazione di contratti commerciali, ma
descrivere il funzionamento tecnico dei meccanismi di rilevamento tethering per scopi
di comprensione e ricerca.
