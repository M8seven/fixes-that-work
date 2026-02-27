# eSIM Tethering Enforcement on macOS: Multi-Layer Detection Analysis and Bypass via Network Parameter Manipulation

*Author: Valentino Paulon*
*Technical Security Document — Mobile Network Security Assessment*

---

## Executive Summary

This document analyzes the tethering enforcement mechanisms implemented by travel eSIM carriers (MVNOs) and their interaction with macOS when an iPhone Personal Hotspot is used as an upstream connection. The analysis demonstrates that:

- Carrier-side tethering enforcement operates across **five independent detection layers**, spanning IP/TCP header inspection, ICMP path signaling, protocol selection, and DNS infrastructure. Each layer independently degrades or blocks connectivity for tethered clients.
- The commonly documented TTL-modification technique addresses only Layer 1 of the enforcement stack. Applying it alone leaves four additional blocking vectors active, producing symptoms that cannot be distinguished from network misconfiguration.
- The failure mode is **silent and non-obvious**: the tethered host obtains an IP address, DNS resolves, small requests succeed, but browser page loads and native application traffic fail — an inconsistency that systematically misleads standard diagnostic procedures.
- A complete bypass requires coordinated manipulation of five macOS network parameters, none of which requires elevated privileges beyond what `sudo` provides, and all of which are **fully reversible and non-persistent across reboots**.

This document does not describe an attack on third-party infrastructure. It analyzes a real operational scenario where a device owner seeks to use a legitimately provisioned eSIM data plan through a tethering path and documents the technical mechanisms that prevent this, together with the countermeasures that restore function.

---

## 1. Operational Context

### 1.1 Scenario

A traveler provisions a data-only eSIM from a travel MVNO carrier. The eSIM is installed on an iPhone. The traveler connects a MacBook to the iPhone via Personal Hotspot (WiFi). Despite the hotspot association succeeding and IP/DNS being assigned, the MacBook has no usable internet connectivity.

This scenario is increasingly common as travel eSIM usage grows, yet the complete failure mechanism is not publicly documented. Most guides address only the TTL layer, leaving users unable to diagnose residual failures.

### 1.2 Network Topology

```
  MacBook                iPhone                  MVNO Network              Internet
    │                      │                           │                       │
    │──── WiFi (DHCP) ────▶│                           │                       │
    │  172.20.10.0/28       │                           │                       │
    │                       │──── eSIM (LTE/5G) ──────▶│──── transit/peering ─▶│
    │                       │    (carrier data plan)    │                       │
    │                       │                           │  DPI inspection       │
    │                       │                           │  TTL check            │
    │                       │                           │  MTU/ICMP filtering   │
    │                       │                           │  IPv6 routing         │
    │                       │                           │  UDP 443 filtering    │
```

The iPhone acts as a NAT gateway. Traffic originating on the MacBook traverses:

1. The iPhone's internal Wi-Fi hotspot interface (172.20.10.0/28 subnet)
2. The iPhone's IP stack, which forwards and NATs traffic
3. The eSIM cellular interface (PDN/APN toward the MVNO)
4. The MVNO's core network and DPI enforcement plane
5. The MVNO's upstream Internet transit

Each of these hops introduces one or more enforcement points.

### 1.3 Devices and Configuration

| Device | Role | Connection |
|--------|------|------------|
| MacBook (macOS) | Tethered client | Wi-Fi → iPhone Personal Hotspot |
| iPhone (iOS) | Hotspot gateway / NAT | Personal Hotspot + eSIM |
| MVNO Core Network | Carrier enforcement | DPI, packet inspection, filtering |

The MVNO operates on a plan that does not contractually include tethering, or includes it at a throttled tier. Enforcement is applied at the network level, not via MDM or device-side profile.

---

## 2. Threat Model

### 2.1 Perspective

This analysis is written from the perspective of a device owner attempting to use a legitimately provisioned data plan through a path that the carrier's network policy does not permit, and diagnosing why that path fails.

### 2.2 Carrier Capabilities

The MVNO has the following enforcement capabilities at the network level:

- **Deep Packet Inspection (DPI)**: inspection of IP and transport headers on all traffic passing through the PDN gateway.
- **ICMP filtering**: selective discard of ICMP messages that would otherwise facilitate client-side path adaptation.
- **Protocol-level filtering**: ability to block or throttle specific transport protocols (UDP) on specific ports independently of TCP on the same port.
- **IPv6 routing policy**: may not advertise IPv6 routes over tethered PDN sessions, or may not assign IPv6 prefixes to the tethered APN.
- **TTL inspection**: comparison of IP TTL values against expected baselines for direct (non-tethered) traffic.

### 2.3 What the MVNO Cannot Do (in this context)

- Inspect the content of TLS-encrypted payloads (HTTPS traffic is opaque at the application layer).
- Differentiate individual applications on the tethered host.
- Modify the client's device configuration remotely (no MDM profile is installed).

### 2.4 Assets

| Asset | Owner | Enforcement mechanism |
|-------|-------|----------------------|
| Tethered internet access | Carrier restricts | DPI + TTL + ICMP filter + UDP block |
| eSIM data plan | User owns | Provisioned for direct use, not tethering |
| Network configuration | User controls | All parameters modifiable via macOS APIs |

