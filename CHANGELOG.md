# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

## [0.2.0] - 2026-07-24

### Added
- WAD animation-dictionary reading with animation names, hash lookup, flags, track metadata, decoded channels, frame evaluation, and time-based sampling.
- Support for stock raw, static, quantized, compact, and RLE integer WAD channels, while retaining unsupported channel headers for lossless inspection.
- Format-neutral arbitrary animation targets, scalar/vector values, sparse frames, interpolation, selected-track streaming, and primitive-data export.
- Semantic WAD track classification, structured animation and dictionary validation, aggregate audit reports, and explicit reporting for custom track IDs.
- Target-independent UV transforms, frames, clips, interpolation, coordinate transformation, primitive-data export, and material-slot binding metadata.
- Typed IDE archetype views and animation flags, including UV-animation dictionary bindings that do not guess clip names.
- Target-independent skeletal transforms, poses, clips, normalized quaternion interpolation, and separately modeled mover/root-motion tracks.
- Optional skeletal binding by bone ID with hierarchy, names, indices, skeleton signatures, bind-pose matrices, strict validation, and explicit unresolved targets.
- Explicit MLO archetypes with typed entities, rooms, portals, bounds, time flags, cross-references, internal LOD parenting, and topology validation.
- MLO hash registries, WPL placement resolution, world-space entity/room/portal projection, primitive-data export, and lossless editing through IDE records.
- Lossless text IPL support with typed GTA IV occlusion boxes.
- Named layered-terrain shader parameters, drawable-light flags, neutral WDR default UV transforms, and lightweight WBD dictionary-hash inspection.

### Changed
- Reorganized the monolithic WDR parser into the focused `fourfury.wdr` package for constants, math, materials, geometry, scene data, and binary reading.
- Preserved the complete WDR public API, type identities, pickle compatibility, native-decoder patching, and root-package imports across the module reorganization.
- WPL section 8 is now modeled explicitly as `WplMloPortal`; `WplStrBig` remains available as a compatibility alias.
- WAD targets are modeled independently from their per-chunk encodings so converters can consume stable logical animation data.

### Fixed
- WAD track-group sampling respects the shared boundary frame between adjacent groups.
- Stock UV-animation dictionary hashes resolve through their base-name and material-slot convention.
- WAD UV targets are identified explicitly instead of being reported as integer tracks.
- WAD skeletal targets remain stable when their per-chunk encoding changes, and sampled quaternions now use normalized shortest-path interpolation.
- WAD action-flags tracks are no longer misclassified as bone translations.
- WAD packed integer sequences decode their unary prefix before the Rice remainder.

### Performance
- Bounded IMG resource scanning uses roughly 4× less peak memory, caches logical resource sizes, and skips repeated zlib scans.
- Atomic streaming IMG and RPF writers use roughly 200× less peak memory when saving large archives.
- Lazy WAD channel decoding makes large animation dictionaries roughly 40× faster to parse while using about 11× less peak memory.
- Lazy WDR vertex decoding makes large drawables roughly 2.5× faster to parse while retaining about 1.5× less memory.
- Indexed animation, skeleton, texture, and track lookups make repeated UV sampling up to 75× faster and texture lookup roughly 55× faster.

## [0.1.0] - 2026-07-22

### Added
- Initial public release of FourFury for GTA IV asset workflows on Python 3.11 and newer.
- RPF2, audio RPF3, and IMG3 archive reading and extraction, with creation and writing for RPF2 and IMG3.
- IDE, WPL, GTXD, NOD, and WNV map-data APIs, including explicit LOD parenting and format-neutral path graphs.
- RSC5 texture, drawable, fragment, and collision support through WTD, WDR, WDD, WFT, WBN, and WBD.
- Format-neutral model projection, stock shader and collision-material catalogs, and optional native acceleration for common decoding paths.
