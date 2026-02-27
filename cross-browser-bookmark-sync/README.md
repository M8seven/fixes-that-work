# Cross-Browser Bookmark and Password Synchronization on macOS: Bidirectional Merge Between Safari and Chrome via Direct File Manipulation

*Author: Valentino Paulon*
*Technical Document — macOS Browser Data Interoperability*

---

## Executive Summary

This document addresses the absence of a native bidirectional bookmark and password synchronization mechanism between Safari and Google Chrome on macOS. The analysis demonstrates that:

- Apple and Google maintain **completely isolated bookmark and credential storage systems** with no cross-browser sync capability. Apple's iCloud Bookmarks extension for Chrome functions only on Windows, not macOS.
- Third-party solutions (xBrowserSync, BookMacster, Bookmark UniSync) either **do not support Safari**, require manual intervention, or introduce unacceptable privacy trade-offs by routing data through external servers.
- Safari stores bookmarks in a **binary Property List** (`~/Library/Safari/Bookmarks.plist`) with a nested tree structure, while Chrome uses a **flat JSON file** (`~/Library/Application Support/Google/Chrome/Default/Bookmarks`). These formats are structurally incompatible but both are deterministically parseable.
- Password stores are even more isolated: Safari credentials reside in the **macOS system Keychain** (encrypted, biometric-gated), while Chrome encrypts passwords in a **SQLite database** using a key stored in the Keychain under "Chrome Safe Storage". Neither can be programmatically read without user authentication.
- A complete synchronization workflow is achievable through a combination of **direct file manipulation** (bookmarks) and **CSV-mediated import/export** (passwords), with deduplication logic that handles URL normalization across `http/https`, `www/non-www`, and query parameter variations.

This document provides a tested, automated solution for macOS that requires no third-party software, no browser extensions, and no external servers.

---

## 1. Problem Statement

### 1.1 Operational Context

A user maintains active sessions across both Safari and Chrome on macOS. Bookmarks and saved passwords accumulate independently in each browser, leading to:

- **Data fragmentation** — credentials saved in Chrome are unavailable in Safari and vice versa
- **Duplicate management overhead** — the same bookmark must be manually created in both browsers
- **Password desynchronization** — password updates in one browser do not propagate to the other
- **Accumulated dead weight** — legacy bookmarks (defunct sites, obsolete tools) persist across years without cleanup

### 1.2 Why No Native Solution Exists

| Vendor | Sync scope | Cross-browser support |
|--------|-----------|----------------------|
| Apple (iCloud) | Safari ↔ Safari across Apple devices | None on macOS. iCloud Bookmarks Chrome extension is Windows-only |
| Google (Chrome Sync) | Chrome ↔ Chrome across all platforms | None. Chrome Sync is proprietary and Google-account-bound |
| Third-party extensions | Varies | Most support Chrome + Firefox. Safari support is rare due to Apple's extension restrictions |

The root cause is economic: neither Apple nor Google has incentive to make cross-browser sync easy. Browser lock-in is a strategic advantage for both ecosystems.

---

## 2. Storage Architecture Analysis

### 2.1 Safari Bookmarks — Property List

**Location:** `~/Library/Safari/Bookmarks.plist`

Safari stores bookmarks in a binary Property List with the following tree structure:

```
Root (WebBookmarkTypeList)
├── Cronologia (WebBookmarkTypeProxy)
├── BookmarksBar (WebBookmarkTypeList)
│   ├── Folder A (WebBookmarkTypeList)
│   │   ├── Bookmark 1 (WebBookmarkTypeLeaf)
│   │   └── Bookmark 2 (WebBookmarkTypeLeaf)
│   └── Folder B (WebBookmarkTypeList)
│       └── ...
├── BookmarksMenu (WebBookmarkTypeList)
│   └── ...
└── com.apple.ReadingList (WebBookmarkTypeProxy)
    └── ...
```

Each `WebBookmarkTypeLeaf` node contains:
- `URLString` — the full URL
- `URIDictionary.title` — display title
- `WebBookmarkUUID` — unique identifier

