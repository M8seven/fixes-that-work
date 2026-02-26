# Captive Portal MAC-Based Authentication: Robustness Analysis and Bypass via MAC Spoofing with Proxy Authentication

*Technical Security Document — Wireless Network Security Assessment*

---

## Executive Summary

This document analyzes the robustness of an authentication system based on a **captive portal with MAC-based authorization**, implemented on a public WiFi network with AP Isolation active.

The analysis demonstrates that:

- The association between web authentication (layer 7) and MAC address-based network authorization (layer 2) constitutes a **Weak Identity Binding**: the authorized identity is not cryptographically bound to the authenticated device.
- AP Isolation does not mitigate MAC impersonation attacks, because the attack does not require direct communication between clients.
- The effective security of the system depends largely on **limitations imposed by modern client devices** (e.g., macOS Sequoia), not on the soundness of the architectural mechanism — a pattern known as *Security through Client Capability Limitation*, a fragile and non-deterministic defense.
- The vulnerability does not stem from a configuration error, but from **trust placed in a non-cryptographic identifier**.

This document does not describe an attack aimed at unauthorized access to third-party networks, but analyzes a real case in which a legitimate device (travel router) cannot complete captive portal authentication due to operational limitations, and the security implications that emerge from this.

---

## 1. Operational Context

### 1.1 Network Infrastructure

The WiFi network under analysis, referred to as **"GuestNet"**, is implemented in a hospitality facility (hotel) and adopts the following configuration:

1. **HTTP-based Captive Portal** — Mandatory web authentication before Internet access. Once completed, the client's MAC address is inserted into a whitelist and authorized at the network level.
2. **MAC-based Whitelisting** — Post-authentication traffic is authorized exclusively based on the source MAC address of frames, without further session verification.
3. **AP Isolation (Client Isolation)** — Each wireless client is isolated from others at the L2 level; devices associated with the same Access Point can only communicate with the AP, not with each other.

No WPA2/WPA3-Enterprise (802.1X) authentication is present. This configuration is common in hotels, airports, hospitals, and corporate guest networks.

### 1.2 Devices Involved

| Device | Role | Connection |
|--------|------|------------|
| **Workstation** | User workstation | WiFi → GuestNet (authenticated) |
| **Travel router (headless, no browser)** | Travel router, headless repeater | WiFi → GuestNet (associated, not authenticated) |
| **802.11 monitor mode device** | 802.11 monitor mode, passive analysis | Ethernet → Travel router WAN |

---

## 2. Threat Model

### 2.1 Assumptions

- The attacker is a legitimate user, **associated with the WiFi network**.
- They have no infrastructure privileges (no access to the AP, controller, or RADIUS server).
- They have no physical access to the target device (the travel router is in a remote room).
- They do not perform active attacks against other clients.
- They do not intercept or alter third-party traffic.

### 2.2 Attacker Capabilities

- Knowledge of the target device's MAC address (known from prior configuration, or obtainable via passive reconnaissance in monitor mode).
- Ability to modify their own device's MAC address (platform-dependent — see section 6).
- Access to the captive portal via browser.

### 2.3 Protected Assets

- Internet access, controlled via captive portal.
- Association between user identity (HTTP authentication) and network identity (L2 MAC address).

---

## 3. Architecture and Operational Deadlock

### 3.1 Topology

```
┌──────────────────────────────────────────────────────────────┐
│                      NETWORK "GuestNet"                      │
│            (Captive Portal + AP Isolation + Open Auth)        │
│                                                              │
│   ┌──────────┐         ┌──────────┐         ┌──────────┐    │
│   │ Worksta- │──WiFi──▶│    AP    │◀──WiFi──│  Travel  │    │
│   │  tion    │   ❌     │ GuestNet │    ✓    │  Router  │    │
│   └──────────┘ AP iso   └──────────┘  assoc.  └─────┬────┘   │
│                blocks                  captive      │        │
│              client↔client            portal ❌     │        │
│                                       blocks       │        │
│                                       traffic      │        │
└──────────────────────────────────────────────────────────────┘
                                                     │ ETH
                                               ┌─────┴──────┐
                                               │  Monitor   │
                                               │mode device │
                                               └────────────┘
```

