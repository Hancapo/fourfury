# fourfury

`fourfury` is a Python library for working with Grand Theft Auto IV archives. Its API follows the style of `fivefury`, while implementing GTA IV's native formats instead of reusing GTA V RPF7 structures.

## Initial format support

- RPF2: reading, searching, extraction, creation, and writing.
- Audio RPF3: reading and extraction. Names stored only as hashes are represented in hexadecimal.
- IMG3: reading, searching, extraction, creation, and writing.
- WPL: typed reading and writing for instances, garages, parked cars, culls, StrBig records, LOD culls, zones, and blocks.
- IDE: lossless reading and writing of sectioned definition files, including comments, blank lines, and nested MLO tokens.
- Encrypted stock archives: automatic GTA IV 16-pass AES-256 ECB decryption using the embedded, SHA-1-verified game key.
- RSC5 resources inside RPF and IMG archives: resource headers and flags are preserved, and trailing sector padding after the zlib stream is removed when extracting from IMG archives.

Archive writing is intentionally unencrypted because GTA IV accepts open modified archives. The embedded key is used only to read encrypted stock archives.

## Development installation

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Opening stock archives

```python
from pathlib import Path
from fourfury import ImgArchive, RpfArchive

game = Path(r"D:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto IV\GTAIV")
with RpfArchive.from_path(game / "pc/data/game.rpf") as archive:
    entry = archive.find_entry("data/taskparams.txt")
    print(entry.read().decode("utf-8"))
    archive.extract("game-rpf")

with ImgArchive.from_path(game / "common/data/cdimages/script.img") as archive:
    script = archive.find_entry("advanced_car_actions.sco")
    print(script.read()[:8])
    archive.extract("scripts")
```

## Creating archives

```python
from fourfury import ImgArchive, RpfArchive

rpf = RpfArchive.empty("mod.rpf")
rpf.add_file("data/example.txt", b"fourfury")
rpf.save("mod.rpf")

img = ImgArchive.empty("scripts.img")
img.add_file("example.sco", b"scr\x0e...")
img.save("scripts.img")
```

The convenience APIs `RpfArchive.from_folder(...)`, `ImgArchive.from_folder(...)`, `load_rpf`, `load_img`, `create_rpf`, and `create_img` are also available.

## Map definitions and placements

```python
from fourfury import IdeDocument, WplDocument

ide = IdeDocument.from_path(game / "pc/data/maps/manhat/manhat01.ide")
for entry in ide.iter_entries("objs"):
    print(entry.values[0])

wpl = WplDocument.from_path(game / "pc/data/maps/manhat/manhat01.wpl")
for instance in wpl.instances:
    print(hex(instance.model_hash), instance.flags, instance.lod_index, instance.lod_distance)

# Both formats can be edited and written back.
ide.add_entry("objs", ["example", "example", "100", "0"])
ide.save("example.ide")
wpl.save("example.wpl")
```

The WPL writer preserves trailing bytes such as the sector padding found in some stock files. The IDE writer preserves original lines byte-for-byte until their parsed values are modified.

### WPL instance flags

Instance records expose semantic fields instead of anonymous integers:

```python
from fourfury import WplInstanceFlags

instance = wpl.instances[0]
instance.flags |= WplInstanceFlags.FULL_ROTATION
instance.detail_level = 2

for info in instance.flag_info:
    print(info.flag.name, info.effect, info.confidence)

print(instance.lod_index)     # -1 means no parent LOD instance
print(instance.block_index)   # BLOK association; it may reference inherited map data
print(instance.lod_distance)  # -1.0 uses the model's IDE draw distance
```

| Mask | API name | Effect | Confidence |
| ---: | --- | --- | --- |
| `0x001` | `STREAM_LOW_PRIORITY` | Requests lower-priority streaming. | Inferred from the loader and later RAGE naming. |
| `0x002` | `FULL_ROTATION` | Preserves the complete quaternion instead of the upright fast path. | Verified in the GTA IV loader. |
| `0x004` | `DISABLE_EMBEDDED_COLLISIONS` | Disables collision data embedded in the drawable. | Inferred from the loader and later RAGE naming. |
| `0x020` | `STATIC_ENTITY` | Marks the placement as static. | Inferred from the loader and later RAGE naming. |
| `0x040` | `INTERIOR_LOD` | Marks the placement as an interior LOD. | Inferred from the loader and later RAGE naming. |
| `0x080` | `RUNTIME_STATE_BIT_2` | Sets bit 2 in the secondary entity state word. | Loader behavior verified; higher-level effect unresolved. |
| `0x100` | `RUNTIME_STATE_BIT_3` | Sets bit 3 in the secondary entity state word. | Loader behavior verified; higher-level effect unresolved. |
| `0x200` | `RUNTIME_STATE_BIT_1` | Sets bit 1 in the secondary entity state word. | Loader behavior verified; higher-level effect unresolved. |
| `0xC00` | `DETAIL_LEVEL_MASK` | Stores a detail level from 0 through 3. | Verified in the GTA IV loader. |

`WplInstanceFlags.DEFAULT` is `0x180`, the normal baseline used by most stock map instances. Unknown future bits are retained by `IntFlag` and reported by `instance.flag_info` instead of being discarded.

`GTAIVCrypto.from_game(...)` and `extract_aes_key(...)` remain available when an application wants to verify the embedded key against a local executable.

## Current limitations

- RPF3 writing is not implemented yet; audio RPF3 archives are currently read-only.
- RPF3 names are not stored as text in the archive. The API preserves `name_hash` and uses its hexadecimal representation when no external name dictionary is available.
- IMG3 archives are flat and cannot contain internal directories.
- Asset formats such as `WDR`, `WTD`, `WBN`, and `SCO` are not implemented yet.
