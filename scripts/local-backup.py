#!/usr/bin/env python3
"""Private local backup of uncommitted changes before merging the combined branch.

Run from anywhere inside the repo:
    python3 scripts/local-backup.py

What it does:
- Copies tracked-modified and untracked files, plus small ignored files whose
  names look secret-bearing (keys/tokens), into ~/tiptour-backup-<timestamp>
  (mode 0700), preserving their relative paths.
- Records deleted tracked files and symlinks in the manifest (recorded only,
  not copied).
- Skips build output directories (DerivedData, .build, build, node_modules).
- Verifies every copied file's sha256 against the source before finishing.
- Scans backed-up files with fixed secret patterns and reports only the file
  names that matched; it never prints file contents. The scan is a safety
  net, not a guarantee.
- The ignored-file name list covers common key/secret names but is NOT
  complete; do not treat it as a guarantee every secret was included.
- Prints only file names and counts.
- Exits nonzero on any error. A nonzero exit means STOP: do not run any
  git add, switch, merge or commit afterwards.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

SKIP_PREFIXES = ("DerivedData/", ".build/", "build/", "node_modules/", ".git/")
SECRET_NAME_PARTS = (".env", ".dev.vars", ".pem", ".key", ".p8", ".p12",
                     ".xcconfig", ".mobileprovision", ".netrc", "id_rsa",
                     "secret", "credential", "apikey", "api-key", "token")
MAX_SECRET_IGNORED_BYTES = 5 * 1024 * 1024
MAX_SCAN_BYTES = 5 * 1024 * 1024
SECRET_CONTENT = [
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(rb"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}"),
]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def zlist(data):
    return sorted(p for p in data.decode("utf-8", "surrogateescape").split("\0") if p)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg):
    print("backup FAILED: " + msg + " - STOP here, run no git add/switch/merge/commit.", file=sys.stderr)
    sys.exit(1)


def main():
    root = git("rev-parse", "--show-toplevel").decode().strip()
    os.chdir(root)
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(os.path.expanduser("~"), "tiptour-backup-" + ts)
    backup_real = os.path.realpath(backup)

    changed = set(zlist(git("diff", "--name-only", "-z", "--diff-filter=d", "HEAD", "--")))
    changed |= set(zlist(git("ls-files", "-m", "-z")))
    deleted = set(zlist(git("diff", "--name-only", "-z", "--diff-filter=D", "HEAD", "--")))
    deleted |= set(zlist(git("ls-files", "-d", "-z")))
    untracked = set(zlist(git("ls-files", "-o", "--exclude-standard", "-z")))

    ignored_secret = []
    for p in zlist(git("ls-files", "-o", "-i", "--exclude-standard", "-z")):
        if p.startswith(SKIP_PREFIXES):
            continue
        low = p.lower()
        if not any(part in low for part in SECRET_NAME_PARTS):
            continue
        try:
            if os.path.getsize(p) > MAX_SECRET_IGNORED_BYTES:
                continue
        except OSError:
            continue
        ignored_secret.append(p)

    candidates = sorted((changed | untracked | set(ignored_secret)) - deleted)
    symlinks = []
    to_copy = []
    for rel in candidates:
        if rel.startswith(SKIP_PREFIXES):
            continue
        if os.path.islink(rel):
            symlinks.append(rel)
            continue
        if os.path.isfile(rel):
            to_copy.append(rel)
    others = [p for p in candidates
              if not p.startswith(SKIP_PREFIXES)
              and p not in set(to_copy) and p not in set(symlinks)]

    if not to_copy and not deleted and not symlinks:
        print("Nothing uncommitted to back up. Working tree matches HEAD.")
        return

    os.makedirs(backup, mode=0o700, exist_ok=False)
    os.chmod(backup, 0o700)
    manifest = []
    copied = 0
    for rel in to_copy:
        dest = os.path.realpath(os.path.join(backup_real, rel))
        if not (dest == backup_real or dest.startswith(backup_real + os.sep)):
            fail("unsafe path, refusing to copy: " + rel)
        parent = os.path.dirname(dest)
        os.makedirs(parent, exist_ok=True)
        os.chmod(parent, 0o700)
        shutil.copy2(rel, dest)
        os.chmod(dest, 0o600)
        src_hash, dst_hash = sha256(rel), sha256(dest)
        if src_hash != dst_hash:
            fail("hash mismatch after copy: " + rel)
        copied += 1
        manifest.append("copied %d bytes sha256=%s  %s" % (os.path.getsize(rel), src_hash[:16], rel))
    for rel in sorted(deleted):
        manifest.append("deleted locally (recorded only, nothing copied): " + rel)
    for rel in symlinks:
        try:
            target = os.readlink(rel)
        except OSError:
            target = "?"
        manifest.append("symlink -> %s (recorded only, not copied): %s" % (target, rel))
    for rel in others:
        manifest.append("skipped (not a regular file): " + rel)

    flagged = []
    for rel in to_copy:
        try:
            if os.path.getsize(rel) > MAX_SCAN_BYTES:
                continue
            with open(rel, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if any(rx.search(data) for rx in SECRET_CONTENT):
            flagged.append(rel)

    with open(os.path.join(backup_real, "manifest.txt"), "w") as f:
        f.write("tiptour local backup " + ts + "\nrepo: " + root + "\n\n" + "\n".join(manifest) + "\n")
    os.chmod(os.path.join(backup_real, "manifest.txt"), 0o600)

    print("Backup verified: %d file(s) copied to %s (mode 0700, hashes match)." % (copied, backup))
    if deleted:
        print("%d deleted tracked file(s) recorded in manifest.txt (nothing to copy)." % len(deleted))
    if symlinks:
        print("%d symlink(s) recorded in manifest.txt (targets not copied)." % len(symlinks))
    if ignored_secret:
        print("%d ignored secret-looking file(s) included by name pattern." % len(ignored_secret))
    if flagged:
        print("%d backed-up file(s) match secret content patterns (names only, scan not perfect):" % len(flagged))
        for rel in flagged:
            print("  " + rel)
    print("Keep this folder private: do not zip, upload, push or paste it.")


if __name__ == "__main__":
    main()
