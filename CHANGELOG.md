# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

### Added
- WAD animation dictionary reading with named track metadata, decoded channels, hash lookup, and frame sampling.
- Format-neutral arbitrary WAD tracks, sparse frames, interpolation, and primitive-data export.
- Structured WAD track classification, validation diagnostics, and dictionary audit reports.
- Runtime-compatible WAD RLE integer channel decoding and frame evaluation.
- Lossless inspection and audit reporting for unsupported WAD channel encodings.
- Target-independent UV animation clips, affine transforms, sampling, and primitive-data export.
- Target-independent skeletal poses and clips with explicit mover/root-motion tracks.
- Optional skeletal-animation binding with hierarchy, skeleton signatures, and bind-pose matrices.
- Text IPL support with typed GTA IV occlusion boxes.
- Additional layered-terrain shader metadata, named drawable-light flags, and lightweight WBD hash inspection.
- Typed IDE archetype animation flags and neutral WDR default UV transforms.
- Explicit MLO archetypes, entities, rooms, portals, topology validation, WPL resolution, and world-space projection.

### Fixed
- WAD track-group sampling respects the shared boundary frame between adjacent groups.
- Stock UV-animation dictionary hashes resolve through their base-name and material-slot convention.
- WAD UV targets are identified explicitly instead of being reported as integer tracks.
- WAD skeletal targets remain stable when their per-chunk encoding changes, and sampled quaternions now use normalized shortest-path interpolation.
- WAD action-flags tracks are no longer misclassified as bone translations.
- WAD packed integer sequences decode their unary prefix before the Rice remainder.

## [0.1.0] - 2026-07-22

### Added
- Initial public release of FourFury for GTA IV asset workflows on Python 3.11 and newer.
- RPF2, audio RPF3, and IMG3 archive reading and extraction, with creation and writing for RPF2 and IMG3.
- IDE, WPL, GTXD, NOD, and WNV map-data APIs, including explicit LOD parenting and format-neutral path graphs.
- RSC5 texture, drawable, fragment, and collision support through WTD, WDR, WDD, WFT, WBN, and WBD.
- Format-neutral model projection, stock shader and collision-material catalogs, and optional native acceleration for common decoding paths.