### 3.2 Initial State

| Device | Associated to GuestNet | Authenticated (captive portal) | Internet | Reachable by user |
|--------|:-:|:-:|:-:|:-:|
| Workstation | ✓ | ✓ | ✓ | — |
| Travel Router | ✓ | ❌ | ❌ | ❌ (AP isolation + physical distance) |
| Monitor mode device | via Travel Router ETH | — | ❌ | ❌ (downstream of Travel Router) |

### 3.3 Operational Authentication Deadlock

A **circular condition** arises in which no device can complete the authentication cycle on behalf of another:

1. The **travel router** is associated with the GuestNet network but cannot browse — the captive portal requires browser-based authentication, but the travel router is a **headless router with no browser**.
2. The **workstation** could authenticate the travel router, but **AP Isolation** prevents any L2 communication between the two devices.
3. The **monitor mode device** (equipped with 802.11 monitor mode for passive reconnaissance) is unreachable: it receives connectivity from the travel router via Ethernet, and the travel router has no internet.
4. The user **cannot physically reach** the travel router to connect to its local WiFi (travel router SSID out of radio range).

The result is a deadlock: authentication requires a communication path that the infrastructure itself precludes.

---

## 4. Architectural Weakness: Weak Identity Binding

### 4.1 Separation Between Authentication and Authorization

The system performs two distinct operations:

1. **Application authentication** (layer 7): the user identifies themselves via HTTP interaction with the captive portal.
2. **Network authorization** (layer 2): the system authorizes traffic based on the source MAC address of 802.11 frames.

The core problem lies in the **unbound separation** between these two phases. The association between the application identity (authenticated user) and the network identity (MAC address) is not cryptographically guaranteed.

### 4.2 The MAC Address as an Identifier

The MAC address has characteristics incompatible with a secure authentication factor:

| Property | Security Requirement | MAC Address |
|----------|:--------------------:|:-----------:|
| Secrecy | The identifier must not be observable | ❌ Transmitted in cleartext in every 802.11 frame |
| Immutability | Not modifiable by the client | ❌ Modifiable via software on nearly all platforms |
| Guaranteed uniqueness | Uniquely bound to the device | ❌ Cloneable; multiple devices can use the same MAC |
| Cryptographic verification | Verifiable via challenge-response | ❌ No proof-of-possession mechanism |

This creates a form of **Weak Layer-2 Identity Binding**: the authorized identity is not intrinsically tied to the device that completed authentication.

### 4.3 Analogy

Relying on the MAC address as an authentication factor is equivalent to checking concert tickets by verifying only the **color of the shirt** declared at the entrance — anyone can wear the same color.

---

## 5. Technique: MAC Impersonation for Proxy Authentication

### 5.1 Principle

The technique exploits the Weak Identity Binding described in section 4:

1. Device **A** (proxy) temporarily assumes the MAC of device **B** (target).
2. **A** associates with the network and completes captive portal authentication.
3. The system registers B's MAC as authorized.
4. **A** restores its original MAC.
5. **B**, which uses that MAC natively, is now authorized — the captive portal allows it to browse.

No traffic is intercepted. No Man-in-the-Middle is performed. No third-party traffic is altered. This is a form of **Data Link layer impersonation with delegated authentication**.

### 5.2 Operational Sequence

```
   Proxy Device                AP / Captive Portal              Target Device
       │                              │                              │
  [1]  │── MAC := target_MAC ──▶      │                              │
       │                              │                              │
  [2]  │── Associate (WiFi) ────────▶ │                              │
       │                              │                              │
  [3]  │── HTTP Auth (browser) ──────▶│                              │
       │                              │── whitelist(target_MAC) ──▶  │
       │◀── Auth OK ─────────────────│                              │
       │                              │                              │
  [4]  │── MAC := original_MAC ──▶    │                              │
       │                              │                              │
  [5]  │                              │◀── Traffic (target_MAC) ────│
       │                              │── ✓ Authorized ────────────▶│
       │                              │                              │
```