**Access constraints:**
- Safari must be **closed** before modifying the plist. If Safari is running, it holds a lock on the file and will overwrite external changes on next write cycle.
- The file is binary plist format, parseable via Python's `plistlib` module.
- iCloud sync may propagate changes to other Apple devices — this is a feature, not a bug.

### 2.2 Chrome Bookmarks — JSON

**Location:** `~/Library/Application Support/Google/Chrome/Default/Bookmarks`

Chrome uses a flat JSON structure:

```json
{
  "roots": {
    "bookmark_bar": {
      "children": [
        {
          "type": "folder",
          "name": "Folder A",
          "children": [
            {
              "type": "url",
              "name": "Bookmark 1",
              "url": "https://example.com"
            }
          ]
        }
      ]
    },
    "other": { "children": [] },
    "synced": { "children": [] }
  }
}
```

**Access constraints:**
- Chrome must be **closed** before modifying the file. Chrome watches the file via `inotify`/`kqueue` but does not reliably pick up external changes while running.
- If Chrome Sync is enabled, cloud data may overwrite local changes. Sync must be temporarily disabled, cloud data cleared, then re-enabled after local modifications.
- The file is plain JSON, trivially parseable.

### 2.3 Passwords — Encrypted Stores

| Browser | Storage | Encryption | Programmatic access |
|---------|---------|-----------|-------------------|
| Safari | macOS Keychain (`login.keychain-db`) | AES-256, biometric-gated | `security` CLI requires per-item user authorization |
| Chrome | SQLite (`Login Data`) + Keychain key | AES-128-CBC, key in "Chrome Safe Storage" | Requires Keychain access + SQLite decryption |

**Conclusion:** Direct programmatic password manipulation is not feasible without repeated user authentication. The only practical path is CSV export/import through each browser's UI.

---

## 3. Synchronization Methodology

### 3.1 Bookmark Sync — Automated

The sync process operates in three phases:

```
Phase 1: READ
┌─────────────────┐     ┌─────────────────┐
│  Safari plist    │     │  Chrome JSON     │
│  (binary plist)  │     │  (plain JSON)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
    Parse folders           Parse folders
    + bookmarks             + bookmarks
         │                       │
         └──────────┬────────────┘
                    ▼
Phase 2: DIFF
         ┌─────────────────┐
         │  Compare by URL  │
         │  per folder       │
         └────────┬────────┘
                  │
         ┌────────┴────────┐
         ▼                  ▼
   Missing in Safari   Missing in Chrome
                  │
                  ▼
Phase 3: WRITE
   Add missing bookmarks to each browser's file
```

**URL matching strategy:** Bookmarks are compared by exact URL within each folder. This avoids false positives from sites with the same domain but different paths.

### 3.2 Password Merge — Semi-Automated

```
1. Export Safari passwords  →  CSV (via System Settings > Passwords > Export)
2. Export Chrome passwords  →  CSV (via chrome://password-manager/settings)
3. Merge CSVs programmatically:
   a. Deduplicate by (domain, username) — keep one per pair
   b. For same-password duplicates: keep the https:// variant
   c. For different-password duplicates: flag for manual resolution
   d. Identify browser-exclusive entries
4. Import merged CSV into both browsers via UI
5. Delete plaintext CSV files immediately
```

### 3.3 Deduplication Logic

Safari commonly creates duplicate entries for the same credential across URL variants:

| Variant | Example |
|---------|---------|
| Protocol | `http://` vs `https://` |
| WWW prefix | `www.example.com` vs `example.com` |
| Trailing path | `https://example.com/` vs `https://example.com` |
| Query parameters | `?utm_source=...` appended |

The deduplication algorithm normalizes by extracting the domain (stripping `www.`) and grouping by `(domain, username)`. Within each group:
- If all passwords are identical → keep one entry (prefer `https://`, prefer without `www.`)
- If passwords differ → keep all entries (flag for manual review)

---

## 4. Implementation

### 4.1 Prerequisites

- macOS (tested on macOS Sequoia 15.x)
- Python 3.9+ (ships with Xcode Command Line Tools)
- Both Safari and Chrome installed
- No third-party dependencies required

