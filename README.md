# DAT Creator

Generate RomVault and clrmamepro compatible **DAT** files from any directory tree, with a two‑line live progress display and fully‑customisable header metadata.

---

\## Features

- **Two‑line live UI** – always shows the file currently being hashed and a tqdm progress bar below it.
- **Header templating** – supply `<name>`, `<description>`, `<category>`, `<version>`, `<date>`, `<author>`, `<comment>`, `<url>`, and `<romvault forcepacking>` from the CLI or interactively.
- **Game‑depth logic** – choose which folder level becomes a `<game>` wrapper (`--game-depth`).
- **Loose‑file policy** – decide how orphaned files are wrapped (`--loose-files strip|parent`).
- **Extension‑strip toggle** – keep or remove file‑name extensions when they would clash with game names.
- **Pure‑Python**, no external deps except **tqdm** (optional, auto‑detected).

---

\## Requirements

- Python 3.8 +
- Optional: [`tqdm`](https://pypi.org/project/tqdm/) for a nicer progress bar (`pip install tqdm`)

---

\## Installation

```bash
# clone or download this repo
pip install tqdm  # optional
cd /path/to/repo # where you downloaded/copied the dat_creator.py
```

No further install step—just run the script.

---

\## Usage

```bash
python dat_creator.py [options] SOURCE_DIR OUTPUT.dat
```

\### Interactive mode (Quick start)

Leave off any header flag (or use `--interactive`) and the script will prompt for missing values:

```bash
python create_dat_twoline_live.py --interactive /mnt/roms My.dat
```

\### Non-Interactive (example)

```bash
python dat_creator.py --name "My Collection" --author "Mike and Ike" --game-depth 2 --loose-files parent /mnt/stuff MyCollection.dat
```

\### Important options

| Flag                                      | Default       | Purpose                                                        |
| ----------------------------------------- | ------------- | -------------------------------------------------------------- |
| `--name TEXT`                             | *(none)*      | `<name>` header                                                |
| `--description TEXT`                      |               | `<description>` header                                         |
| `--category TEXT`                         |               | `<category>` header                                            |
| `--version TEXT`                          |               | `<version>` header                                             |
| `--date YYYY-MM-DD`                       | today         | `<date>` header                                                |
| `--author TEXT`                           |               | `<author>` header                                              |
| `--comment TEXT`                          |               | `<comment>` header                                             |
| `--url TEXT`                              |               | `<url>` header                                                 |
| `--forcepacking {fileonly,archive,split}` | *(omitted)*   | Adds `<romvault forcepacking="…"/>`                            |
| `--game-depth N`                          | `1`           | Which folder level becomes a `<game>` (0 = one global set)     |
| `--loose-files {strip,parent}`            | `strip`       | How to wrap files that aren’t inside a sub‑folder at `N` depth |
| `--strip-ext / --no-strip-ext`            | `--strip-ext` | Keep/remove extensions when game = file                        |

---

\## Loose‑file policy explained

A `<dir>` may only own other `<dir>` or `<game>` elements; it can’t own <rom> directly. If the script finds a file at a depth where you were expecting a folder, it has to wrap that file in a `<game>` element—there’s no legal way around it in the spec.

In practice you have two options:

Option 1:
(default) Strip the extension and use that as the game-folder.	You’ll see one extra level (“file name without extension”) under the category directory.

Option 2:
Group “loose” files into the parent folder’s game
(i.e. make Category itself a game whenever it holds direct files)	All files in Category appear as ROMs inside a single set named Category. You still have a game wrapper, but you avoid one-game-per-file clutter.
For this approach use the `--loose-files parent` flag

\## Output structure

```xml
<datafile>
  <header>…</header>
  <dir name="Category">
    <game name="Title">
      <rom name="file.zip" size="1234" crc="…" md5="…" sha1="…"/>
    </game>
  </dir>
</datafile>
```

- **strip** – Each loose file becomes its own `<game>`; the extension is removed so RomVault can create a directory without clashing with the file.
- **parent** – All loose files are placed into a single `<game>` named after their parent directory, preserving the folder layout.
---

\## Live progress UI

```
3.42 MiB | Guides/How‑To/Modding.pdf
Hashing ▏███████▍  65%| 812/1250 [00:41<00:22, 19.3 file/s]
```

