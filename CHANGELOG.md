# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

## [0.2.0] - 2026-07-24

### Added
- WAD animation-dictionary reading with animation names, hash lookup, flags, and track metadata.
- Decoding for stock raw, static, quantized, compact, and RLE integer WAD channels.
- Lossless inspection and audit reporting for unsupported WAD channel encodings.
- Frame evaluation and time-based sampling for decoded WAD animations.
- Format-neutral animation targets, scalar and vector values, sparse frames, and interpolation.
- Selected-track streaming and primitive-data export for format-independent animation consumers.
- Semantic WAD track classification with explicit reporting for custom track IDs.
- Structured WAD animation validation and aggregate dictionary audit reports.
- Target-independent UV transforms, frames, clips, interpolation, and coordinate transformation.
- UV-animation material-slot binding metadata without guessed clip names.
- Typed, editable IDE archetype views.
- Named IDE archetype animation flags.
- Neutral WDR default UV transforms shared with the animation API.
- Target-independent skeletal transforms, poses, and clips.
- Separately modeled mover and root-motion tracks.
- Optional skeletal binding by bone ID with hierarchy, names, indices, skeleton signatures, and bind-pose matrices.
- Strict skeleton validation with explicit unresolved targets in permissive mode.
- Explicit MLO archetypes with typed entities, rooms, portals, bounds, time flags, and cross-references.
- Internal MLO LOD parenting and structured topology validation.
- MLO hash registries and WPL placement resolution.
- World-space projection for MLO entities, room bounds, and portal corners.
- Primitive-data export and lossless MLO editing through the original IDE records.
- Lossless text IPL support with typed GTA IV occlusion boxes.
- Named layered-terrain shader parameters.
- Named drawable-light flags.
- Lightweight WBD dictionary-hash inspection.

### Changed
- Reorganized the monolithic WDR parser into the focused `fourfury.wdr` package for constants, math, materials, geometry, scene data, and binary reading.
- Preserved the complete WDR public API and root-package imports across the module reorganization.
- Preserved WDR type identities, pickle compatibility, and native-decoder patching.
- WPL section 8 is now modeled explicitly as `WplMloPortal`.
- `WplStrBig` remains available as a compatibility alias.
- WAD targets are modeled independently from their per-chunk encodings so converters can consume stable logical animation data.

### Fixed
- WAD track-group sampling respects the shared boundary frame between adjacent groups.
- Stock UV-animation dictionary hashes resolve through their base-name and material-slot convention.
- WAD UV targets are identified explicitly instead of being reported as integer tracks.
- WAD skeletal targets remain stable when their per-chunk encoding changes.
- Sampled skeletal quaternions now use normalized shortest-path interpolation.
- WAD action-flags tracks are no longer misclassified as bone translations.
- WAD packed integer sequences decode their unary prefix before the Rice remainder.

### Performance
- Bounded IMG resource scanning uses roughly 4× less peak memory.
- Cached IMG logical resource sizes avoid repeated zlib scans.
- Atomic streaming IMG and RPF writers use roughly 200× less peak memory when saving large archives.
- Lazy WAD channel decoding makes large animation dictionaries roughly 40× faster to parse while using about 11× less peak memory.
- Lazy WDR vertex decoding makes large drawables roughly 2.5× faster to parse while retaining about 1.5× less memory.
- Indexed animation-frame sampling is up to 75× faster.
- Indexed texture-name lookup is roughly 55× faster.
- Indexed skeleton and track metadata avoid repeated lookup allocations.

## [0.1.0] - 2026-07-22

### Added
- Initial public release of FourFury for GTA IV asset workflows on Python 3.11 and newer.
- RPF2, audio RPF3, and IMG3 archive reading and extraction, with creation and writing for RPF2 and IMG3.
- IDE, WPL, GTXD, NOD, and WNV map-data APIs, including explicit LOD parenting and format-neutral path graphs.
- RSC5 texture, drawable, fragment, and collision support through WTD, WDR, WDD, WFT, WBN, and WBD.
- Format-neutral model projection, stock shader and collision-material catalogs, and optional native acceleration for common decoding paths.
