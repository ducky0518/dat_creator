#!/usr/bin/env python3
"""
===========

Generate a RomVault / clrmamepro-compatible XML DAT from an existing
directory tree.

Features
--------
* **Full hashing** – CRC-32, MD5, SHA-1 for every file.
* **POSIX paths** – All path separators normalised to '/'.
* **Configurable folder hierarchy** via `--game-depth`:

    Depth meaning (relative to the source root)
    -------------------------------------------
      0  –  Everything is a single <game>; each ROM name stores its *full* path.
      1  –  First-level folder becomes <game>; its files & deeper paths are ROMs.
      2  –  First-level = <dir>, second-level = <game>, rest = ROM paths.
      3+ –  First n-1 levels = nested <dir>, level n = <game>, rest = ROM paths.

Typical use case from the question:
-----------------------------------
    root/
      ├── Category-A/            (dir)
      │     └── Project-1/       (game)
      │          ├── readme.txt
      │          └── docs/manual.pdf
      └── Category-B/
            └── Project-2/
                 └── asset.bin
CLI flags
-------------
--name TEXT	(none)	            <name> header
--description TEXT		        <description> header
--category TEXT		            <category> header
--version TEXT		            <version> header
--date YYYY-MM-DD (today)	    <date> header
--author TEXT		            <author> header
--comment TEXT		            <comment> header
--url TEXT		                <url> header
--forcepacking {fileonly,archive,split}	(Adds <romvault forcepacking="…"/>
--game-depth NUM	            Which folder level becomes a <game> (0 = one global set)
--loose-files {strip,parent}    How to wrap files that aren’t inside a sub‑folder at N depth
--strip-ext / --no-strip-ext	Keep/remove extensions when game = file

Usage (easiest)
-----
    python dat_creator.py --interactive /mnt/roms My.dat
"""

from __future__ import annotations
import argparse, datetime, hashlib, os, sys, time, zlib, xml.etree.ElementTree as ET
from math import log2
from collections import deque
try:
    from shutil import get_terminal_size
except ImportError:
    get_terminal_size = lambda _=None: os.terminal_size((80, 24))
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None                              # fallback if tqdm not installed

CHUNK  = 1 << 16    # 64 KiB
PING_S = 1.0        # UI ping interval while hashing
WIN_S  = 30         # rolling-window length for ETA (seconds)