### 4.2 Bookmark Sync Script

The sync script (`sync_bookmarks.py`) performs bidirectional bookmark synchronization:

```python
#!/usr/bin/env python3
"""
Cross-browser bookmark sync: Safari <-> Chrome on macOS.
Both browsers must be closed before running.

Usage: python3 sync_bookmarks.py
"""

import plistlib
import json
import uuid
import subprocess
import sys
import time
from urllib.parse import urlparse

SAFARI_PATH = '~/Library/Safari/Bookmarks.plist'
CHROME_PATH = '~/Library/Application Support/Google/Chrome/Default/Bookmarks'

def is_running(process):
    result = subprocess.run(['pgrep', '-x', process], capture_output=True)
    return result.returncode == 0

def read_safari():
    path = os.path.expanduser(SAFARI_PATH)
    with open(path, 'rb') as f:
        data = plistlib.load(f)

    folders = {}
    for child in data.get('Children', []):
        if child.get('Title') == 'BookmarksBar':
            for folder in child.get('Children', []):
                if folder.get('WebBookmarkType') == 'WebBookmarkTypeList':
                    name = folder.get('Title', '')
                    bookmarks = []
                    for bm in folder.get('Children', []):
                        if bm.get('WebBookmarkType') == 'WebBookmarkTypeLeaf':
                            title = bm.get('URIDictionary', {}).get('title', '') or bm.get('Title', '')
                            url = bm.get('URLString', '')
                            bookmarks.append({'title': title, 'url': url})
                    folders[name] = bookmarks
    return folders, data

def read_chrome():
    path = os.path.expanduser(CHROME_PATH)
    with open(path) as f:
        data = json.load(f)

    folders = {}
    for child in data['roots']['bookmark_bar'].get('children', []):
        if child.get('type') == 'folder':
            name = child.get('name', '')
            bookmarks = []
            for bm in child.get('children', []):
                if bm.get('type') == 'url':
                    bookmarks.append({'title': bm.get('name', ''), 'url': bm.get('url', '')})
            folders[name] = bookmarks
    return folders, data

def sync():
    if is_running('Safari'):
        print("Error: Close Safari before running.")
        sys.exit(1)
    if is_running('Google Chrome'):
        print("Error: Close Chrome before running.")
        sys.exit(1)

    safari_folders, safari_data = read_safari()
    chrome_folders, chrome_data = read_chrome()

    all_folders = set(list(safari_folders.keys()) + list(chrome_folders.keys()))
    changes = False

    for folder in all_folders:
        s_urls = {bm['url'] for bm in safari_folders.get(folder, [])}
        c_urls = {bm['url'] for bm in chrome_folders.get(folder, [])}

        # Add Chrome-only bookmarks to Safari
        for bm in chrome_folders.get(folder, []):
            if bm['url'] not in s_urls:
                # Add to Safari plist
                changes = True

        # Add Safari-only bookmarks to Chrome
        for bm in safari_folders.get(folder, []):
            if bm['url'] not in c_urls:
                # Add to Chrome JSON
                changes = True

    if not changes:
        print("Already in sync. No changes needed.")
    else:
        # Write both files
        print("Sync complete.")

if __name__ == '__main__':
    sync()
```

The full working script is provided in `sync_bookmarks.py` in this directory.

### 4.3 Password Merge Script

The password merge script (`merge_passwords.py`) handles CSV-based deduplication:

```python
# Read both CSVs
# Group by (domain, username)
# Deduplicate same-password entries
# Flag different-password entries for manual review
# Output merged CSVs in both Safari and Chrome import formats
```

The full working script is provided in `merge_passwords.py` in this directory.

---

## 5. Chrome Sync Interaction

### 5.1 The Problem

If Chrome Sync is enabled, Google's cloud stores a copy of all bookmarks. Modifying the local `Bookmarks` file while sync is active results in a merge on next Chrome launch — re-introducing deleted bookmarks from the cloud.

### 5.2 The Fix

A clean sync reset requires four steps:

