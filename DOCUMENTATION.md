# FourFury documentation

This guide describes FourFury's archive, map, collision, drawable, texture, and
navigation APIs. Start with the [public README](README.md) for installation and a
short overview.

FourFury implements Grand Theft Auto IV's native formats directly. It does not
reinterpret GTA IV data as GTA V resources, and the neutral model layer deliberately
has no target-game dependency.

## Contents

- [Supported formats](#supported-formats)
- [Native acceleration](#native-acceleration)
- [Development installation](#development-installation)
- [Opening stock archives](#opening-stock-archives)
- [Creating archives](#creating-archives)
- [Map definitions and placements](#map-definitions-and-placements)
- [Navigation paths](#navigation-paths)
- [Collision bounds](#collision-bounds)
- [Drawable models](#drawable-models)
- [Texture dictionaries and GTXD parents](#texture-dictionaries-and-gtxd-parents)
- [WPL instance flags](#wpl-instance-flags)
- [Current limitations](#current-limitations)

## Supported formats

- RPF2: reading, searching, extraction, creation, and writing.
- Audio RPF3: reading and extraction. Names stored only as hashes are represented in hexadecimal.
- IMG3: reading, searching, extraction, creation, and writing.
- WPL: typed reading and writing for instances, garages, parked cars, culls, StrBig records, LOD culls, zones, and blocks.
- IDE: lossless reading and writing of sectioned definition files, including comments, blank lines, and nested MLO tokens.
- GTXD/`txdp`: typed child-to-parent texture dictionary hierarchies, lossless editing, chain resolution, and cycle detection.
- NOD: typed vehicle and pedestrian navigation graphs with fixed-point positions, directed links, path costs, behavior-flag confidence metadata, and lossless editing.
- `materials.dat`: typed physical-material catalogs with names, FX groups, friction, elasticity, density, grip, combustion, and behavior flags.
- WBD: typed RSC5 collision dictionaries with JOAAT lookup, shared bounds, material resolution, and lossless fixed-size editing.
- WBN: typed RSC5 collision bounds, composites, quantized geometry, resolved physical materials, polygons, and BVH trees, with lossless fixed-size editing.
- WDR: typed RSC5 drawables with LODs, models, decoded vertex declarations, vertex and index buffers, shaders, embedded textures, skeletons, and lights.
- WTD: typed RSC5 texture dictionaries with names, dimensions, formats, mip chains, raw payloads, and DDS export.
- Encrypted stock archives: automatic GTA IV 16-pass AES-256 ECB decryption using the embedded, SHA-1-verified game key.
- RSC5 resources inside RPF and IMG archives: resource headers and flags are preserved, and trailing sector padding after the zlib stream is removed when extracting from IMG archives.

Archive writing is intentionally unencrypted because GTA IV accepts open modified archives. The embedded key is used only to read encrypted stock archives.

## Native acceleration

FourFury includes an optional C++17 extension for performance-sensitive kernels.
Source installations attempt to compile it when a compatible compiler is available;
if compilation is unavailable, installation continues with the equivalent Python
fallbacks. The native module uses CPython's stable 3.11 ABI.

On Windows, the native AES kernel keeps the cached BCrypt key and all sixteen GTA IV
decryption passes inside one native call. No native APIs are exposed as part of the
public compatibility contract; applications should continue using `GTAIVCrypto`.

The native WDR decoder materializes vertex declarations as semantic columns. Parsed
`WdrVertexBuffer.attribute_channels` can be consumed without allocating one dictionary
per vertex; the existing `vertices` property remains available and creates row-oriented
`WdrVertex` objects lazily. `WdrDocument.to_model()` reads the columns directly.

The native WBN decoder handles the fixed-size quantized vertex, polygon, BVH node,
and BVH subtree records. Parsing still returns the same mutable `WbnVertex`,
`WbnPolygon`, `WbnBvhNode`, and `WbnBvhSubTree` objects, so native acceleration does
not change the public API or editing behavior.

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
    if entry is None:
        raise FileNotFoundError("data/taskparams.txt")
    print(entry.read().decode("utf-8"))
    archive.extract("game-rpf")

with ImgArchive.from_path(game / "common/data/cdimages/script.img") as archive:
    script = archive.find_entry("advanced_car_actions.sco")
    if script is None:
        raise FileNotFoundError("advanced_car_actions.sco")
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

## Navigation paths

The 64 `nodes*.nod` files in `pc/data/cdimages/paths.img` divide the city into pathfinding sectors. Vehicle and pedestrian nodes are exposed separately while retaining their shared directed graph:

```python
from fourfury import ImgArchive, NodDocument

with ImgArchive.from_path(game / "pc/data/cdimages/paths.img") as archive:
    entry = archive.find_entry("nodes32.nod")
    if entry is None:
        raise FileNotFoundError("nodes32.nod")
    paths = NodDocument.from_bytes(entry.read(), name=entry.name)

for node in paths.vehicle_nodes:
    print(node.key, node.position, node.path_width, node.link_count)
    if node.is_intersection:
        print("intersection", node.flag_info)
    if node.is_boat:
        print("boat route")
    for link in node.outgoing_links:
        destination = link.resolve(paths)  # None when the link enters another sector.
        print(link.target_key, link.length, link.pathfinding_cost, destination)
```

Node positions and path widths use their world-space values in the public API. The original fixed-point encodings remain exactly reproducible. `runtime_address` and `source_path_value` deliberately describe the provenance of the two compiler metadata fields instead of assigning speculative behavior to them. Undocumented behavior bits are preserved collectively in `unresolved_flags`; the four embedded adjacency-count bits are exposed as `link_count` and can be edited with `set_link_count()`.

NOD writing supports new documents and topology-preserving edits. When changing topology, link records must remain contiguous per node and `link_start`/`link_count` must describe the complete link table; invalid graphs are rejected before writing.

## Collision bounds

WBN files can be loaded directly after extraction from an IMG entry. Composite children, transforms, bounding boxes, decoded vertices, polygon adjacency, material behavior flags, and BVH nodes are exposed with semantic names:

```python
from fourfury import ImgArchive, MaterialCatalog, WbnDocument, WbnMaterialFlags

materials = MaterialCatalog.from_game(game)

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bronx_e_1.wbn")
    if entry is None:
        raise FileNotFoundError("bronx_e_1.wbn")
    bounds = WbnDocument.from_bytes(entry.read(), name=entry.name, materials=materials)

for geometry in bounds.geometries:
    print(len(geometry.vertices), len(geometry.polygons))
    print(geometry.decoded_vertices[0])
    for material in geometry.materials:
        print(material.material_id, material.name, material.definition.friction)
        if material.flags & WbnMaterialFlags.SEE_THROUGH:
            print("see-through collision material", material.material_id)

    for polygon in geometry.polygons:
        physical_material = geometry.material_for_polygon(polygon)
        print(physical_material.name, physical_material.definition.fx_group)

# Existing values can be edited without rebuilding resource pointers.
if bounds.geometries and bounds.geometries[0].materials:
    bounds.geometries[0].materials[0].flags |= WbnMaterialFlags.BLOCK_CLIMB
bounds.save("edited.wbn")
```

The writer preserves the original compressed resource byte-for-byte when nothing changes. It supports edits that keep array counts fixed; adding or removing bounds, vertices, polygons, materials, or BVH nodes requires pointer relocation and is rejected explicitly.

WBD files contain hash-addressed collections of the same collision bounds. Dictionary entries can be found by their numeric hash or by a model name, which is converted with GTA IV's lowercase JOAAT algorithm:

```python
from fourfury import WbdDocument

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bronx_e.wbd")
    if entry is None:
        raise FileNotFoundError("bronx_e.wbd")
    dictionary = WbdDocument.from_bytes(entry.read(), name=entry.name, materials=materials)

for collision in dictionary:
    print(collision.hash_hex, collision.bound.bound_type)

bound = dictionary.find_bound("a_model_name")
print(len(dictionary.bounds), len(dictionary.geometries))
```

WBD writing supports fixed-size changes to entry hashes, parent/usage metadata, and decoded bounds. Adding or removing dictionary entries requires pointer relocation and is rejected.

## Drawable models

WDR resources expose renderable model geometry rather than collision surfaces. Vertex attributes are decoded according to each file's RAGE declaration, including positions, normals, colors, UV sets, skin data, and tangents:

```python
from fourfury import ImgArchive, WdrDocument

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bay_billbrds_02.wdr")
    if entry is None:
        raise FileNotFoundError("bay_billbrds_02.wdr")
    drawable = WdrDocument.from_bytes(entry.read(), name=entry.name)

high_lod = drawable.lods[0]
if high_lod is not None:
    for model in high_lod.models:
        for geometry in model.geometries:
            print(geometry.vertex_count, geometry.face_count)
            print(geometry.vertices[0].position)
            print(geometry.vertices[0].normal)
            print(geometry.vertices[0].texcoords)
            print(geometry.triangles[0])

            # Skinned geometry stores local blend indices that address this palette.
            if model.has_skin:
                print(model.skin_flag, geometry.bone_ids)
                print(geometry.resolve_bone_indices(geometry.vertices[0]))

            if geometry.shader is not None:
                print(geometry.shader.name)
                for parameter in geometry.shader.parameters:
                    if parameter.texture is not None:
                        print(parameter.name, parameter.texture.name)

for texture in drawable.embedded_textures:
    print(texture.name, texture.width, texture.height, texture.format_name)
    texture.save_dds(Path("textures") / f"{texture.name}.dds")

if drawable.drawable.skeleton is not None:
    skeleton = drawable.drawable.skeleton
    for bone in skeleton.bones:
        print(bone.name, bone.flags, bone.parent_index)
        print(bone.absolute_transform.translation)
```

For converters and other tooling, `to_model()` projects a WDR into immutable,
target-independent dataclasses:

```python
model = drawable.to_model()

high = model.get_lod("high")
if high is not None:
    for mesh in high.meshes:
        print(mesh.positions, mesh.indices, mesh.material_index)
        print(mesh.get_texcoords(0), mesh.blend_weights, mesh.bone_palette)

for material in model.materials:
    print(material.shader_name, material.texture_names)
```

The neutral model preserves source LODs, meshes, material hashes and parameters,
embedded texture mip chains, skeleton matrices, and lights. Colors and byte-based
blend weights are normalized to `0.0..1.0`; coordinates and row-major matrices are
not transformed. The model layer has no FiveFury, GTA V, or YDR dependency, so a
separate converter can map it to any target format without coupling FourFury to that
format.

The semantic view exposes all four geometry vertex/index-buffer slots, matrix palettes,
rigid and skinned model bindings, model and per-geometry bounds, complete bone records,
parent indices, joint-scale-orientation matrices, default transforms, bind transforms,
and the known RAGE bone flags. Raw values whose purpose is still unverified are retained
as `reserved` fields instead of being assigned speculative meanings.

The current WDR API is a read-only semantic view. `to_bytes()` and `save()` preserve the original compressed RSC5 resource exactly; editing decoded drawable structures is not serialized yet.

## Texture dictionaries and GTXD parents

Standalone WTD files and drawable-embedded dictionaries use the same texture model. DDS export wraps the original compressed mip data without recompressing it:

```python
from fourfury import GtxdHierarchy, ImgArchive, WtdDocument

hierarchy = GtxdHierarchy.from_game(game)
print(hierarchy.chain("bxe_ind1"))  # ("bxe_ind1", "bronxe_shared")

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bronxe_shared.wtd")
    if entry is None:
        raise FileNotFoundError("bronxe_shared.wtd")
    dictionary = WtdDocument.from_bytes(entry.read(), name=entry.name)
    texture = dictionary.get("qw_rooftex1")
    if texture is not None:
        texture.save_dds("qw_rooftex1.dds")
```

`GtxdDocument` provides a typed, lossless view of `txdp` sections in `gtxd.ide` or regular map IDE files. `GtxdHierarchy.from_game(...)` combines the base-game common and map IDE relationships in the same child-first lookup order used by GTA IV.

## WPL instance flags

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
- WTD structures are currently read-only; decoded texture replacement and dictionary rebuilding are not implemented yet.
- SCO bytecode is not implemented yet.
- WBN/WBD sphere, capsule, and box records currently expose their shared bound metadata but not every type-specific trailing field.
- Some NOD node and link behavior bits have no reliable public definition. They are preserved without speculative names through `unresolved_flags` and `traffic_flags`.