---

## 3. Detection Layer Architecture

The carrier's tethering enforcement is not a single mechanism. It is a stack of independent filters, each of which operates on a different signal. A bypass that addresses only one layer leaves all others active.

```
  MacBook Traffic
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                  MVNO Enforcement Stack                     │
  │                                                             │
  │  Layer 1 ──▶  TTL Inspection          (IP header)          │
  │  Layer 2 ──▶  PMTUD/ICMP Filtering    (ICMP type 3/4)      │
  │  Layer 3 ──▶  IPv6 Routing Policy     (no IPv6 on tether)  │
  │  Layer 4 ──▶  DNS Infrastructure      (client-side tool)   │
  │  Layer 5 ──▶  UDP 443 Blocking        (QUIC / HTTP/3)      │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
        │
        ▼ (traffic that passes all layers reaches Internet)
```

The following sections analyze each layer independently.

---

## 4. Technical Analysis

### 4.1 Layer 1 — TTL-Based Tethering Detection

#### Mechanism

Every IP packet carries a Time-to-Live (TTL) value in its header, decremented by each IP hop that forwards it. Direct traffic from an iPhone to the carrier has a TTL of 64 (iOS default). When the iPhone forwards tethered traffic from the MacBook, it acts as an IP router: it decrements the MacBook's TTL by 1 before sending it to the carrier.

macOS uses a default TTL of 64 for outgoing packets. After iPhone forwarding:

```
  MacBook sends:     TTL = 64
  iPhone decrements: TTL = 63
  Carrier receives:  TTL = 63  → flagged as tethered, dropped
```

The carrier's DPI engine compares the observed TTL against the expected value for a direct mobile endpoint (64). A value of 63 is a reliable signal for NAT-tethered traffic.

This is the only layer that most public guides address.

#### Fix

Set the MacBook's outgoing TTL to 65. After iPhone decrement, the carrier observes 64 — consistent with direct traffic:

```
  MacBook sends:     TTL = 65
  iPhone decrements: TTL = 64
  Carrier receives:  TTL = 64  → consistent with direct device
```

```bash
sudo sysctl -w net.inet.ip.ttl=65
```

This change is in-memory only; it resets to 64 on reboot.

#### Diagnostic signature

Without this fix: all outbound traffic is silently dropped at the carrier. No ICMP unreachable is returned. The connection appears to hang. `curl` with `--verbose` shows the TCP SYN sending but no SYN-ACK arrives.

---

### 4.2 Layer 2 — MTU and Path MTU Discovery Failure

#### Mechanism

The default MTU for Wi-Fi interfaces on macOS is 1500 bytes. However, the effective MTU of the path through the cellular network is lower — typically 1400–1480 bytes, due to encapsulation overhead added by GTP-U tunneling in LTE/5G core networks.

Normally, this is handled by **Path MTU Discovery (PMTUD)** (RFC 1191): when a router cannot forward a packet due to MTU constraints, it returns an ICMP type 3 code 4 message ("Fragmentation Required") to the sender, which then reduces its segment size.

The iPhone's hotspot interface **discards ICMP Fragmentation Required messages** rather than forwarding them to the tethered client. This is a known iOS behavior that affects tethered connections.

The result:

```
  MacBook sends:        Large TCP segment (e.g., 1500 bytes)
  Carrier/iPhone:       MTU exceeded — needs fragmentation
  ICMP type 3/4 sent:  ← dropped at iPhone hotspot interface
  MacBook receives:     Nothing — unaware that fragmentation is needed
  MacBook retransmits:  Same oversized packet → same drop
  Result:               TCP connection stalls silently after initial handshake
```

Small requests (HTTP headers, curl, DNS) fit within the cellular MTU and succeed. Large responses (HTML with embedded resources, JavaScript bundles, images) exceed the MTU and are silently dropped. This produces the characteristic "curl works, browser doesn't" symptom.

#### Fix

Set the MacBook's MTU to 1280 bytes — the mandatory minimum for IPv6 (RFC 8200), and a value guaranteed to traverse any IP network without fragmentation:

```bash
sudo networksetup -setMTU en0 1280
```

At 1280 bytes, all TCP segments are small enough to traverse the cellular path without triggering fragmentation, regardless of the actual path MTU.

The cost is a slight reduction in throughput efficiency (more packets for the same payload), which is negligible on a cellular path already constrained to 10–30 Mbps.

#### Diagnostic signature

With only Layer 1 fixed (TTL=65): `curl https://example.com` returns a response. `curl https://www.google.com` may succeed. Opening a browser and loading a page with embedded resources results in a timeout or partial render. The browser developer console shows stalled requests after the initial byte is received.

---

### 4.3 Layer 3 — IPv6 Routing Failure

#### Mechanism

Travel eSIM carriers frequently do not provision IPv6 on tethered APNs. Either the PDN session is IPv4-only, or the carrier does not delegate an IPv6 prefix to the iPhone for the tethered subnet, or IPv6 routes are not advertised to the tethered client.

