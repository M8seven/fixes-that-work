#!/usr/bin/env python3
"""
Cross-browser password merge: Safari + Chrome on macOS.
Reads exported CSV files, deduplicates, and produces merged CSVs
ready for import into both browsers.

Author: Valentino Paulon
License: MIT

Usage:
  1. Export Safari passwords:  System Settings > Passwords > File > Export
  2. Export Chrome passwords:  chrome://password-manager/settings > Download file
  3. Run: python3 merge_passwords.py <safari.csv> <chrome.csv>
  4. Import Merged_Safari.csv into Safari (System Settings > Passwords > File > Import)
  5. Import Merged_Chrome.csv into Chrome (chrome://password-manager/settings > Import)
  6. Delete all CSV files (they contain plaintext passwords)
"""

import csv
import sys
import os
from urllib.parse import urlparse


def get_domain(url):
    """Extract normalized domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except Exception:
        return url.lower()


def read_safari_csv(path):
    """Read Safari password CSV. Columns: Title, URL, Username, Password, Notes, OTPAuth."""
    entries = []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            entries.append({
                'url': row['URL'].strip(),
                'username': row['Username'].strip(),
                'password': row['Password'].strip(),
                'title': row.get('Title', '').strip(),
                'notes': row.get('Notes', '').strip(),
                'otp': row.get('OTPAuth', '').strip(),
            })
    return entries


def read_chrome_csv(path):
    """Read Chrome password CSV. Columns: name, url, username, password, note."""
    entries = []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            entries.append({
                'url': row['url'].strip(),
                'username': row['username'].strip(),
                'password': row['password'].strip(),
                'title': row.get('name', '').strip(),
                'notes': row.get('note', '').strip(),
                'otp': '',
            })
    return entries


def deduplicate(entries):
    """
    Remove duplicate entries with same (domain, username) and same password.
    Keeps the https:// variant when possible. Flags entries with different passwords.
    """
    groups = {}
    for entry in entries:
        key = (get_domain(entry['url']), entry['username'].lower())
        groups.setdefault(key, []).append(entry)

    deduped = []
    conflicts = []

    for (domain, user), group in groups.items():
        passwords = set(e['password'] for e in group)
        if len(passwords) > 1:
            # Different passwords — keep all, flag for manual review
            deduped.extend(group)
            conflicts.append((domain, user, len(group)))
        else:
            # Same password — keep best URL variant
            best = group[0]
            for e in group:
                if 'https' in e['url'] and 'www.' not in e['url']:
                    best = e
                    break
                elif 'https' in e['url']:
                    best = e
            deduped.append(best)

    return deduped, conflicts


def merge(safari_entries, chrome_entries):
    """
    Merge Safari and Chrome entries. Safari is treated as the primary source.
    Chrome-only entries are added. Conflicts are flagged.
    """
    # Build Safari lookup
    safari_lookup = {}
    for entry in safari_entries:
        key = (get_domain(entry['url']), entry['username'].lower())
        safari_lookup.setdefault(key, []).append(entry)

    # Find Chrome-only entries
    chrome_only = []
    conflicts = []
    duplicates_same = 0

    for entry in chrome_entries:
        key = (get_domain(entry['url']), entry['username'].lower())
        if key in safari_lookup:
            safari_match = safari_lookup[key][0]
            if entry['password'] == safari_match['password']:
                duplicates_same += 1
            else:
                conflicts.append({
                    'domain': key[0],
                    'username': key[1],
                    'chrome_pw': entry['password'],
                    'safari_pw': safari_match['password'],
                })
        else:
            chrome_only.append(entry)

    return chrome_only, conflicts, duplicates_same


def write_safari_csv(entries, path):
    """Write merged entries in Safari CSV format."""
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Title', 'URL', 'Username', 'Password', 'Notes', 'OTPAuth'])
        for e in entries:
            title = e['title'] or f"{get_domain(e['url'])} ({e['username']})"
            writer.writerow([title, e['url'], e['username'], e['password'], e['notes'], e['otp']])


def write_chrome_csv(entries, path):
    """Write merged entries in Chrome CSV format."""
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'url', 'username', 'password', 'note'])
        for e in entries:
            name = e['title'] or get_domain(e['url'])
            writer.writerow([name, e['url'], e['username'], e['password'], e['notes']])


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 merge_passwords.py <safari_export.csv> <chrome_export.csv>")
        print("\nExport instructions:")
        print("  Safari: System Settings > Passwords > File > Export Passwords")
        print("  Chrome: chrome://password-manager/settings > Download file")
        sys.exit(1)

    safari_path = sys.argv[1]
    chrome_path = sys.argv[2]

    if not os.path.exists(safari_path):
        print(f"Error: Safari CSV not found: {safari_path}")
        sys.exit(1)
    if not os.path.exists(chrome_path):
        print(f"Error: Chrome CSV not found: {chrome_path}")
        sys.exit(1)

    # Read
    print("Reading CSVs...")
    safari_entries = read_safari_csv(safari_path)
    chrome_entries = read_chrome_csv(chrome_path)
    print(f"  Safari: {len(safari_entries)} entries")
    print(f"  Chrome: {len(chrome_entries)} entries")

    # Deduplicate Safari internal duplicates
    print("\nDeduplicating Safari entries...")
    safari_deduped, safari_conflicts = deduplicate(safari_entries)
    removed = len(safari_entries) - len(safari_deduped)
    print(f"  Removed {removed} duplicates")
    if safari_conflicts:
        print(f"  Entries with different passwords (kept all):")
        for domain, user, count in safari_conflicts:
            print(f"    {domain} [{user}] — {count} variants")

    # Merge
    print("\nMerging...")
    chrome_only, pw_conflicts, duplicates_same = merge(safari_deduped, chrome_entries)
    print(f"  Identical duplicates (no action): {duplicates_same}")
    print(f"  Chrome-only (adding): {len(chrome_only)}")
    if chrome_only:
        for e in chrome_only:
            print(f"    + {get_domain(e['url'])} [{e['username']}]")
    if pw_conflicts:
        print(f"  Password conflicts (manual review needed): {len(pw_conflicts)}")
        for c in pw_conflicts:
            print(f"    {c['domain']} [{c['username']}]")
            print(f"      Chrome: {c['chrome_pw'][:3]}{'*' * max(0, len(c['chrome_pw'])-3)}")
            print(f"      Safari: {c['safari_pw'][:3]}{'*' * max(0, len(c['safari_pw'])-3)}")

    # Create merged list
    merged = safari_deduped + chrome_only
    print(f"\nTotal merged: {len(merged)} entries")

    # Write output
    out_dir = os.path.dirname(safari_path) or '.'
    safari_out = os.path.join(out_dir, 'Merged_Safari.csv')
    chrome_out = os.path.join(out_dir, 'Merged_Chrome.csv')

    write_safari_csv(merged, safari_out)
    write_chrome_csv(merged, chrome_out)

    print(f"\nOutput files:")
    print(f"  {safari_out}")
    print(f"  {chrome_out}")
    print(f"\nNext steps:")
    print(f"  1. Import {safari_out} into Safari (System Settings > Passwords > File > Import)")
    print(f"  2. Import {chrome_out} into Chrome (chrome://password-manager/settings > Import)")
    print(f"  3. DELETE ALL CSV FILES — they contain plaintext passwords!")


if __name__ == '__main__':
    main()
