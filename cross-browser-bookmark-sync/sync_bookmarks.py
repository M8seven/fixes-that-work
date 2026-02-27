#!/usr/bin/env python3
"""
Cross-browser bookmark sync: Safari <-> Chrome on macOS.
Both browsers must be closed before running.

Author: Valentino Paulon
License: MIT

Usage: python3 sync_bookmarks.py
"""

import plistlib
import json
import uuid
import subprocess
import sys
import os
import time
from urllib.parse import urlparse

SAFARI_PATH = os.path.expanduser('~/Library/Safari/Bookmarks.plist')
CHROME_PATH = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/Bookmarks')


def is_running(process):
    """Check if a process is running by name."""
    result = subprocess.run(['pgrep', '-x', process], capture_output=True)
    return result.returncode == 0


def get_domain(url):
    """Extract normalized domain from URL."""
    try:
        return urlparse(url).netloc.lower().replace('www.', '')
    except Exception:
        return url.lower()


# === SAFARI ===

def read_safari():
    """Read Safari bookmarks from plist. Returns (folders_dict, raw_data)."""
    with open(SAFARI_PATH, 'rb') as f:
        data = plistlib.load(f)

    folders = {}
    bar = None
    for child in data.get('Children', []):
        if child.get('Title') == 'BookmarksBar':
            bar = child
            break

    if not bar:
        print("Warning: BookmarksBar not found in Safari plist.")
        return {}, data

    for child in bar.get('Children', []):
        if child.get('WebBookmarkType') == 'WebBookmarkTypeList':
            folder_name = child.get('Title', '')
            bookmarks = []
            for bm in child.get('Children', []):
                if bm.get('WebBookmarkType') == 'WebBookmarkTypeLeaf':
                    title = bm.get('URIDictionary', {}).get('title', '') or bm.get('Title', '')
                    url = bm.get('URLString', '')
                    bookmarks.append({'title': title, 'url': url})
            folders[folder_name] = bookmarks

    return folders, data


def write_safari(new_bookmarks_by_folder, data):
    """Add new bookmarks to Safari plist. Only adds, never removes."""
    bar = None
    for child in data.get('Children', []):
        if child.get('Title') == 'BookmarksBar':
            bar = child
            break

    if not bar:
        return 0

    added = 0
    for child in bar.get('Children', []):
        if child.get('WebBookmarkType') == 'WebBookmarkTypeList':
            folder_name = child.get('Title', '')
            if folder_name in new_bookmarks_by_folder:
                existing_urls = {
                    bm.get('URLString', '')
                    for bm in child.get('Children', [])
                    if bm.get('WebBookmarkType') == 'WebBookmarkTypeLeaf'
                }
                for bm in new_bookmarks_by_folder[folder_name]:
                    if bm['url'] not in existing_urls:
                        child['Children'].append({
                            'WebBookmarkType': 'WebBookmarkTypeLeaf',
                            'WebBookmarkUUID': str(uuid.uuid4()).upper(),
                            'URLString': bm['url'],
                            'URIDictionary': {'title': bm['title']},
                        })
                        added += 1

    with open(SAFARI_PATH, 'wb') as f:
        plistlib.dump(data, f)

    return added


# === CHROME ===

def read_chrome():
    """Read Chrome bookmarks from JSON. Returns (folders_dict, raw_data)."""
    with open(CHROME_PATH) as f:
        data = json.load(f)

    folders = {}
    for child in data['roots']['bookmark_bar'].get('children', []):
        if child.get('type') == 'folder':
            folder_name = child.get('name', '')
            bookmarks = []
            for bm in child.get('children', []):
                if bm.get('type') == 'url':
                    bookmarks.append({'title': bm.get('name', ''), 'url': bm.get('url', '')})
            folders[folder_name] = bookmarks

    return folders, data


def write_chrome(new_bookmarks_by_folder, data):
    """Add new bookmarks to Chrome JSON. Only adds, never removes."""
    ts = str(int(time.time() * 1000000))
    added = 0

    for child in data['roots']['bookmark_bar'].get('children', []):
        if child.get('type') == 'folder':
            folder_name = child.get('name', '')
            if folder_name in new_bookmarks_by_folder:
                existing_urls = {
                    bm.get('url', '')
                    for bm in child.get('children', [])
                    if bm.get('type') == 'url'
                }
                for bm in new_bookmarks_by_folder[folder_name]:
                    if bm['url'] not in existing_urls:
                        child['children'].append({
                            'date_added': ts,
                            'date_last_used': '0',
                            'guid': '',
                            'id': str(int(ts) + added),
                            'name': bm['title'],
                            'type': 'url',
                            'url': bm['url'],
                        })
                        added += 1

    with open(CHROME_PATH, 'w') as f:
        json.dump(data, f, indent=3)

    return added


# === SYNC ===

def sync():
    """Bidirectional bookmark sync between Safari and Chrome."""

    # Preflight: check both browsers are closed
    if is_running('Safari'):
        print("Error: Close Safari before running this script.")
        sys.exit(1)
    if is_running('Google Chrome'):
        print("Error: Close Chrome before running this script.")
        sys.exit(1)

    print("Reading bookmarks...")
    safari_folders, safari_data = read_safari()
    chrome_folders, chrome_data = read_chrome()

    # Compute diffs
    all_folders = set(list(safari_folders.keys()) + list(chrome_folders.keys()))

    to_add_safari = {}  # bookmarks in Chrome but not Safari
    to_add_chrome = {}  # bookmarks in Safari but not Chrome

    for folder in sorted(all_folders):
        s_urls = {bm['url'] for bm in safari_folders.get(folder, [])}
        c_urls = {bm['url'] for bm in chrome_folders.get(folder, [])}

        new_for_safari = [bm for bm in chrome_folders.get(folder, []) if bm['url'] not in s_urls]
        new_for_chrome = [bm for bm in safari_folders.get(folder, []) if bm['url'] not in c_urls]

        if new_for_safari:
            to_add_safari[folder] = new_for_safari
        if new_for_chrome:
            to_add_chrome[folder] = new_for_chrome

    total_safari = sum(len(v) for v in to_add_safari.values())
    total_chrome = sum(len(v) for v in to_add_chrome.values())

    if total_safari == 0 and total_chrome == 0:
        print("Already in sync. No changes needed.")
        # Print current state
        for folder in sorted(all_folders):
            count = len(safari_folders.get(folder, []))
            print(f"  {folder}: {count} bookmarks")
        total = sum(len(v) for v in safari_folders.values())
        print(f"  Total: {total} bookmarks in {len(all_folders)} folders")
        return

    # Report changes
    if total_safari > 0:
        print(f"\nAdding to Safari ({total_safari}):")
        for folder, bms in to_add_safari.items():
            for bm in bms:
                print(f"  [{folder}] {bm['title']}")

    if total_chrome > 0:
        print(f"\nAdding to Chrome ({total_chrome}):")
        for folder, bms in to_add_chrome.items():
            for bm in bms:
                print(f"  [{folder}] {bm['title']}")

    # Apply changes
    print("\nWriting...")
    if total_safari > 0:
        n = write_safari(to_add_safari, safari_data)
        print(f"  Safari: +{n} bookmarks")
    if total_chrome > 0:
        n = write_chrome(to_add_chrome, chrome_data)
        print(f"  Chrome: +{n} bookmarks")

    print("\nSync complete.")


if __name__ == '__main__':
    sync()