macOS and iOS support **Happy Eyeballs** (RFC 8305): when a hostname resolves to both A (IPv4) and AAAA (IPv6) records, the OS attempts IPv6 first with a 250ms head start before initiating the IPv4 attempt in parallel. The first successful connection wins.

When IPv6 is present but non-functional:

```
  DNS resolution:      google.com → 142.250.x.x (A) + 2607:f8b0:... (AAAA)
  IPv6 attempt:        SYN → ... → timeout (25–30 seconds)
  IPv4 attempt:        SYN → SYN-ACK → established
  Effective latency:   250ms + TCP handshake = acceptable
  Worst case:          IPv6 timeout (30s) before IPv4 takes over
```

In practice, it is worse than this: if the IPv6 default route is present but blackholed, the OS may not detect the failure until the TCP connection times out rather than receiving an ICMP unreachable. This can delay the IPv4 fallback by 10–30 seconds per connection, making browsing appear broken.

#### Diagnostic

```bash
ping6 -c 3 google.com    # → "No route to host" or timeout
ping -c 3 google.com     # → replies received
```

#### Fix

Disable IPv6 on the Wi-Fi interface, removing the non-functional address family from the kernel routing table:

```bash
sudo networksetup -setv6off "Wi-Fi"
```

With no IPv6 addresses configured, Happy Eyeballs omits the AAAA attempt and connects directly via IPv4. Connection establishment time drops to a single TCP handshake RTT.

Restore with:

```bash
sudo networksetup -setv6automatic "Wi-Fi"
```

---

### 4.4 Layer 4 — DNS Infrastructure Interference

#### Mechanism

This layer is not carrier-imposed but arises from the interaction between the tethered network and client-side network management tools, particularly VPN clients and mesh networking software (e.g., Tailscale, WireGuard clients, or corporate VPN agents).

These tools commonly:

1. Install a custom DNS resolver address (e.g., `100.100.100.100` for Tailscale) via split-DNS or full-tunnel configuration.
2. Modify the macOS DNS configuration via `scutil` or `networksetup` at activation time.
3. Install routing table entries that intercept DNS traffic and route it through the VPN tunnel.

When the VPN is active but the tethered network cannot reach the VPN's DNS endpoint (because the VPN tunnel itself requires a functional internet connection, which depends on DNS), a circular dependency arises:

```
  DNS query → VPN DNS (100.100.100.100) → VPN tunnel → needs internet
  Internet → needs DNS → VPN DNS → needs internet → ...
```

The result is complete DNS failure, which appears as total loss of connectivity even if the TCP/IP path is otherwise functional.

Additionally, some VPN clients install split routes that capture traffic and route it incorrectly when the expected upstream interface is absent.

#### Fix

Override DNS servers explicitly to bypass any VPN-injected resolver:

```bash
sudo networksetup -setdnsservers "Wi-Fi" 1.1.1.1 8.8.8.8
```

Flush the DNS cache to purge any stale negative entries accumulated during the failure period:

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

If a VPN client is installed, it should be disabled before activating the hotspot connection:

```bash
# Tailscale example
tailscale down
```

Restore automatic DNS on return to normal network:

```bash
sudo networksetup -setdnsservers "Wi-Fi" empty
```

---

### 4.5 Layer 5 — UDP Port 443 Blocking (QUIC / HTTP/3)

#### Mechanism

This is the least obvious layer and the one that produces the most puzzling symptom pattern: `curl` works, Chrome works (slowly), but Safari, Apple Maps, Apple Weather, and other native Apple applications fail entirely or intermittently.