1. **Disable Chrome Sync** — `chrome://settings/syncSetup` → Turn off sync (without checking "Remove data from this device")
2. **Clear cloud data** — Navigate to `https://chrome.google.com/sync` → "Clear Data". This purges the server-side copy.
3. **Modify local bookmarks** — With sync off and cloud empty, local changes are safe.
4. **Re-enable Chrome Sync** — The clean local state uploads to the cloud as the new canonical copy.

**Critical:** Do not check "Remove bookmarks, history, passwords and other data from this device" when disabling sync. This deletes local data, which is the opposite of the goal.

---

## 6. Results

### 6.1 Test Environment

| Component | Version |
|-----------|---------|
| macOS | Sequoia 15.x |
| Safari | 18.x |
| Chrome | 133.x |
| Python | 3.9.6 (Xcode CLT) |

### 6.2 Bookmark Sync Results

**Before:**
| Browser | Bookmarks | Folders | Dead links |
|---------|-----------|---------|------------|
| Safari | 42 | 3 (flat + ALTRI) | ~5 |
| Chrome | 77 | 12 | ~50 |

**After:**
| Browser | Bookmarks | Folders | Dead links |
|---------|-----------|---------|------------|
| Safari | 39 | 8 (categorized) | 0 |
| Chrome | 39 | 8 (identical) | 0 |

Categories: Email & Chat, OneAnswerAI, AI, Rete, Lavoro, Security, Varie, ALTRI.

### 6.3 Password Merge Results

**Before:**
| Browser | Passwords | Internal duplicates |
|---------|-----------|-------------------|
| Safari | 355 | 23 groups (21 URL variants, 2 genuine different passwords) |
| Chrome | 22 | 0 |

**After:**
| Browser | Passwords | Overlap |
|---------|-----------|---------|
| Safari | 343 | 100% |
| Chrome | 339 | 98.8% (4 entries without URL rejected by Chrome import) |

Password conflicts resolved: 1 (RevenueCat — Safari version confirmed as current via login test).

---

## 7. Limitations

1. **Browser must be closed** — Both Safari and Chrome lock their bookmark files while running. The sync script verifies this and exits with an error if either browser is open.

2. **Password sync is semi-manual** — Due to encryption, password export/import requires user interaction through each browser's settings UI. This cannot be fully automated without compromising security.

3. **Chrome Sync requires reset** — If Chrome Sync is active, the cloud must be cleared before local modifications will persist. This is a one-time operation per sync cycle.

4. **Folder structure must pre-exist** — The sync script adds bookmarks to existing folders. It does not create new folders. Initial folder setup should be done via the setup script or manually.

5. **No conflict resolution for bookmarks** — If the same URL exists in different folders across browsers, both copies are preserved. Manual cleanup may be needed.

---

## 8. Comparison with Existing Solutions

| Solution | Safari support | Bidirectional | Privacy | Cost | Automation |
|----------|---------------|--------------|---------|------|-----------|
| iCloud Bookmarks (Chrome ext.) | macOS: No | N/A | Apple servers | Free | N/A |
| xBrowserSync | No | N/A | Self-hosted option | Free | N/A |
| BookMacster | Yes | Yes | Local | $29 | Manual trigger |
| EverSync | No | N/A | External servers | Free/Paid | Auto |
| Bookmark UniSync | Claimed | Claimed | Unknown | Free | Auto |
| **This solution** | **Yes** | **Yes** | **Fully local** | **Free** | **Script-triggered** |

Key advantage: no external servers, no browser extensions, no subscription fees, no privacy trade-offs. Data never leaves the local machine.

---

## 9. File Reference

| File | Purpose |
|------|---------|
| `sync_bookmarks.py` | Bidirectional bookmark sync script |
| `merge_passwords.py` | Password CSV merge and deduplication |
| `README.md` | This document |
| `README.it.md` | Italian translation |

---

## License

MIT

## Disclaimer

This document describes manipulation of local browser data files on author-owned hardware. No unauthorized access to Apple, Google, or third-party systems was performed. Password handling follows security best practices: plaintext CSV files are created only temporarily and deleted immediately after import.
