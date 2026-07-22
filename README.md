# fourfury

`fourfury` is a Python library for working with Grand Theft Auto IV archives. Its API follows the style of `fivefury`, while implementing GTA IV's native formats instead of reusing GTA V RPF7 structures.

## Initial format support

- RPF2: reading, searching, extraction, creation, and writing.
- Audio RPF3: reading and extraction. Names stored only as hashes are represented in hexadecimal.
- IMG3: reading, searching, extraction, creation, and writing.
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

`GTAIVCrypto.from_game(...)` and `extract_aes_key(...)` remain available when an application wants to verify the embedded key against a local executable.

## Current limitations

- RPF3 writing is not implemented yet; audio RPF3 archives are currently read-only.
- RPF3 names are not stored as text in the archive. The API preserves `name_hash` and uses its hexadecimal representation when no external name dictionary is available.
- IMG3 archives are flat and cannot contain internal directories.
- Asset formats such as `WDR`, `WTD`, `WBN`, and `SCO` are not implemented yet.
