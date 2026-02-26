# fixes-that-work

Real solutions to real problems. Tested, documented, and actually working — not the usual "have you tried restarting?" advice.

Each paper documents a problem where mainstream solutions fail, provides root cause analysis through live testing, and delivers a working fix with automation scripts.

---

## Papers

| # | Paper | Problem | Status |
|---|-------|---------|--------|
| 1 | [Captive Portal Bypass](captive-portal-bypass/) | MAC-based captive portal authentication bypass via identity binding weakness | Published |
| 2 | [eSIM Tethering Bypass](esim-tethering-bypass/) | iPhone eSIM hotspot blocked by carrier DPI/TTL/QUIC inspection — 5-layer fix for macOS | Published |

---

## What This Is

A collection of technical papers born from problems that had no working solution online. Each paper follows a consistent structure:

- **Problem** — clearly defined, reproducible
- **Root Cause Analysis** — not guesses, actual diagnosis with packet-level evidence
- **Solution** — tested fix with automation where possible
- **Comparison** — why existing solutions don't work

## What This Is Not

- Not a hacking toolkit
- Not theoretical research
- Not a collection of untested Stack Overflow answers

## Languages

Each paper is available in English and Italian.

- `README.md` — English
- `README.it.md` — Italiano

## License

MIT

## Disclaimer

All research was conducted on author-owned equipment for educational and architectural analysis purposes. No unauthorized access to third-party systems was performed.
