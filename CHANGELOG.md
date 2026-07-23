# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

## [0.1.0] - 2026-07-22

### Added
- Initial public release of FourFury for Python 3.11 and newer.
- RPF2 archive reading, extraction, creation, and unencrypted writing, plus read-only audio RPF3 support.
- IMG3 archive reading, extraction, creation, writing, encrypted index handling, and RSC5 padding removal.
- Automatic stock-archive decryption through the embedded, SHA-1-verified GTA IV AES key.
- Lossless IDE definition-file parsing and editing, including comments, formatting, MLO tokens, and GTXD parent texture relationships.
- Typed WPL placement reading and writing with explicit local and streamed LOD hierarchies, flags, garages, parked cars, culls, zones, and blocks.
- RSC5 resource allocation, pointer, compression, and texture-dictionary foundations shared by the resource formats.
- WTD texture dictionaries with embedded payload access, mip metadata, DDS export, and binary-stream loading.
- WDR drawable reading with LODs, models, geometry, vertex declarations, shaders, embedded textures, skeletons, lights, and format-neutral model projection.
- A typed Complete Edition shader catalog covering all 134 SPS presets, 71 compiled programs, draw buckets, scalar defaults, and 66 known WDR parameter names.
- WDD drawable dictionaries with hash and JOAAT lookup plus format-neutral model projection.
- WFT fragment models with reusable drawables, physics groups and children, damping, inertia, archetypes, events, and embedded collision bounds.
- WBN collision bounds and WBD collision dictionaries with composites, primitive bounds, quantized geometry, polygons, materials, BVH trees, and fixed-size editing.
- Built-in names and byte IDs for all 156 stock collision materials, without requiring `materials.dat`.
- WNV navigation meshes with decoded geometry, polygon and edge flags, cover points, adjacency, quadtrees, traversal, and fixed-size editing.
- NOD vehicle and pedestrian navigation graphs with semantic flags, directed links, editing, validation, and format-neutral path-graph export.
- Shared format-neutral model and path APIs intended for conversion tools without coupling FourFury to a specific target game or DCC application.

### Performance
- Optional CPython stable-ABI C++ acceleration for GTA IV AES decryption, WDR vertex decoding, and WBN geometry decoding.
- Lazy WDR vertex materialization and reduced archive indexing, copying, and repeated traversal in common read paths.