# ───────────────────────── helpers ─────────────────────────
def fmt_size(b: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    if b == 0:
        return "0 B"
    e = min(int(log2(b) // 10), len(units) - 1)
    return f"{b / (1 << (10 * e)):.2f} {units[e]}"


def discover(root: str):
    """Walk *root* once, returning (file list, total bytes)."""
    walker = os.walk(root)
    if tqdm:
        walker = tqdm(walker, desc="Scanning", unit=" directories", leave=False)
    files, total = [], 0
    for d, ds, fs in walker:
        ds.sort(); fs.sort()
        for f in fs:
            abs_p = os.path.join(d, f)
            rel_p = os.path.relpath(abs_p, root).replace(os.sep, "/")
            files.append((abs_p, rel_p, rel_p.split("/")))
            total += os.path.getsize(abs_p)
    return files, total


# ───────────────────── header XML ─────────────────────
def build_header(parent: ET.Element, a):
    h = ET.SubElement(parent, "header")
    for tag, val in [
        ("name",        a.name),
        ("description", a.description),
        ("category",    a.category),
        ("version",     a.version),
        ("date",        a.date or datetime.date.today().isoformat()),
        ("author",      a.author),
        ("comment",     a.comment),
        ("url",         a.url),
    ]:
        if val:
            ET.SubElement(h, tag).text = val
    if a.forcepacking:
        ET.SubElement(h, "romvault", forcepacking=a.forcepacking)


# ───── hash a file with per-second ping ─────
def hash_file(path, ping_cb):
    size = os.path.getsize(path)
    crc = 0
    md5, sha1 = hashlib.md5(), hashlib.sha1()
    last = time.monotonic()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            crc = zlib.crc32(chunk, crc)
            md5.update(chunk)
            sha1.update(chunk)
            now = time.monotonic()
            if now - last >= PING_S:
                ping_cb()
                last = now
    return size, f"{crc & 0xFFFFFFFF:08x}", md5.hexdigest(), sha1.hexdigest()


# ─────────────── build DAT + live UI ───────────────
def build_dat(items, root, out_path, a, total_bytes):
    cols = get_terminal_size((80, 24)).columns

    # ── initialise progress bars ──
    if tqdm:
        header = tqdm(total=0, position=0, bar_format="{desc}", leave=False)
        bar = tqdm(
            items,
            desc="Hashing",
            unit="file",
            total=len(items),
            position=1,
            leave=False,
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}{postfix}]",
        )
    else:
        header = None
        bar = items

    # ── build XML scaffold ──
    root_el = ET.Element("datafile")
    build_header(root_el, a)
    g_global = (
        ET.SubElement(root_el, "game", name=a.name or "DAT")
        if a.game_depth == 0
        else None
    )
    dir_cache, game_cache = {}, {}

    done_bytes = 0
    window = deque()                      # (timestamp, bytes_done)

    try:
        for abs_fp, rel_fp, parts in bar:
            # ── decide names ───────────────────────────────────────────────
            if a.game_depth == 0:
                dirs, game, rom = [], a.name or "DAT", rel_fp
            else:
                dirs = parts[: max(a.game_depth - 1, 0)]
                game = (
                    parts[a.game_depth - 1]
                    if len(parts) >= a.game_depth
                    else (a.name or "DAT")
                )
                rom = (
                    "/".join(parts[a.game_depth :])
                    if len(parts) > a.game_depth
                    else parts[-1]
                )

            if game == rom:
                if a.loose_files == "parent" and dirs:
                    game = dirs[-1]; dirs = dirs[:-1]
                elif a.loose_files == "strip" and a.strip:
                    game, _ = os.path.splitext(game)

            # ── update header BEFORE hashing ─────────────────────────────
            size_str = fmt_size(os.path.getsize(abs_fp))
            avail = cols - len(size_str) - 3
            path_disp = rel_fp if len(rel_fp) <= avail else "…" + rel_fp[-(avail - 1) :]
            line = f"{size_str} | {path_disp}"
            if tqdm:
                header.set_description_str(line, refresh=True)
            else:
                sys.stderr.write("\r" + line.ljust(cols))

            # ── ping updates rolling ETA ─────────────────────────────────
            def ping():
                now = time.monotonic()
                window.append((now, done_bytes))
                while window and now - window[0][0] > WIN_S:
                    window.popleft()
                if len(window) > 1:
                    span = now - window[0][0]
                    delta = done_bytes - window[0][1]
                    speed = delta / span if span else 0
                    eta = (total_bytes - done_bytes) / speed if speed else 0
                    if tqdm:
                        bar.set_postfix(
                            eta=time.strftime(
                                "%H:%M:%S", time.gmtime(max(0, eta))
                            ),
                            refresh=False,
                        )
                if tqdm:
                    bar.refresh(); header.refresh()
                else:
                    sys.stderr.write("\r" + line.ljust(cols))

            # ── hash file ────────────────────────────────────────────────
            size, crc, md5, sha1 = hash_file(abs_fp, ping)
            done_bytes += size
            ping()  # final update for this file

            # ── XML dirs & game ──────────────────────────────────────────
            parent = root_el
            for lvl, d in enumerate(dirs, 1):
                k = (lvl, "/".join(parts[:lvl]))
                if k not in dir_cache:
                    dir_cache[k] = ET.SubElement(parent, "dir", name=d)
                parent = dir_cache[k]

            if a.game_depth == 0:
                game_el = g_global
            else:
                gk = (len(dirs), "/".join(dirs + [game]))
                if gk not in game_cache:
                    game_cache[gk] = ET.SubElement(parent, "game", name=game)
                game_el = game_cache[gk]

            ET.SubElement(
                game_el,
                "rom",
                name=rom,
                size=str(size),
                crc=crc,
                md5=md5,
                sha1=sha1,
            )

    finally:
        # ── always write what we have ────────────────────────────────────
        if tqdm:
            bar.close()
            header.close()
        else:
            print(file=sys.stderr)

        try:
            ET.indent(root_el, space="  ")
        except AttributeError:
            pass
        ET.ElementTree(root_el).write(
            out_path, encoding="utf-8", xml_declaration=True
        )
        print(f"\nPartial (or complete) DAT written to {out_path}", file=sys.stderr)


# ─────────────── CLI / prompts ───────────────
def parse_args():
    pa = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    pa.add_argument("source")
    pa.add_argument("output")
    pa.add_argument("name", nargs="?")
    pa.add_argument("--interactive", action="store_true")
    for fld in (
        "name",
        "description",
        "category",
        "version",
        "date",
        "author",
        "comment",
        "url",
    ):
        pa.add_argument(f"--{fld}")
    pa.add_argument("--forcepacking", choices=["fileonly", "archive", "split"])
    pa.add_argument("--game-depth", type=int, default=1, metavar="N")
    pa.add_argument("--loose-files", choices=["strip", "parent"], default="strip")
    grp = pa.add_mutually_exclusive_group()
    grp.add_argument("--strip-ext", dest="strip", action="store_true", default=True)
    grp.add_argument("--no-strip-ext", dest="strip", action="store_false")
    return pa.parse_args()


def maybe_prompt(a):
    if not a.interactive:
        return

    def ask(attr, prompt):
        if getattr(a, attr) is None:
            val = input(f"{prompt}: ").strip()
            setattr(a, attr, val or None)

    for attr, prompt in [
        ("name", "DAT name"),
        ("description", "Description"),
        ("category", "Category"),
        ("version", "Version"),
        ("date", "Date (YYYY-MM-DD, blank=today)"),
        ("author", "Author"),
        ("comment", "Comment"),
        ("url", "URL"),
    ]:
        ask(attr, prompt)

    if a.forcepacking is None:
        fp = input(
            "RomVault forcepacking (fileonly/archive/split, blank = none): "
        ).strip().lower()
        a.forcepacking = fp if fp else None

    if not a.date:
        a.date = datetime.date.today().isoformat()


# ─────────────────────────── main ───────────────────────────
def main():
    a = parse_args()
    maybe_prompt(a)

    files, total_bytes = discover(a.source)
    print(
        f"Found {len(files):,} files ({fmt_size(total_bytes)}) – hashing …",
        file=sys.stderr,
    )

    try:
        build_dat(files, a.source, a.output, a, total_bytes)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)


if __name__ == "__main__":
    main()
