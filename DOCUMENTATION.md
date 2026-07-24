# FourFury documentation

This guide describes FourFury's archive, map, collision, drawable, texture,
animation, and navigation APIs. Start with the [public README](README.md) for
installation and a short overview.

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
- [Water surfaces](#water-surfaces)
- [Navigation paths](#navigation-paths)
- [Collision bounds](#collision-bounds)
- [Animation dictionaries](#animation-dictionaries)
- [Drawable models](#drawable-models)
- [Fragment models](#fragment-models)
- [Texture dictionaries and GTXD parents](#texture-dictionaries-and-gtxd-parents)
- [WPL instance flags](#wpl-instance-flags)
- [Current limitations](#current-limitations)

## Supported formats

- RPF2: reading, searching, extraction, creation, and writing.
- Audio RPF3: reading and extraction. Names stored only as hashes are represented in hexadecimal.
- IMG3: reading, searching, extraction, creation, and writing.
- IPL: lossless sectioned text with typed `OCCL` occlusion boxes.
- `water.dat`: lossless typed triangles and quads with runtime flags, spatial queries, validation, editing, and neutral mesh export.
- WPL: typed reading and writing for instances, garages, parked cars, culls, MLO world portals, LOD culls, zones, and blocks.
- IDE: lossless definitions with typed archetypes and complete nested MLO entities, rooms, portals, and topology validation.
- GTXD/`txdp`: typed child-to-parent texture dictionary hierarchies, lossless editing, chain resolution, and cycle detection.
- NOD: typed vehicle and pedestrian navigation graphs with fixed-point positions, directed links, path costs, behavior-flag confidence metadata, and lossless editing.
- WNV: typed RSC5 navigation meshes with quantized vertices, polygon flags, adjacency edges, cover points, and quadtrees, with lossless fixed-size editing.
- WBD: typed RSC5 collision dictionaries with JOAAT lookup, shared bounds, built-in material names, and lossless fixed-size editing.
- WBN: typed RSC5 collision bounds, composites, quantized geometry, built-in physical-material names, polygons, and BVH trees, with lossless fixed-size editing.
- WAD: typed RSC5 animation dictionaries with JOAAT lookup, named track and bone metadata, track groups, chunks, decoded static/raw/quantized channels, and frame sampling.
- WDD: typed hash-addressed RSC5 drawable dictionaries with JOAAT lookup and neutral model projection.
- WDR: typed RSC5 drawables with LODs, models, decoded vertex declarations, vertex and index buffers, shaders, embedded textures, skeletons, and lights.
- WFT: typed RSC5 fragment models with reusable WDR drawables, physical groups and children, named flags, damping, inertia, archetypes, and embedded WBN collision bounds.
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
from fourfury import IdeDocument, IplDocument, WplDocument

ide = IdeDocument.from_path(game / "pc/data/maps/manhat/manhat01.ide")
for entry in ide.iter_entries("objs"):
    print(entry.values[0])

for archetype in ide.uv_animated_archetypes:
    print(archetype.name, archetype.uv_animation_dictionary)

wpl = WplDocument.from_path(game / "pc/data/maps/manhat/manhat01.wpl")
for instance in wpl.instances:
    print(hex(instance.model_hash), instance.flags, instance.lod_index, instance.lod_distance)

ipl = IplDocument.from_path(game / "common/data/maps/occlu.ipl")
for occluder in ipl.occluders:
    print(occluder.center, occluder.size, occluder.rotation)

hierarchy = wpl.build_lod_hierarchy(strict=True)
for root in hierarchy.roots:
    print("root", root.index, "descendants", len(tuple(root.iter_descendants())))

# Both formats can be edited and written back.
ide.add_entry("objs", ["example", "example", "100", "0"])
ide.save("example.ide")
wpl.save("example.wpl")
```

The WPL writer preserves trailing bytes such as the sector padding found in some stock files. The IDE writer preserves original lines byte-for-byte until their parsed values are modified.

`IdeDocument.archetypes` provides typed, editable views for `objs`, `tobj`,
`anim`, and `tanm`. `IdeArchetypeFlags.HAS_UV_ANIMATION` names bit 10 explicitly;
`uv_animated_archetypes` and `uv_animation_dictionary` expose the external
dictionary binding without guessing a clip name. WDR shader parameters
`global_animation_uv_0` and `global_animation_uv_1` are available together as
`WdrShader.uv_transform`, using the same neutral `UvTransform` returned by WAD
animation sampling.

### MLO interiors

IDE `mlo` sections are parsed as complete `MloArchetype` objects instead of
being exposed only as unrelated CSV rows. Each archetype contains local
`MloEntity`, `MloRoom`, and `MloPortal` records, declared counts, draw
distances, room bounds, time-cycle hashes, room/entity membership, portal
corners, and the room graph:

```python
from fourfury import IdeDocument, MloRegistry, WplDocument

interiors = IdeDocument.from_path("bars_1.ide")
for archetype in interiors.mlo_archetypes:
    print(archetype.name, len(archetype.rooms), len(archetype.portals))
    print("LOD parents", archetype.lod_parent_indices)
    for room in archetype.rooms:
        print(room.name, room.entity_ids)
    for issue in archetype.validate():
        print(issue.code, issue.message)

registry = MloRegistry.from_ide_documents((interiors,))
wpl = WplDocument.from_path("bars_1.wpl")
for instance in wpl.resolve_mlos(registry):
    print(instance.archetype.name, instance.position)
    print(instance.entities[0].position)  # world coordinates
    print(instance.rooms[0].corners)
    print(instance.portals[0].corners)
```

MLO entities and topology remain in archetype-local coordinates. A resolved
`MloInstance` applies the serialized WPL placement quaternion and translation
to entities, all eight room-bound corners, and all four portal corners.
Internal entity LOD parents follow the MLO level-0 → level-1 → level-2
relationship explicitly and are included in `to_data()` output.

`MloRegistry` uses lowercase JOAAT names to match normal WPL section-0
placements. When several loaded IDE files define the same hash, later
documents take precedence and `duplicate_hashes` keeps the collision visible.
WPL section 8 is exposed separately as `WplMloPortal`; the old `WplStrBig`
name remains a compatibility alias.

The typed MLO records wrap the original `IdeEntry` objects. Editing their
names, vectors, flags, bounds, counts, or scalar parameters therefore writes
back through the normal lossless IDE writer. The current convenience API does
not add or remove nested MLO records.

### WPL LOD parenting

`lod_index` has two different scopes in GTA IV. A standalone parent WPL resolves
the index against its own instance table. A streamed WPL stored inside an IMG
resolves it against the parent WPL named after that archive: for example,
`manhat01_6.wpl` inside `manhat01.img` references instances in `manhat01.wpl`.
Pass that document explicitly so the scope cannot be mistaken:

```python
from fourfury import WplDocument, WplLodParentScope

parent = WplDocument.from_path("manhat01.wpl")
stream = WplDocument.from_bytes(stream_entry.read(), name=stream_entry.name)
hierarchy = stream.build_lod_hierarchy(parent=parent, strict=True)

node = hierarchy.node_at(0)  # index 0 in the streamed document
if node.parent is not None:
    assert node.parent_scope is WplLodParentScope.EXTERNAL
    print(node.parent.document.name, node.parent.index)
    print("depth", node.depth, "children", len(node.children))
```

The hierarchy is a detached snapshot over mutable WPL records. It
exposes `nodes`, validated `edges`, resolved `roots`, `parent`, `children`,
`depth`, `ancestors`, and `iter_descendants()`. Build it again after changing an
instance list or `lod_index`. With `strict=False` (the default), malformed links
are retained as structured `issues` and affected nodes report
`has_unresolved_parent`; `strict=True` raises `WplLodHierarchyError`. Neither
mode changes the raw indices or the bytes written by `WplDocument`.

## Water surfaces

`WaterDocument` reads GTA IV's text `common/data/water.dat` without changing
comments, directives, whitespace, numeric spelling, or line endings. The game
uses 30-value quads and also accepts a legacy 22-value triangle form:

```python
from fourfury import WaterDocument, WaterSurfaceFlags

water = WaterDocument.from_path(game / "common/data/water.dat")
for surface in water:
    print(surface.shape, surface.bounds, surface.height)
    print(surface.is_visible, surface.is_rendered, surface.is_dynamic)
    if surface.contains_xy(100.0, -250.0):
        print("height", surface.height_at(100.0, -250.0))

dynamic = [
    surface
    for surface in water
    if surface.flags & WaterSurfaceFlags.DYNAMIC
]
mesh = water.to_mesh_data(visible_only=True)
water.save("water.dat")
```

Quads retain the engine's triangle-strip order as `(0, 1, 2)` and
`(2, 1, 3)`. `to_mesh_data()` returns primitive positions, triangle indices,
and their source-surface indices without depending on a renderer or target
game. `surfaces_at()` and `height_at()` provide XY point queries, while
`validate()` reports non-finite values, degenerate geometry, and flag bits not
yet named by FourFury.

`WaterSurfaceFlags.VISIBLE`, `RENDER`, and `DYNAMIC` name the bits used by the
GTA IV runtime loader. Unknown bits are preserved and exposed through
`unresolved_flags`. The four values following each vertex position remain
available as `WaterVertex.legacy_values`; GTA IV reads them but does not use
them when constructing the runtime surfaces. Quads additionally expose their
serialized dynamic-water value as `wave_scale`, while legacy triangles do not
store it.

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

For converters, visualization, and graph analysis, NOD sectors can be projected into
immutable data that does not expose the binary NOD layout:

```python
from fourfury import combine_nod_graphs, load_nod_graph

graph = load_nod_graph("nodes32.nod")
for node in graph.nodes:
    print(node.id, node.position, node.kind, node.width, node.traits)
for edge in graph.edges:
    print(edge.source, edge.target, edge.length, edge.cost)

# Parsed sectors can be joined without changing their original identifiers.
city = combine_nod_graphs(sector_documents, name="liberty-city")
print(city.unresolved_targets)
city.save_json("liberty-city-paths.json")
```

`NodDocument.iter_path_nodes()` and `iter_path_edges()` provide the same projection
without allocating a complete graph snapshot. `include_source_metadata=True` retains
NOD-only scalar values such as packed flags, compiler metadata, and traffic flags;
the default output contains only portable navigation data. Cross-sector destinations
remain valid node identifiers even when their sector has not been loaded.

WNV files in `pc/data/cdimages/navmeshes.img` contain the polygon meshes used for
local navigation and cover queries:

```python
from fourfury import ImgArchive, WnvDocument, WnvEdgeFlags, WnvPolygonFlags

with ImgArchive.from_path(game / "pc/data/cdimages/navmeshes.img") as archive:
    entry = archive.find_entry("sectors2x2_60_94.wnv")
    if entry is None:
        raise FileNotFoundError("sectors2x2_60_94.wnv")
    navmesh = WnvDocument.from_bytes(entry.read(), name=entry.name)

for polygon in navmesh.polygons:
    print(polygon.area_id, polygon.flags, navmesh.polygon_vertex_indices(polygon))
    if polygon.flags & WnvPolygonFlags.PAVEMENT:
        print("pavement", navmesh.polygon_vertices(polygon))

for edge in navmesh.edges:
    if edge.flags & WnvEdgeFlags.EXTERNAL_EDGE:
        print("external adjacency", edge.area_id_1, edge.polygon_id_1)

for node in navmesh.iter_quadtree():
    if node.data is not None:
        print(node.data.polygon_ids, node.data.cover_points)
```

Vertices are available both in their original unsigned 16-bit representation and
as world-space values through `decoded_vertices`. Named flags cover behavior supported
by source evidence; other bits remain preserved by the `IntFlag` values and are exposed
separately through `edge.unresolved_flags` and `polygon.unresolved_flags`. The writer
supports edits that keep array counts and quadtree topology fixed.

## Collision bounds

WBN files can be loaded directly after extraction from an IMG entry. Composite children, transforms, bounding boxes, decoded vertices, polygon adjacency, material behavior flags, and BVH nodes are exposed with semantic names:

```python
from fourfury import ImgArchive, WbnDocument, WbnMaterialFlags, WbnMaterialType

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bronx_e_1.wbn")
    if entry is None:
        raise FileNotFoundError("bronx_e_1.wbn")
    bounds = WbnDocument.from_bytes(entry.read(), name=entry.name)

for geometry in bounds.geometries:
    print(len(geometry.vertices), len(geometry.polygons))
    print(geometry.decoded_vertices[0])
    for material in geometry.materials:
        print(material.material_id, material.material_type, material.name)
        if material.flags & WbnMaterialFlags.SEE_THROUGH:
            print("see-through collision material", material.material_id)

    for polygon in geometry.polygons:
        physical_material = geometry.material_for_polygon(polygon)
        print(physical_material.name)

# Existing values can be edited without rebuilding resource pointers.
if bounds.geometries and bounds.geometries[0].materials:
    material = bounds.geometries[0].materials[0]
    material.material_type = WbnMaterialType.ROCK
    material.flags |= WbnMaterialFlags.BLOCK_CLIMB
bounds.save("edited.wbn")
```

`WbnMaterialType` embeds the 156 stock material names and their binary IDs, so
collision loading does not require `materials.dat`. `material_type` is `None` only
for an out-of-range or modded ID; the original numeric `material_id` is still
preserved and writable.

The writer preserves the original compressed resource byte-for-byte when nothing changes. It supports edits that keep array counts fixed; adding or removing bounds, vertices, polygons, materials, or BVH nodes requires pointer relocation and is rejected explicitly.

WBD files contain hash-addressed collections of the same collision bounds. Dictionary entries can be found by their numeric hash or by a model name, which is converted with GTA IV's lowercase JOAAT algorithm:

```python
from fourfury import WbdDocument

with ImgArchive.from_path(game / "pc/data/maps/east/bronx_e.img") as archive:
    entry = archive.find_entry("bronx_e.wbd")
    if entry is None:
        raise FileNotFoundError("bronx_e.wbd")
    dictionary = WbdDocument.from_bytes(entry.read(), name=entry.name)

for collision in dictionary:
    print(collision.hash_hex, collision.bound.bound_type)

bound = dictionary.find_bound("a_model_name")
print(len(dictionary.bounds), len(dictionary.geometries))
```

WBD writing supports fixed-size changes to entry hashes, parent/usage metadata, and decoded bounds. Adding or removing dictionary entries requires pointer relocation and is rejected.

## Animation dictionaries

GTA IV stores WAD animation dictionaries as RSC5 resources in
`pc/anim/anim.img`. Pass the extracted IMG entry bytes directly to `load_wad`:

```python
from fourfury import ImgArchive, WadTrackId, load_wad

archive = ImgArchive.from_path(game / "pc/anim/anim.img")
entry = archive.find_entry("amb@arcade.wad")
if entry is None:
    raise FileNotFoundError("amb@arcade.wad")

wad = load_wad(entry.read())
animation = wad.find_animation("play_pinball")
if animation is None:
    raise KeyError("play_pinball")

print(animation.name, animation.frame_count, animation.frame_rate)
for identifier in animation.bone_ids:
    print(identifier.track_name, identifier.bone_name, identifier.type_name)

pelvis_translation = animation.sample(
    0.5,
    bone_id=417,
    track_id=WadTrackId.BONE_TRANSLATION,
)
```

`WadDocument` pairs each dictionary hash with a `WadAnimation`. Lookup accepts a
JOAAT integer, a short animation name, or a `pack:/name.anim` reference.
Animations expose the serialized track groups, per-bone chunks, channel flags,
duration, signature, and project flags. `WadBoneId.track_name` handles the
action-flags bit explicitly, while `bone_name` resolves the stock character,
facial, and vehicle IDs known to GTA IV.

`WadAnimation.targets` is the complete logical target set across all serialized
chunk groups. Unlike the compatibility `bone_ids` property, it is not limited
to the first group. `evaluate_tracks(frame)` and `sample_tracks(time)` return
values keyed by `(target_id, track_id)` and preserve scalar integers instead of
coercing every channel to a four-component float vector. Use `track_ids=` to
select only the tracks needed by a converter:

```python
values = animation.sample_tracks(
    0.5,
    track_ids=(WadTrackId.BONE_TRANSLATION, WadTrackId.BONE_ROTATION),
)
```

`iter_frames()` streams format-neutral `AnimationTrackFrame` objects.
`to_track_animation()` returns a `TrackAnimationClip` with explicit targets and
step, linear, or quaternion interpolation. Both the WAD animation and neutral
clip provide `to_data()` for consumers that only accept primitive Python data.

`WadAnimation.kinds` classifies known tracks into stable semantic families:
skeletal, material, morph, camera, light, generic, action, and custom. The
corresponding `has_*_tracks` properties support simple filtering without
requiring consumers to duplicate numeric track tables. Unclassified numeric
IDs remain `custom`; FourFury does not assign speculative names to them.

`validate()` returns structured `WadValidationIssue` objects instead of raising
for semantic inconsistencies. Passing a `ModelSkeleton` additionally checks its
signature and animated bone coverage. `WadDocument.audit()` produces aggregate
animation, group, target, track-kind, track-ID, and channel-type counts together
with all validation issues:

```python
report = wad.audit()
print(report.is_valid, report.custom_track_ids)
portable_report = report.to_data()
```

Adjacent serialized track groups overlap by one sample. `frames_per_group` is
the decoded group capacity and `frame_group_stride` is the distance to the next
group; frame evaluation accounts for that overlap, including the final sample.

UV targets use the RAGE `TypeId == 0xFF` sentinel. `WadBoneId.is_uv_channel`,
`uv_index`, and `type_name` expose that identity without misclassifying it as an
integer track. `bind_uv(index)` can retarget an existing track using the same
representation used by the runtime. Animations named with the established
`name_uv_<material-index>` convention expose `is_uv_animation`,
`uv_material_index`, and `uv_base_name`.
Their stock dictionary key is `JOAAT(base_name) + material_index + 1`;
`wad_animation_hash()` and normal `WadDocument` lookup handle this convention
while retaining compatibility with dictionaries hashed from the complete name.

Skeletal targets use `WadBoneId.target_key` to identify the logical
`(bone_id, track_id)` independently from the channel encoding stored in each
chunk group. `is_bone_transform`, `is_mover_transform`, and
`is_skeletal_transform` separate ordinary bone transforms from root-motion
tracks. `WadAnimation.skeletal_tracks` returns the stable target set, while
`sample()` normalizes quaternion tracks and interpolates them over the shortest
path.

`skeletal_pose_at()` and `sample_skeletal()` evaluate all transform tracks as a
single `SkeletalPose`. Each `SkeletalBonePose` keeps its ordinary local transform
and `mover_transform` separate, so root motion is never applied implicitly.
`to_skeletal_animation()` returns a format-neutral `SkeletalAnimationClip` with
ordered frames, time sampling, the WAD skeleton signature, and primitive-data
export:

```python
clip = wad["walk"].animation.to_skeletal_animation()
pose = clip.sample(0.5)
pelvis = pose.get_bone(417)
converter_data = clip.to_data()
```

Binding is optional. Passing a neutral `ModelSkeleton`, or calling
`skeleton.bind_animation(clip)`, adds a `SkeletalBoneTarget` for every animated
bone with its name, skeleton index, parent index, local/world transform, and
inverse bind matrix. Strict binding rejects signature mismatches and missing
bones; `strict=False` preserves unresolved targets explicitly:

```python
model = WdrDocument.from_path("player.wdr").to_model()
clip = wad["walk"].animation.to_skeletal_animation(skeleton=model.skeleton)
child = clip.get_target(417)
```

`to_uv_animation()` projects the two `SHADER_SLIDE_U` and `SHADER_SLIDE_V`
matrix-row tracks into a format-neutral `UvAnimationClip`. The result contains
ordered `UvAnimationFrame` objects, supports interpolation through `sample()`,
can transform coordinates with `UvTransform.apply()`, and exports only primitive
data through `to_data()`:

```python
uv_clip = wad["television_uv_2"].animation.to_uv_animation()
transform = uv_clip.sample(0.5)
animated_uv = transform.apply((0.25, 0.75))
converter_data = uv_clip.to_data()
```

This follows the OAD exporter layout: UV row 0 is `(1, 0, u_offset, 0)` and UV
row 1 is `(0, 1, v_offset, 0)`. Missing individual rows use their identity
value, while animations with neither row are rejected explicitly.

Static float, integer, vector, and quaternion channels are decoded. Raw float
and integer arrays and packed quantized floats are also materialized, so
`vector_at()` and `sample()` can evaluate normal transform tracks without a game
runtime. RLE integer channels expose their distinct `run_values` and decoded
`run_lengths`; `value_at(frame)` evaluates them with the same run-boundary
behavior as the GTA IV runtime. The original packed words, bit count, and Rice
divisor remain available for low-level inspection.

Known but undecoded channel encodings, and channel type bytes unknown to this
version of FourFury, no longer prevent the containing WAD from loading.
`channel_type_value`, `channel_type_name`, `is_supported`, and `header_bytes`
preserve inspectable metadata. Evaluation still raises `NotImplementedError`
explicitly, while `WadDocument.audit()` lists unsupported channel names and
emits structured warnings. The original resource remains lossless.

The WAD API is a read-only semantic view. `to_bytes()` and `save()` preserve the
original compressed RSC5 resource exactly.

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

for shader in drawable.shaders:
    print(shader.program, shader.preset, shader.file_name)
    print(shader.definition.defaults if shader.definition is not None else ())
    texture_sampler = shader.get_parameter("texture_sampler")
    print(texture_sampler.texture if texture_sampler is not None else None)

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

`WdrShaderProgram` enumerates the 71 compiled programs shipped by Complete Edition,
while `WdrShaderPreset` enumerates all 134 SPS material presets. This distinction is
intentional: presets such as `gta_alpha.sps` select `gta_default` and override scalar
defaults. `WdrShader.definition` exposes that relationship; values in
`definition.defaults` come from the SPS database and remain separate from the
parameters actually serialized in `shader.parameters`. Unknown programs, presets,
and parameter hashes remain readable and are reported through `unknown_shaders`,
`unknown_parameters`, and the existing `hash_XXXXXXXX` names.

The semantic view exposes all four geometry vertex/index-buffer slots, matrix palettes,
rigid and skinned model bindings, model and per-geometry bounds, complete bone records,
parent indices, joint-scale-orientation matrices, default transforms, bind transforms,
and the known RAGE bone flags. Raw values whose purpose is still unverified are retained
as `reserved` fields instead of being assigned speculative meanings.

The current WDR API is a read-only semantic view. `to_bytes()` and `save()` preserve the original compressed RSC5 resource exactly; editing decoded drawable structures is not serialized yet.

WDD files store several of the same drawables behind JOAAT hashes. Entries can be
looked up with a model name, raw bytes, or the serialized hash:

```python
from fourfury import WddDocument

dictionary = WddDocument.from_path(game / "pc/models/plantsmgr.wdd")
print(dictionary.parent_dictionary_hash, dictionary.usage_count)

for entry in dictionary:
    print(entry.hash_hex, len(entry.drawable.geometries), len(entry.shaders))
    for texture in entry.embedded_textures:
        print(texture.name)

plant = dictionary.find_drawable("some_plant_model")
if plant is not None:
    print(plant.bounding_box_minimum, plant.bounding_box_maximum)

# Integer hashes use their hexadecimal form as the neutral model name.
model = dictionary.to_model(dictionary.entries[0].name_hash)
```

`to_models()` projects every entry using its hexadecimal hash as the fallback name.
The WDD API is read-only and preserves the complete original RSC5 resource through
`to_bytes()` and `save()`.

## Fragment models

WFT resources combine drawable data with a breakable physics hierarchy. The drawable
parser is shared with WDR, and collision bounds use the same objects as WBN:

```python
from fourfury import ImgArchive, WftDocument, WftFragmentFlags

with ImgArchive.from_path(game / "pc/models/cdimages/vehicles.img") as archive:
    entry = archive.find_entry("admiral.wft")
    if entry is None:
        raise FileNotFoundError("admiral.wft")
    fragment = WftDocument.from_bytes(entry.read(), name=entry.name)

print(fragment.fragment.tune_name, fragment.fragment.bounding_sphere)
print(fragment.fragment.archetype.mass)

for group in fragment.groups:
    print(group.name, group.mass, group.damage_health, group.flags)
    for child in group.children:
        print(child.bone_index, child.undamaged_mass, child.damaged_mass)
        print(child.bone_attachment, child.link_attachment)

if fragment.fragment.flags & WftFragmentFlags.HAS_ARTICULATED_PARTS:
    print("articulated fragment")

for drawable in fragment.iter_drawables():
    print(drawable.name, len(drawable.geometries), drawable.bound)

# The common drawable uses the same target-independent contract as WDR.
model = fragment.to_model()
```

Child drawables are decoded on first access. Reading fragment groups, masses,
inertia, and attachment matrices therefore does not materialize every drawable
and collision bound. `undamaged_drawable_pointer` and
`damaged_drawable_pointer` remain available without triggering that work;
accessing either drawable property or iterating `iter_drawables()` resolves and
caches the corresponding object.

`WftFragmentFlags`, `WftGroupFlags`, and `WftChildFlags` preserve the named RAGE
meanings without presenting later-engine equivalences as proven GTA IV behavior.
Each fragment, group, and child exposes `flag_info` entries with `verified`,
`inferred`, or `unresolved` confidence, plus `unresolved_flags` for unnamed bits.
The standalone `explain_fragment_flags()`, `explain_group_flags()`, and
`explain_child_flags()` helpers provide the same structured descriptions.
`WftDampingKind` addresses all six damping vectors by their linear/angular and
constant/velocity behavior. Child event references are named by collision,
break, and break-from-root role while their opaque event payloads remain pointer
values.

The WFT semantic view is read-only. `to_bytes()` and `save()` preserve the complete
original RSC5 resource, including fields that are not part of the public semantic
model.

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

print(instance.lod_index)     # -1 means no parent; resolve non-negative values through a hierarchy
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
- WAD structures are currently read-only, and RLE integer timing expansion is not modeled yet.
- WDD structures are currently read-only; dictionary and drawable edits are not serialized yet.
- WFT structures are currently read-only; drawable, hierarchy, and physics edits are not serialized yet.
- SCO bytecode is not implemented yet.
- WBN/WBD sphere, capsule, and box records currently expose their shared bound metadata but not every type-specific trailing field.
- Some NOD node and link behavior bits have no reliable public definition. They are preserved without speculative names through `unresolved_flags` and `traffic_flags`.
- WNV writing preserves fixed-size edits but does not rebuild vertex, polygon, edge, or quadtree topology.