### 5.3 Classification

| Term | Applicability |
|------|---------------|
| **MAC Spoofing** | Modification of the MAC address to impersonate another device |
| **Proxy Authentication** | Authentication performed on behalf of a third-party device |
| **Captive Portal Bypass** | Circumvention of the portal's authentication mechanism |
| **Masquerading** | Assumption of another party's identity at the network level |

In the **MITRE ATT&CK** taxonomy:
- **T1036 — Masquerading**: the proxy device presents itself with an L2 identity not its own.
- **T1036.005 — Match Legitimate Name or Location**: the cloned MAC corresponds to a device legitimately present on the network.

*Note*: this technique does not constitute an Adversary-in-the-Middle (T1557), as no device is interposed in the communication flow and no traffic is intercepted.

---

## 6. Experimental Validation: Obstacles and Attempts

### 6.1 Attempt 1 — macOS as Proxy (Failed)

**Platform**: Workstation, macOS 15 Sequoia.

A bash script (`proxy-auth.sh`) was developed to automate proxy authentication:

```bash
#!/bin/bash
# Intended sequence (NOT functional on macOS Sequoia)
TRAVEL_ROUTER_MAC="AA:BB:CC:11:22:33"

networksetup -setairportpower en0 off
sleep 2
sudo ifconfig en0 ether "$TRAVEL_ROUTER_MAC"    # ← FAILS
networksetup -setairportpower en0 on
# ... captive portal authentication ...
# ... restore original MAC ...
```

**Result**:
```
ifconfig: ioctl (SIOCAIFADDR): Can't assign requested address
```

**Analysis**: starting with **macOS Monterey (12)**, with growing restrictions in **Sonoma (14)** and **Sequoia (15)**, Apple has progressively blocked arbitrary MAC address modification on WiFi interfaces:

- The `sudo ifconfig en0 ether` command fails with the WiFi interface down; with the interface up, it is silently ignored by the WiFi driver or overwritten on the first association.
- System Settings offers a "Private WiFi Address" toggle (randomized MAC per network), but **does not allow entry of an arbitrary MAC**.
- No native utility (`networksetup`, `airport`, System Settings) supports specifying a custom MAC.
- Attempts from the macOS GUI are equally impossible: there is no interface for setting a user-chosen MAC.

This block is documented in the Apple Developer forums [6] and confirmed by community reports [5][7].

### 6.2 Attempt 2 — Alternative Network-Based Approaches (Blocked)

With the workstation excluded as a proxy device, every network-based alternative is precluded by AP Isolation:

| Approach | Blocker |
|----------|---------|
| ARP scan to locate the travel router on GuestNet | AP Isolation prevents L2 communication between clients |
| Access to travel router admin panel (192.168.8.1) via GuestNet | AP Isolation blocks client→client traffic |
| Use of monitor mode device for passive reconnaissance | Unreachable: downstream of travel router, which has no internet |
| Connection to travel router's local WiFi | Out of radio range (user in another room/floor) |

### 6.3 Attempt 3 — Rooted Android Device as Proxy

**Rationale**: unlike macOS and iOS, **Android with root access** allows full MAC address modification:

```bash
# On rooted Android (adb shell or local terminal)
ip link set wlan0 down
ip link set wlan0 address AA:BB:CC:11:22:33
ip link set wlan0 up
```

A rooted Android smartphone is an ideal candidate:
- **Portable**: the user always has it available, regardless of the travel router's location
- **Browser-equipped**: can complete captive portal authentication
- **Root enables MAC spoofing**: full control over the WiFi interface

### 6.4 Future Solution — Dedicated Hardware (ESP32)

With the availability of **ESP32**-based hardware (M5Stack Cardputer, LILYGO T-Display, etc.), MAC spoofing becomes trivial. The ESP-IDF framework allows full programmatic control over the WiFi MAC:

```c
#include "esp_wifi.h"

uint8_t target_mac[6] = {0xAA, 0xBB, 0xCC, 0x11, 0x22, 0x33};
esp_wifi_set_mac(WIFI_IF_STA, target_mac);
// → WiFi connection + HTTP request for captive portal auth
```

