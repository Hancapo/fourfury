# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

### Added
- Lossless GTA IV `water.dat` support with typed triangle and quad surfaces, runtime flags, spatial queries, validation, editing, and format-neutral mesh export.

### Changed
- WFT fragment, group, and child flags now expose confidence metadata and preserve unnamed bits explicitly instead of presenting later-RAGE meanings as verified GTA IV behavior.

## [0.2.0] - 2026-07-24

### Added
- WAD animation-dictionary reading with animation names, hash lookup, flags, and track metadata.
- Decoding for stock WAD channel encodings, with lossless inspection of unsupported encodings.
- Frame evaluation, time-based sampling, and format-neutral targets, values, sparse frames, and interpolation.
- Selected-track streaming and primitive-data export for format-independent animation consumers.
- Semantic WAD track classification, structured validation, aggregate audits, and explicit custom track IDs.
- Target-independent UV transforms, frames, clips, interpolation, and coordinate transformation.
- UV-animation material-slot bindings and neutral WDR default UV transforms shared with the animation API.
- Typed, editable IDE archetype views with named animation flags.
- Target-independent skeletal transforms, poses, clips, and separately modeled mover/root-motion tracks.
- Optional skeletal binding with hierarchy, skeleton signatures, bind-pose matrices, strict validation, and explicit unresolved targets.
- Explicit MLO archetypes with typed entities, rooms, portals, bounds, time flags, cross-references, internal LOD parenting, and topology validation.
- MLO hash registries, WPL placement resolution, and world-space entity, room, and portal projection.
- Primitive-data export and lossless MLO editing through the original IDE records.
- Lossless text IPL support with typed GTA IV occlusion boxes.
- Named layered-terrain shader parameters and drawable-light flags.
- Lightweight WBD dictionary-hash inspection.

### Changed
- Reorganized the monolithic WDR parser into the focused `fourfury.wdr` package while preserving its public API, type identities, pickle compatibility, and native-decoder patching.
- WPL section 8 is now modeled explicitly as `WplMloPortal`, with `WplStrBig` retained as a compatibility alias.
- WAD targets are modeled independently from their per-chunk encodings so converters can consume stable logical animation data.

### Fixed
- WAD track-group sampling respects the shared boundary frame between adjacent groups.
- Stock UV-animation hashes and targets now follow their dictionary, material-slot, and UV-index conventions.
- WAD skeletal targets remain stable across encoding changes, with normalized shortest-path quaternion interpolation.
- WAD action-flags tracks are no longer misclassified as bone translations.
- WAD packed integer sequences decode their unary prefix before the Rice remainder.

### Performance
- Bounded IMG resource scanning uses roughly 4× less peak memory, while cached logical sizes avoid repeated zlib scans.
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
