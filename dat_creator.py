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
import argparse, datetime, hashlib, os, sys, zlib, xml.etree.ElementTree as ET
from math import log2
try:
    from shutil import get_terminal_size
except ImportError:                                 # <3.3
    get_terminal_size = lambda _=None: os.terminal_size((80, 24))
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

CHUNK = 1 << 16                                     # 64 KiB blocks


# ───────────────────────── helpers ─────────────────────────
def fmt_size(b: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    if b == 0:
        return "0 B"
    e = min(int(log2(b) // 10), len(units) - 1)
    return f"{b / (1 << (10 * e)):.2f} {units[e]}"


def crc32(path: str) -> str:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xFFFFFFFF:08x}"


def md5_sha1(path: str) -> tuple[str, str]:
    m, s = hashlib.md5(), hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            m.update(chunk)
            s.update(chunk)
    return m.hexdigest(), s.hexdigest()


def discover(root: str):
    walker = os.walk(root)
    if tqdm:
        walker = tqdm(walker, desc="Scanning", unit="dir", leave=False)
    items = []
    for d, ds, fs in walker:
        ds.sort()
        fs.sort()
        for f in fs:
            abs_fp = os.path.join(d, f)
            rel_fp = os.path.relpath(abs_fp, root).replace(os.sep, "/")
            items.append((abs_fp, rel_fp, rel_fp.split("/")))
    return items


# ────────────────── header construction ──────────────────
def build_header(parent: ET.Element, a: argparse.Namespace) -> None:
    h = ET.SubElement(parent, "header")
    ordered = [
        ("name",        a.name),
        ("description", a.description),
        ("category",    a.category),
        ("version",     a.version),
        ("date",        a.date or datetime.date.today().isoformat()),
        ("author",      a.author),
        ("comment",     a.comment),
        ("url",         a.url),
    ]
    for tag, val in ordered:
        if val:
            ET.SubElement(h, tag).text = val
    if a.forcepacking:
        ET.SubElement(h, "romvault", forcepacking=a.forcepacking)


# ───── build DAT + two-line live progress ─────
def build_dat(items, root, out_path, a):
    cols = get_terminal_size((80, 24)).columns

    # tqdm bars
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
        )
    else:
        header = None
        bar = items

    # XML skeleton
    root_el = ET.Element("datafile")
    build_header(root_el, a)

    g_global = (
        ET.SubElement(root_el, "game", name=a.name or "DAT")
        if a.game_depth == 0
        else None
    )
    dir_cache: dict[tuple[int, str], ET.Element] = {}
    game_cache: dict[tuple[int, str], ET.Element] = {}

    processed = 0
    for abs_fp, rel_fp, parts in bar:
        # ── decide dir / game / rom names ────────────────────────────────
        if a.game_depth == 0:
            dir_parts, game_name, rom_name = [], a.name or "DAT", rel_fp
        else:
            dir_parts = parts[: max(a.game_depth - 1, 0)]
            game_name = (
                parts[a.game_depth - 1]
                if len(parts) >= a.game_depth
                else (a.name or "DAT")
            )
            rom_name = (
                "/".join(parts[a.game_depth :])
                if len(parts) > a.game_depth
                else parts[-1]
            )

        # Handle loose-file policy
        loose = game_name == rom_name
        if loose:
            if a.loose_files == "parent" and dir_parts:
                # promote parent folder to game
                game_name = dir_parts[-1]
                dir_parts = dir_parts[:-1]
            elif a.loose_files == "strip" and a.strip:
                # keep previous behaviour: strip extension
                game_name, _ = os.path.splitext(game_name)

        # ── update header BEFORE hashing ────────────────────────────────
        size = os.path.getsize(abs_fp)
        size_str = fmt_size(size)
        avail = cols - len(size_str) - 3
        if avail < 1:
            avail = 1
        path_disp = rel_fp if len(rel_fp) <= avail else "…" + rel_fp[-(avail - 1) :]
        line = f"{size_str} | {path_disp}"
        if tqdm:
            header.set_description_str(line, refresh=True)
        else:
            sys.stderr.write("\r" + line.ljust(cols))

        # ── build / look-up dir hierarchy ───────────────────────────────
        parent = root_el
        for lvl, d in enumerate(dir_parts, 1):
            key = (lvl, "/".join(parts[:lvl]))
            if key not in dir_cache:
                dir_cache[key] = ET.SubElement(parent, "dir", name=d)
            parent = dir_cache[key]

        # ── build / look-up game ────────────────────────────────────────
        if a.game_depth == 0:
            game_el = g_global
        else:
            g_key = (len(dir_parts), "/".join(dir_parts + [game_name]))
            if g_key not in game_cache:
                game_cache[g_key] = ET.SubElement(parent, "game", name=game_name)
            game_el = game_cache[g_key]

        # ── heavy hashing & ROM entry ───────────────────────────────────
        crc = crc32(abs_fp)
        md5, sha1 = md5_sha1(abs_fp)
        ET.SubElement(
            game_el,
            "rom",
            name=rom_name,
            size=str(size),
            crc=crc,
            md5=md5,
            sha1=sha1,
        )

        if not tqdm:
            processed += 1
            if processed % 1000 == 0:
                print(f"\nHashed {processed:,} files …", file=sys.stderr, end="")

    if not tqdm:
        print(file=sys.stderr)

    try:
        ET.indent(root_el, space="  ")
    except AttributeError:
        pass
    ET.ElementTree(root_el).write(out_path, encoding="utf-8", xml_declaration=True)


# ─────────────────────────── CLI ───────────────────────────
def parse_args():
    pa = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # positional
    pa.add_argument("source")
    pa.add_argument("output")
    pa.add_argument("name", nargs="?", help="<header><name> (optional)")

    # header flags
    pa.add_argument("--interactive", action="store_true", help="Prompt for any header fields not supplied by flags.")
    pa.add_argument("--name")
    pa.add_argument("--description")
    pa.add_argument("--category")
    pa.add_argument("--version")
    pa.add_argument("--date")
    pa.add_argument("--author")
    pa.add_argument("--comment")
    pa.add_argument("--url")
    pa.add_argument(
        "--forcepacking",
        choices=["fileonly", "archive", "split"],
        help='<romvault forcepacking="…">',
    )

    # behaviour flags
    pa.add_argument("--game-depth", type=int, default=1, metavar="N")
    pa.add_argument(
        "--loose-files",
        choices=["strip", "parent"],
        default="strip",
        help="How to handle loose files that aren’t in a sub-folder.",
    )
    grp = pa.add_mutually_exclusive_group()
    grp.add_argument("--strip-ext", dest="strip", action="store_true", default=True)
    grp.add_argument("--no-strip-ext", dest="strip", action="store_false")

    return pa.parse_args()


# ─────────── interactive prompts for missing header fields ───────────
def maybe_prompt(a: argparse.Namespace) -> None:
    if not a.interactive:
        return

    def ask(attr, prompt):
        if getattr(a, attr) is None:
            val = input(f"{prompt}: ").strip()
            setattr(a, attr, val or None)

    ask("name", "DAT name")
    ask("description", "Description")
    ask("category", "Category")
    ask("version", "Version")
    ask("date", "Date (YYYY-MM-DD, blank = today)")
    ask("author", "Author")
    ask("comment", "Comment")
    ask("url", "URL")

    if a.forcepacking is None:
        fp = input("RomVault forcepacking (fileonly/archive/split, blank = none): ").strip().lower()
        a.forcepacking = fp if fp else None

    if not a.date:
        a.date = datetime.date.today().isoformat()


# ─────────────────────────── main ───────────────────────────
def main():
    a = parse_args()
    maybe_prompt(a)

    files = discover(a.source)
    total = sum(os.path.getsize(f[0]) for f in files)
    print(f"Found {len(files):,} files ({fmt_size(total)}) – hashing …", file=sys.stderr)

    build_dat(files, a.source, a.output, a)
    print(f"Wrote {a.output}")


if __name__ == "__main__":
    main()