A microcontroller costing approximately €15 can execute the entire procedure (spoof → association → HTTP authentication → disconnection) in an **autonomous and repeatable** manner, without depending on the operating system of a laptop or smartphone.

---

## 7. Security Analysis

### 7.1 Structural Vulnerability

The analyzed system presents the following weaknesses:

| Weakness | Description |
|----------|-------------|
| Absence of cryptographic authentication | No challenge-response, no certificates, no proof of possession |
| Absence of session↔device binding | The authorization token (MAC) is not tied to the HTTP session that generated it |
| Public identifier used as a secret | The MAC is observable by any radio receiver within range of the AP |
| No runtime uniqueness verification | The system does not detect (or does not react to) simultaneous duplicate MACs |

### 7.2 Impact

**Technical**: an actor with monitor mode capability and MAC spoofing can:

1. **Passively observe** the MACs of authenticated clients (wireless reconnaissance, zero packets transmitted).
2. **Clone** an authorized MAC onto their own device.
3. **Gain network access** without authentication.

The technique works on **any MAC-based captive portal**, regardless of the infrastructure vendor.

**Business**: risks include:

- Unauthorized access to the guest network
- Bandwidth consumption that is untracked and unattributable
- Potential **pivoting** toward internal network segments if VLAN segregation is misconfigured
- Economic impact (bandwidth theft) and reputational damage

### 7.3 Advanced Scenario: MAC Conflict and Race Condition

With the simultaneous presence on the network of:
- A legitimate device with the original MAC (online)
- A spoofed device with the same MAC (online)

The following may occur:

| Event | Description |
|-------|-------------|
| **Frame collision** | The AP receives frames from two sources with the same MAC; one is discarded |
| **Automatic deauthentication** | Some enterprise controllers send deauth to the "old" client |
| **Session invalidation** | The captive portal may invalidate the session due to the anomaly |
| **Duplicate MAC logging** | More sophisticated controllers generate alerts |

However, in the Proxy Authentication technique described in this document, the temporal conflict is **minimized**: the proxy device restores its own MAC before the target reassociates, avoiding simultaneous coexistence.

---

## 8. Detection and Logging

### 8.1 Observable Indicators

A monitoring system could detect:

- **Simultaneous duplicate MACs** in the association table
- **ARP flapping**: rapid oscillation of the MAC↔IP association
- **Anomalous deauthentication**: the controller disconnects a client that "appears" from a different radio location
- **RADIUS inconsistencies**: (where present) authentication without a corresponding session

### 8.2 Detection Limitations

Such mechanisms generate **significant false positives** in legitimate scenarios:

- Roaming between APs of the same ESS
- Clients with Private WiFi Address rotating MACs
- Failover and re-association after sleep/wake
- Devices with non-standard WiFi implementations

The signal-to-noise ratio makes reliable detection possible only with **multi-source correlation** (WIDS + RADIUS + flow analysis), rarely implemented on guest networks.

---

## 9. Recommended Mitigations

| Mitigation | Effectiveness | Notes |
|------------|:-------------:|-------|
| **WPA2/WPA3-Enterprise (802.1X)** | **High** | Per-session authentication with individual credentials; mutual authentication; elimination of the captive portal. Resistant to MAC spoofing by design. |
| **RADIUS with client certificates (EAP-TLS)** | **High** | PKI-based mutual authentication; the certificate is a cryptographic secret that cannot be cloned over radio. |
| **Captive portal with cryptographic binding** | **Medium** | Session token bound to MAC + IP + HTTP cookie; timeout and periodic re-validation. Reduces the attack window. |
| **Network Access Control (NAC)** | **Medium-High** | Device fingerprinting, anomaly detection, MAC↔behavior correlation. High deployment complexity. |
| **Duplicate MAC monitoring** | **Low** | Useful secondary control for logging and forensics, but high false-positive rate. Not preventive. |

The primary recommendation is adoption of **802.1X** for any network that requires access control. For guest environments where 802.1X is not practical, cryptographic session↔device binding represents the most reasonable compromise.