**QUIC** (RFC 9000) is a transport protocol that runs over **UDP port 443**. HTTP/3 uses QUIC as its transport. Apple has aggressively adopted QUIC across its platforms: Safari uses HTTP/3 by default when the server supports it (virtually all major CDNs and Apple's own servers do). Native iOS/macOS applications use `Network.framework`, which enables QUIC by default.

The carrier blocks or severely rate-limits **UDP port 443** on tethered connections. This is a distinct enforcement action from the TTL inspection — it targets the protocol rather than the header field.

The behavioral difference by application:

```
  curl (default):          TCP → HTTP/2 → unaffected by UDP block
  Chrome (Chromium):       Attempts QUIC, falls back to TCP quickly (Chromium's
                           QUIC fallback heuristic is aggressive)
  Safari:                  Attempts QUIC, fallback is slower and less reliable
  Apple native apps:       Use Network.framework with QUIC; fallback behavior
  (Weather, Maps, etc.)    varies by API endpoint; some endpoints may not
                           support HTTP/2 fallback in the same binary
```

This produces the distinctive symptom: a Chromium-based browser loads pages (slowly, via TCP fallback), curl works, but Safari and Apple native applications fail — even after all other layers are addressed.

#### Diagnostic

```bash
# Test UDP 443 specifically (requires nc or ncat):
nc -u -z -w 3 1.1.1.1 443 && echo "UDP 443 open" || echo "UDP 443 blocked"

# Compare curl (TCP) vs a known QUIC endpoint:
curl --http3 -v https://cloudflare.com 2>&1 | head -20
curl --http2 -v https://cloudflare.com 2>&1 | head -20
```

#### Fix

Install a `pf` (Packet Filter) rule on the MacBook that blocks outbound UDP on port 443. Applications cannot send QUIC packets; the OS-level fallback to TCP/TLS/HTTP2 is then triggered:

```bash
echo "block out proto udp from any to any port 443" | sudo pfctl -f -
sudo pfctl -e
```

This intercepts QUIC at the MacBook before the packet reaches the iPhone, preventing the carrier from ever seeing UDP 443. Applications that support HTTP/3 will fall back to HTTP/2 over TCP.

Disable on return to normal network:

```bash
sudo pfctl -d
```

The performance cost is negligible: QUIC's primary advantages (0-RTT, multiplexing without head-of-line blocking) are marginal on a cellular path where RTT already dominates.

---

### 4.6 Layer Interaction and Failure Symptom Matrix

The five layers interact in ways that make diagnosis non-linear. Fixing layers out of order, or fixing only a subset, produces misleading results:

| Layers Fixed | Observed Symptom |
|-------------|------------------|
| None | No connectivity. All TCP connections time out. |
| Layer 1 only (TTL) | Small requests work. Browser stalls on complex pages. Safari/apps fail. |
| Layers 1+2 (TTL+MTU) | Browser pages load (slowly). Safari/apps fail. |
| Layers 1+2+3 (+ IPv6) | Browser pages load faster. Safari/apps still fail. |
| Layers 1+2+3+4 (+ DNS) | Full browser functionality. Apple native apps may still fail. |
| All 5 layers | Full functionality: browser, Safari, native apps, terminal tools. |

This explains why published guides that address only the TTL fix leave users with a partially broken connection that appears to be a different, unrelated problem.

---

## 5. Carrier Detection via ASN Identification

Travel eSIM carriers are MVNOs that route traffic through upstream providers whose ASNs vary by region and over time. Rather than pattern-matching against specific ASNs — which is fragile when a carrier exits on an unexpected upstream — the script uses an inverted whitelist approach: known safe domestic carriers are identified, and everything else is presumed to enforce tethering restrictions.

This property enables programmatic carrier identification from the tethered client:

```bash
# Temporary TTL adjustment required to pass the carrier inspection
# before querying the detection endpoint
sudo sysctl -w net.inet.ip.ttl=65

# Query the ASN/org of the current public IP
curl -4 -s --max-time 5 https://ipinfo.io/org
# Returns e.g.: "AS3303 Swisscom AG" for a domestic carrier,
# or empty / unrecognized ASN for a travel eSIM
```

A legitimate domestic carrier always responds to ipinfo.io with an identifiable ASN. If the query fails or returns an unrecognized carrier, this is itself evidence of enforcement — the traffic is being blocked or rerouted. The script treats both cases (empty response and unrecognized carrier) as presumed enforcement and applies the fix.

```
  Hotspot detected?
       │
       ▼
  TTL=65 temporarily
       │
       ▼
  Query ipinfo.io/org
       │
       ├── Matches known safe carrier (Swisscom, Vodafone, etc.)?
       │          YES → Restore TTL, no action needed
       │          NO  → Apply all 5 layers (unknown = presumed enforcement)
       │
       ▼
  Fix active / inactive
```

---

## 6. MITRE ATT&CK Mapping

While this scenario involves no adversarial intent from the user's perspective, the techniques employed map to standard ATT&CK categories when viewed from a defensive or policy enforcement standpoint. Understanding these mappings clarifies the nature of the enforcement and bypass:

| Technique | ATT&CK ID | Direction (user→carrier or carrier→user) |
|-----------|-----------|------------------------------------------|
| Network traffic manipulation via TTL modification | T1562.004 — Impair Defenses: Disable or Modify System Firewall | User modifies kernel parameter to alter packet characteristics observed by carrier |
| Protocol identification and blocking by carrier | T1071 — Application Layer Protocol | Carrier uses DPI to identify and block QUIC (UDP/443) at the protocol layer |
| DNS hijacking/interference by VPN tools | T1557.003 — Adversary-in-the-Middle: DHCP Spoofing | VPN client redirects DNS without user intent in this specific network context |
| Traffic filtering via pf | T1562.004 — Impair Defenses: Disable or Modify System Firewall | User installs outbound block rule to suppress QUIC at source |
| Network discovery via IP geolocation/ASN query | T1016 — System Network Configuration Discovery | Script queries external API to identify upstream carrier identity |

---

## 7. Automated Remediation

Manual application of five distinct commands is impractical for regular use. The following script automates detection, carrier identification, fix activation, and restoration.

### 7.1 `tethering-fix.sh`

```bash
#!/bin/bash
# tethering-fix — Configures macOS for internet access via iPhone Personal Hotspot
#                 when the upstream eSIM carrier blocks tethered traffic.
#
# Addresses five independent enforcement layers:
#   Layer 1: TTL inspection           → set TTL=65
#   Layer 2: PMTUD/ICMP filtering     → set MTU=1280
#   Layer 3: IPv6 routing failure     → disable IPv6
#   Layer 4: DNS infrastructure       → set manual resolvers, flush cache
#   Layer 5: UDP 443 / QUIC blocking  → block UDP 443 via pf
#
# Usage:
#   sudo tethering-fix auto     Auto-detect carrier, apply/remove fixes as needed
#   sudo tethering-fix on       Force activation of all fixes
#   sudo tethering-fix off      Restore all defaults
#   tethering-fix status        Show current fix state (no sudo required)
#
# All changes are temporary and reset on reboot.

set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

WIFI_INTERFACE="en0"
WIFI_SERVICE="Wi-Fi"
STATE_DIR="${HOME}/Library/Application Support/tethering-fix"
STATE_FILE="${STATE_DIR}/active"
LOG_FILE="${HOME}/Library/Logs/tethering-fix.log"
HOTSPOT_GATEWAY="172.20.10.1"

# Known safe carriers where hotspot works without fixes.
# Everything else on iPhone hotspot is presumed to need the fix.
SAFE_CARRIERS="swisscom|vodafone|sunrise|salt|tim|iliad|wind|tre|o2|orange|t-mobile|bouygues|sfr|free mobile"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() {
    mkdir -p "${STATE_DIR}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "${LOG_FILE}"
}

check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        echo -e "${RED}Error: root required${NC}"
        echo "Usage: sudo tethering-fix auto|on|off"
        exit 1
    fi
}

is_on_hotspot() {
    local gw
    gw=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}' || true)
    [[ "${gw}" == "${HOTSPOT_GATEWAY}" ]]
}

detect_carrier() {
    # Inverted logic: detect SAFE carriers (hotspot works natively).
    # Everything else on iPhone hotspot → apply fix.
    # Rationale: travel eSIM MVNOs exit on unpredictable ASNs (LYNTIA, Cogent,
    # or unresolvable). A known domestic carrier always identifies itself.
    # If detection fails entirely, that itself indicates enforcement.
    local info
    info=$(curl -4 -s --max-time 5 https://ipinfo.io/org 2>/dev/null || true)

    if [[ -z "${info}" ]]; then
        echo "unknown"
        return
    fi

    if echo "${info}" | grep -iqE "${SAFE_CARRIERS}"; then
        echo "${info}"
    else
        echo "travel-esim"
    fi
}

activate() {
    echo -e "${GREEN}=== Tethering Fix ON ===${NC}"
    echo ""

    # Disable VPN/mesh tools that inject DNS and intercept routes.
    # Adjust for the VPN client(s) installed on your system.
    if command -v tailscale &>/dev/null; then
        tailscale down 2>/dev/null \
            && echo "[OK] Tailscale disabled" \
            || echo "[SKIP] Tailscale already stopped"
    fi

    # Layer 1: TTL=65
    # Carrier sees TTL=64 after iPhone decrement → appears as direct traffic.
    sysctl -w net.inet.ip.ttl=65 >/dev/null
    echo "[OK] TTL set to 65"

    # Layer 2: MTU=1280
    # Prevents silent packet drops from PMTUD failure through cellular path.
    networksetup -setMTU "${WIFI_INTERFACE}" 1280 2>/dev/null
    echo "[OK] MTU set to 1280"

    # Layer 3: IPv6 off
    # Removes non-functional IPv6 routes that cause connection delays.
    networksetup -setv6off "${WIFI_SERVICE}" 2>/dev/null
    echo "[OK] IPv6 disabled"

    # Layer 4: Manual DNS
    # Bypasses VPN-injected resolvers and carrier DNS filtering.
    networksetup -setdnsservers "${WIFI_SERVICE}" 1.1.1.1 8.8.8.8
    dscacheutil -flushcache 2>/dev/null
    killall -HUP mDNSResponder 2>/dev/null
    echo "[OK] DNS set to 1.1.1.1 / 8.8.8.8, cache flushed"

    # Layer 5: Block UDP 443 (QUIC/HTTP3)
    # Forces all applications to use HTTP/2 over TCP.
    # Safari and native Apple apps use QUIC by default; this triggers fallback.
    echo "block out proto udp from any to any port 443" | pfctl -f - 2>/dev/null || true
    pfctl -e 2>/dev/null || true
    echo "[OK] UDP 443 blocked (QUIC disabled, HTTP/2 fallback active)"

    mkdir -p "${STATE_DIR}"
    touch "${STATE_FILE}"
    log "FIX ON"

    echo ""
    echo -e "${GREEN}Ready. Connect to the iPhone Personal Hotspot.${NC}"
}

deactivate() {
    echo -e "${YELLOW}=== Tethering Fix OFF ===${NC}"
    echo ""

    # Restore TTL
    sysctl -w net.inet.ip.ttl=64 >/dev/null
    echo "[OK] TTL restored to 64"

    # Restore MTU
    networksetup -setMTU "${WIFI_INTERFACE}" 1500 2>/dev/null
    echo "[OK] MTU restored to 1500"

    # Restore IPv6
    networksetup -setv6automatic "${WIFI_SERVICE}" 2>/dev/null
    echo "[OK] IPv6 set to automatic"

    # Restore DNS
    networksetup -setdnsservers "${WIFI_SERVICE}" empty
    dscacheutil -flushcache 2>/dev/null
    killall -HUP mDNSResponder 2>/dev/null
    echo "[OK] DNS restored to automatic, cache flushed"

    # Disable pf
    pfctl -d 2>/dev/null \
        && echo "[OK] pf disabled (UDP 443 unblocked)" \
        || echo "[SKIP] pf was not active"

    # Re-enable VPN/mesh tools
    if command -v tailscale &>/dev/null; then
        tailscale up 2>/dev/null \
            && echo "[OK] Tailscale re-enabled" \
            || echo "[SKIP] Tailscale start failed"
    fi

    rm -f "${STATE_FILE}"
    log "FIX OFF"

    echo ""
    echo -e "${YELLOW}All settings restored. Normal Wi-Fi ready.${NC}"
}

auto_mode() {
    echo -e "${CYAN}=== Tethering Fix AUTO ===${NC}"
    echo ""

    if ! is_on_hotspot; then
        echo "Not on iPhone hotspot (default gateway is not ${HOTSPOT_GATEWAY})"
        if [[ -f "${STATE_FILE}" ]]; then
            echo "Fix was active; deactivating..."
            echo ""
            deactivate
        else
            echo "Nothing to do."
        fi
        return
    fi

    echo "iPhone hotspot detected (gateway ${HOTSPOT_GATEWAY})"

    if [[ -f "${STATE_FILE}" ]]; then
        log "AUTO: fix already active, skipping"
        echo "Fix already active."
        return
    fi

    # Set the state file immediately to prevent re-entrant execution if the
    # LaunchDaemon fires multiple times during network settling.
    mkdir -p "${STATE_DIR}"
    touch "${STATE_FILE}"

    # Temporarily set TTL=65 so the carrier allows the ipinfo.io request used
    # for carrier detection. Without this, the detection query itself is blocked.
    sysctl -w net.inet.ip.ttl=65 >/dev/null 2>&1
    echo "Detecting carrier..."
    local carrier
    carrier=$(detect_carrier)

    if [[ "${carrier}" == "travel-esim" || "${carrier}" == "unknown" ]]; then
        echo -e "Carrier: ${RED}${carrier} (enforcement presumed)${NC}"
        echo ""
        activate
    else
        rm -f "${STATE_FILE}"
        sysctl -w net.inet.ip.ttl=64 >/dev/null 2>&1
        echo -e "Carrier: ${GREEN}${carrier}${NC} — no fix required"
    fi
}

show_status() {
    echo "=== Tethering Fix Status ==="
    echo ""

    if [[ -f "${STATE_FILE}" ]]; then
        echo -e "Fix:       ${GREEN}ACTIVE${NC}"
    else
        echo -e "Fix:       ${YELLOW}INACTIVE${NC}"
    fi

    local ttl
    ttl=$(sysctl -n net.inet.ip.ttl)
    if [[ "${ttl}" == "65" ]]; then
        echo -e "TTL:       ${GREEN}${ttl} (fix)${NC}"
    else
        echo -e "TTL:       ${ttl} (default)"
    fi

    local mtu_line
    mtu_line=$(networksetup -getMTU "${WIFI_INTERFACE}" 2>/dev/null || echo "")
    if echo "${mtu_line}" | grep -q "1280"; then
        echo -e "MTU:       ${GREEN}1280 (fix)${NC}"
    else
        echo -e "MTU:       1500 (default)"
    fi

    local dns
    dns=$(networksetup -getdnsservers "${WIFI_SERVICE}" 2>/dev/null || echo "")
    if echo "${dns}" | grep -q "1.1.1.1"; then
        echo -e "DNS:       ${GREEN}1.1.1.1 / 8.8.8.8 (fix)${NC}"
    else
        echo -e "DNS:       automatic (default)"
    fi

    if pfctl -s rules 2>/dev/null | grep -q "udp.*443"; then
        echo -e "UDP 443:   ${GREEN}BLOCKED (fix)${NC}"
    else
        echo -e "UDP 443:   open (default)"
    fi

    if command -v tailscale &>/dev/null; then
        local ts_status
        ts_status=$(tailscale status 2>&1 || true)
        if echo "${ts_status}" | grep -q "stopped"; then
            echo -e "Tailscale: ${GREEN}DOWN (fix)${NC}"
        else
            echo -e "Tailscale: UP (default)"
        fi
    fi

    echo ""
    if is_on_hotspot; then
        echo -e "Network:   ${CYAN}iPhone Personal Hotspot${NC}"
    else
        local ssid
        ssid=$(networksetup -getairportnetwork "${WIFI_INTERFACE}" 2>/dev/null \
            | sed 's/^Current Wi-Fi Network: //' || echo "unknown")
        echo "Network:   ${ssid}"
    fi
}

case "${1:-}" in
    auto)   check_root; auto_mode  ;;
    on)     check_root; activate   ;;
    off)    check_root; deactivate ;;
    status) show_status            ;;
    *)
        echo "Usage: sudo tethering-fix auto|on|off|status"
        echo ""
        echo "  auto    Detect carrier and activate/deactivate automatically"
        echo "  on      Force activate all fixes"
        echo "  off     Restore all defaults"
        echo "  status  Show current state (no sudo required)"
        exit 1
        ;;
esac
```

### 7.2 Installation

```bash
# Copy to a directory in PATH
sudo cp tethering-fix.sh /usr/local/bin/tethering-fix
sudo chmod +x /usr/local/bin/tethering-fix

# Create log directory
mkdir -p ~/Library/Logs

# Test
sudo tethering-fix status
```

---

## 8. LaunchDaemon for Automatic Activation

For hands-free operation, a `LaunchDaemon` can watch the SystemConfiguration directory for network changes and invoke `tethering-fix auto` automatically when the network transitions.

### 8.1 Plist

Save as `/Library/LaunchDaemons/com.user.tethering-fix.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.tethering-fix</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/tethering-fix</string>
        <string>auto</string>
    </array>

    <!-- Watch the SystemConfiguration store for network changes.
         macOS updates files in this directory whenever the active
         network interface, default route, or DNS configuration changes. -->
    <key>WatchPaths</key>
    <array>
        <string>/Library/Preferences/SystemConfiguration</string>
    </array>

    <!-- Also run once at load time (catches hotspot that was active at boot). -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Suppress repeated firings during network settling.
         Network transitions generate several rapid file updates;
         throttle to avoid running the script multiple times per event. -->
    <key>ThrottleInterval</key>
    <integer>5</integer>

    <key>StandardOutPath</key>
    <string>/tmp/tethering-fix.out</string>

    <key>StandardErrorPath</key>
    <string>/tmp/tethering-fix.err</string>
</dict>
</plist>
```

### 8.2 Loading and Unloading

```bash
# Load the daemon (persists across reboots)
sudo launchctl load /Library/LaunchDaemons/com.user.tethering-fix.plist

# Verify it loaded
sudo launchctl list | grep tethering-fix

# Unload (disable automatic activation)
sudo launchctl unload /Library/LaunchDaemons/com.user.tethering-fix.plist
```

### 8.3 Operational Flow

```
  Network change detected
  (SystemConfiguration updated)
          │
          ▼
  tethering-fix auto
          │
          ├── Default gateway == 172.20.10.1?
          │         NO  → If fix was active: run deactivate
          │               If fix was inactive: exit
          │
          ▼
          YES: iPhone hotspot detected
          │
          ├── State file exists?
          │         YES → Already active, exit
          │
          ▼
          Set TTL=65 temporarily
          Query ipinfo.io/org
          │
          ├── Matches known safe carrier whitelist?
          │         YES → Restore TTL=64, exit (no fix needed)
          │         NO  → Presumed travel eSIM, run activate (all 5 layers)
          │
          ▼
          All fixes active, state file written
```

---

## 9. Observed Results

The following measurements were taken after applying all five layers on a connection through a travel eSIM carrier:

| Metric | Value |
|--------|-------|
| Download speed | 22 Mbps |
| Upload speed | 9 Mbps |
| Round-trip latency | 114 ms |
| curl (HTTP/2, TCP) | Functional |
| Chrome (Chromium) | Functional |
| Safari | Functional (after Layer 5 fix) |
| Apple Maps | Functional (after Layer 5 fix) |
| Apple Weather | Functional (after Layer 5 fix) |
| Terminal / SSH | Functional |

Without Layer 5 (UDP 443 block), Safari and native Apple apps failed despite all other layers being addressed. This confirmed that the QUIC blocking is a distinct, independently enforced mechanism and not a secondary effect of any other layer.

---

## 10. Comparison with Existing Public Guidance

Public documentation on iPhone hotspot connectivity issues with MVNOs is sparse and incomplete. The most widely referenced solution is the [felikcat/unlimited-hotspot](https://github.com/felikcat/unlimited-hotspot) project (approximately 400 GitHub stars at time of writing), which implements only the TTL modification.

| Approach | TTL (L1) | MTU (L2) | IPv6 (L3) | DNS (L4) | UDP 443 (L5) | Outcome |
|----------|:--------:|:--------:|:---------:|:--------:|:------------:|---------|
| felikcat/unlimited-hotspot | Yes | No | No | No | No | Partial: small requests work; browser stalls; apps fail |
| Most community guides | Yes | No | No | No | No | Same as above |
| This document | Yes | Yes | Yes | Yes | Yes | Complete: all browsers and native apps functional |

The TTL fix is a necessary but insufficient condition for full connectivity against carriers that implement the full detection stack. The diagnostic difficulty arises because the failure modes of layers 2–5 are subtler and produce misleading symptoms.

Additionally, the carrier detection in this document uses an inverted whitelist approach — known safe carriers are identified, and all other carriers are presumed to enforce tethering restrictions. This avoids the fragility of pattern-matching against travel eSIM ASNs, which may route through different upstream providers in different regions.

---

## 11. Mitigations (Carrier Perspective)

For network operators seeking to enforce tethering restrictions more robustly, or conversely for security researchers evaluating the detectability of these techniques:

| Detection method | Robustness | Bypass difficulty | Notes |
|-----------------|:----------:|:-----------------:|-------|
| TTL inspection | Low | Trivial | One sysctl command; widely documented |
| PMTUD blocking | Medium | Easy | MTU reduction is a standard troubleshooting step |
| IPv6 suppression | Low | Easy | IPv6 disable is a standard recommendation for compat issues |
| UDP 443 blocking | Medium-High | Moderate | Requires awareness of QUIC; less commonly documented |
| DPI-based OS fingerprinting | High | Hard | Analyzes TCP options, window sizes, TLS fingerprint (JA3/JA4) |
| Behavioral analysis | High | Hard | Connection patterns, concurrent flows, DNS query patterns |
| IMSI/IMEI correlation | Very High | Very Hard | Requires carrier-side correlation of radio and IP identity |

The five-layer approach described in this document is detectable by carriers that perform deep behavioral or fingerprint analysis. It is not detectable by carriers whose enforcement is limited to TTL and protocol filtering.

---

## 12. Recommended Mitigations (User Perspective)

For users who encounter hotspot connectivity failures that appear intermittent or inconsistent:

1. **Diagnose systematically**: apply fixes in layer order. Each layer has a distinct diagnostic signature. Do not skip to Layer 5 without confirming Layers 1–4 are addressed.

2. **Disable VPN tools before testing**: VPN clients are the most common source of false diagnostic signals. A VPN that appears "connected" may be capturing DNS and routing it incorrectly.

3. **Use `tethering-fix status`** before activating fixes to establish a baseline state.

4. **Accept the MTU penalty**: reducing MTU to 1280 is conservative but reliable. The throughput impact on cellular is negligible; the reliability gain is significant.

5. **Understand that all changes reset on reboot**: there is no permanent modification to system files. If something behaves unexpectedly, rebooting restores all defaults.

---

## 13. Conclusions

The tethering enforcement implemented by travel eSIM carriers consists of five independently operating layers:

1. **TTL inspection** — detects the IP hop count increment caused by iPhone's NAT forwarding.
2. **PMTUD/ICMP filtering** — prevents the tethered client from adapting to the cellular path's effective MTU, causing silent drops of large responses.
3. **IPv6 suppression** — absent or non-functional IPv6 routing causes connection delays through Happy Eyeballs timeout.
4. **DNS infrastructure interference** — VPN and mesh networking tools intercept DNS, creating resolver failures specific to the hotspot network path.
5. **UDP port 443 blocking** — prevents QUIC/HTTP3, selectively breaking Safari and Apple-native applications that default to this transport.

The TTL fix is universally documented; the remaining four layers are not. The complete solution requires addressing all five. The `tethering-fix` script and LaunchDaemon described in this document provide automated detection, activation, and restoration with no persistent system modification.

---

## Sources

1. RFC 1191, *Path MTU Discovery*, J. Mogul & S. Deering, 1990
2. RFC 8305, *Happy Eyeballs Version 2: Better Connectivity Using Concurrency*, D. Schinazi & T. Pauly, 2017
3. RFC 9000, *QUIC: A UDP-Based Multiplexed and Secure Transport*, J. Iyengar & M. Thomson, 2021
4. MITRE ATT&CK, [T1562.004 — Impair Defenses: Disable or Modify System Firewall](https://attack.mitre.org/techniques/T1562/004/)
5. MITRE ATT&CK, [T1016 — System Network Configuration Discovery](https://attack.mitre.org/techniques/T1016/)
6. MITRE ATT&CK, [T1071 — Application Layer Protocol](https://attack.mitre.org/techniques/T1071/)
7. Apple Developer Documentation, [Network.framework — Using QUIC](https://developer.apple.com/documentation/network/using_quic_with_the_network_framework)
8. Apple, [Personal Hotspot — Technical Overview](https://support.apple.com/en-us/HT204023)
9. felikcat, [unlimited-hotspot](https://github.com/felikcat/unlimited-hotspot) — TTL-based tethering bypass for macOS
10. Cloudflare Blog, [The QUIC Transport Protocol](https://blog.cloudflare.com/the-road-to-quic/) — QUIC adoption and fallback behavior
11. NIST SP 800-187, *Guide to LTE Security*, December 2017 — PDN gateway architecture and GTP-U encapsulation
12. 3GPP TS 23.401, *General Packet Radio Service (GPRS) Enhancements for Evolved Universal Terrestrial Radio Access Network (E-UTRAN) Access* — APN and PDN session architecture
13. Apple macOS `pfctl(8)` man page — Packet Filter control interface
14. Apple macOS `sysctl(8)` man page — `net.inet.ip.ttl` kernel parameter

---

## Legal Disclaimer

Testing described in this document was conducted exclusively on devices owned by the author, using a legitimately provisioned eSIM data plan. No traffic belonging to third parties was intercepted, altered, or monitored. No unauthorized access to any network, system, or device was obtained or attempted. The techniques documented here modify only the local macOS network stack and do not involve any intrusion, exploitation of software vulnerabilities, or interference with carrier infrastructure.

This document is published for educational and technical research purposes. The analysis of carrier-side enforcement mechanisms is presented to inform users, security researchers, and network operators. The author makes no representation regarding the compliance of these techniques with any specific carrier's terms of service. Users are responsible for reviewing applicable agreements before implementation.

---

*Security Assessment — 2026*
