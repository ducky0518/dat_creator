# dat_creator
DAT Creator - Generate RomVault and clrmamepro‑compatible DAT files from any directory tree, with a two‑line live progress display and fully‑customisable header metadata.

## Features

Two‑line live UI – always shows the file currently being hashed and a tqdm progress bar below it.

Header templating – supply <name>, <description>, <category>, <version>, <date>, <author>, <comment>, <url>, and <romvault forcepacking> from the CLI or interactively.

Game‑depth logic – choose which folder level becomes a <game> wrapper (--game-depth).

Loose‑file policy – decide how orphaned files are wrapped (--loose-files strip|parent).

Extension‑strip toggle – keep or remove file‑name extensions when they would clash with game names.

Pure‑Python, no external deps except tqdm (optional, auto‑detected).

## Requirements

Python 3.8 +

Optional: tqdm for a nicer progress bar (pip install tqdm)

## Installation

# clone or download this repo
cd /path/to/repo
python -m venv .venv && source .venv/bin/activate  # optional virtual‑env
pip install tqdm  # optional

No further install step—just run the script.

## Usage

python create_dat_twoline_live.py [options] SOURCE_DIR OUTPUT.dat

### Quick start

python create_dat_twoline_live.py \
  --name "My Collection" --author "Nate" \
  --game-depth 2 --loose-files parent \
  /mnt/roms   MyCollection.dat

### Interactive mode

Leave off any header flag (or use --interactive) and the script will prompt for missing values:

python create_dat_twoline_live.py --interactive /mnt/roms My.dat

### Important options

Flag

Default

Purpose

--name TEXT

(none)

<name> header

--description TEXT



<description> header

--category TEXT



<category> header

--version TEXT



<version> header

--date YYYY-MM-DD

today

<date> header

--author TEXT



<author> header

--comment TEXT



<comment> header

--url TEXT



<url> header

--forcepacking {fileonly,archive,split}

(omitted)

Adds <romvault forcepacking="…"/>

--game-depth N

1

Which folder level becomes a <game> (0 = one global set)

--loose-files {strip,parent}

strip

How to wrap files that aren’t inside a sub‑folder at N depth

--strip-ext / --no-strip-ext

--strip-ext

Keep/remove extensions when game = file

## Loose‑file policy explained

strip – Each loose file becomes its own <game>; the extension is removed so RomVault can create a directory without clashing with the file.

parent – All loose files are placed into a single <game> named after their parent directory, preserving the folder layout.

## Output structure

<datafile>
  <header>…</header>
  <dir name="Category">
    <game name="Title">
      <rom name="file.zip" size="1234" crc="…" md5="…" sha1="…"/>
    </game>
  </dir>
</datafile>

Every <rom> is always inside a <game> by DAT specification.

## Live progress UI

3.42 MiB | Guides/How‑To/Modding.pdf
Hashing ▏███████▍  65%| 812/1250 [00:41<00:22, 19.3 file/s]

Line 1 updates before each file is hashed, so it always reflects the file currently in progress.

## License

MIT License © 2025 Eggman & Contributors

Feel free to open Pull Requests or issues on the project’s GitHub page.
