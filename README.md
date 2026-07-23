# FourFury

FourFury is a Python library for reading, inspecting, extracting, and editing
Grand Theft Auto IV data files. It provides typed APIs for the game's archives,
world placements, collision resources, drawables, textures, navigation graphs,
and related metadata.

> [!IMPORTANT]
> FourFury is under active development. Read support is broader than write support,
> and some resource types intentionally permit only fixed-size edits.

## Format support

| Format | Read | Write | Notes |
| --- | :---: | :---: | --- |
| RPF2 | Yes | Yes | Search, extraction, creation, and unencrypted output |
| RPF3 | Yes | No | Audio archives; hash-only names remain hexadecimal |
| IMG3 | Yes | Yes | Search, extraction, creation, and resource padding handling |
| IDE | Yes | Yes | Lossless sectioned text, including comments and MLO tokens |
| WPL | Yes | Yes | Placements, culls, garages, zones, and instance flags |
| GTXD | Yes | Yes | Texture-parent chains and cycle detection |
| NOD | Yes | Yes | Navigation nodes, links, costs, and topology validation |
| WNV | Yes | Limited | Navigation meshes, edges, cover points, and quadtrees |
| materials.dat | Yes | No | Typed physical-material catalog |
| WBN | Yes | Limited | Collision bounds and fixed-size edits |
| WBD | Yes | Limited | Collision dictionaries and fixed-size edits |
| WDD | Yes | No | Hash-addressed drawable dictionaries and neutral model projection |
| WDR | Yes | No | Drawables plus neutral model projection |
| WFT | Yes | No | Fragment drawables, physics hierarchy, and collision bounds |
| WTD | Yes | No | Texture dictionaries and DDS export |

See [DOCUMENTATION.md](DOCUMENTATION.md) for examples, field behavior, writer
constraints, and current limitations.

## Installation

FourFury requires Python 3.11 or newer. Install it directly from GitHub:

```powershell
python -m pip install "fourfury @ git+https://github.com/Hancapo/fourfury.git"
```

For an editable installation:

```powershell
git clone https://github.com/Hancapo/fourfury.git
cd fourfury
python -m pip install -e .
```

## Quick start

Open an archive and read one of its entries:

```python
from pathlib import Path

from fourfury import RpfArchive

game = Path(r"D:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto IV\GTAIV")

with RpfArchive.from_path(game / "pc/data/game.rpf") as archive:
    entry = archive.find_entry("data/taskparams.txt")
    if entry is not None:
        print(entry.read().decode("utf-8"))
```

## Documentation

The [complete documentation](DOCUMENTATION.md) covers every supported format,
resource APIs, neutral WDR models, editing constraints, and known limitations.