---

## 10. Key Architectural Consideration

The security of the analyzed system does not derive from:

- Cryptographic robustness
- Strong authentication
- Defense-in-depth

But from **operational friction and the technical limitations of client devices**.

The fact that macOS Sequoia blocks MAC spoofing is not a security property of the network — it is a side effect of vendor privacy choices. The network is not protected; the attacker is (temporarily) limited.

This is a well-known pattern in security:

> **Security through Client Capability Limitation**

It is a **fragile and non-deterministic** defense: a single platform change (Linux, rooted Android, ESP32) negates it entirely. A €15 microcontroller is sufficient to bypass an authentication system implemented on enterprise-grade infrastructure costing thousands of euros.

---

## 11. Conclusions

The analysis has demonstrated that:

1. **MAC-based authentication is intrinsically weak** — the MAC address does not possess the properties necessary to serve as an authentication factor (it is not secret, not immutable, and not cryptographically verifiable).

2. **AP Isolation is not a mitigation** against the analyzed technique — MAC impersonation does not require direct client-to-client communication, only knowledge of the target MAC and the ability to modify one's own.

3. **The architecture presents a Weak Identity Binding** between application authentication (HTTP) and network authorization (MAC) — the two phases operate on different layers without a cryptographic constraint.

4. **Effective security is accidental, not by design** — it depends on the attacker's operating system restrictions (macOS Sequoia), not on the soundness of the infrastructure. Any platform without such restrictions (Linux, rooted Android, microcontrollers) nullifies the protection.

5. **The cost of the attack is asymmetric** — an ESP32 costing €15 or a rooted smartphone is sufficient to overcome a security mechanism implemented on enterprise network infrastructure.

For environments that require real access control, adoption of **802.1X (WPA2/WPA3-Enterprise)** is recommended, or alternatively, a captive portal with cryptographic session↔device binding that does not rely exclusively on the MAC address as an identity factor.

---

## Sources

1. IEEE 802.11-2020, *Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) Specifications* — Section 4.3.1 (MAC addressing), Section 11.3 (Authentication)
2. MITRE ATT&CK, [T1036 — Masquerading](https://attack.mitre.org/techniques/T1036/)
3. MITRE ATT&CK, [T1036.005 — Masquerading: Match Legitimate Name or Location](https://attack.mitre.org/techniques/T1036/005/)
4. NIST SP 800-153, *Guidelines for Securing Wireless Local Area Networks (WLANs)* — Section 4.2 (WLAN Security Threats)
5. [Change MAC address macOS 15 Sequoia — GitHub Gist](https://gist.github.com/thesauri/022a307234eb3296fae6487cacc1fc1f)
6. [MAC address spoofing not working in macOS 12 Monterey — Apple Developer Forums](https://developer.apple.com/forums/thread/684745)
7. [Getting Ahead of Private Wi-Fi Address Changes in macOS Sequoia — brunerd.com](https://www.brunerd.com/blog/2024/09/27/getting-ahead-of-private-wi-fi-address-changes-in-macos-sequoia/)
8. Wright, J. & Cache, J. (2015). *Hacking Exposed Wireless*, 3rd Edition, McGraw-Hill — Chapter 7: Captive Portal Attacks
9. Vanhoef, M. & Piessens, F. (2017). *Key Reinstallation Attacks: Forcing Nonce Reuse in WPA2*, ACM CCS 2017 — Analysis of weaknesses in L2 authentication
10. OWASP, [Web Security Testing Guide — WSTG-ATHN](https://owasp.org/www-project-web-security-testing-guide/)
11. Espressif Systems, [ESP-IDF Programming Guide — Wi-Fi Driver](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_wifi.html) — `esp_wifi_set_mac()`

---

## Legal Disclaimer

Testing was conducted exclusively on devices owned by the author, without interception, alteration, or monitoring of third-party traffic. No unauthorized access to any network or system was obtained. This document is written for the purpose of architectural analysis, education, and robustness evaluation of captive portal systems.

---

*Security Assessment — 2026*
