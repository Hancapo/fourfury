# Changelog

All notable changes to `fourfury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

### Added
- WAD animation dictionary reading with named track metadata, decoded channels, hash lookup, and frame sampling.
- Target-independent UV animation clips, affine transforms, sampling, and primitive-data export.
- Target-independent skeletal poses and clips with explicit mover/root-motion tracks.
- Text IPL support with typed GTA IV occlusion boxes.
- Additional layered-terrain shader metadata, named drawable-light flags, and lightweight WBD hash inspection.
- Typed IDE archetype animation flags and neutral WDR default UV transforms.

### Fixed
- WAD UV targets are identified explicitly instead of being reported as integer tracks.
- WAD skeletal targets remain stable when their per-chunk encoding changes, and sampled quaternions now use normalized shortest-path interpolation.
- WAD action-flags tracks are no longer misclassified as bone translations.

## [0.1.0] - 2026-07-22

### Added
- Initial public release of FourFury for GTA IV asset workflows on Python 3.11 and newer.
- RPF2, audio RPF3, and IMG3 archive reading and extraction, with creation and writing for RPF2 and IMG3.
- IDE, WPL, GTXD, NOD, and WNV map-data APIs, including explicit LOD parenting and format-neutral path graphs.
- RSC5 texture, drawable, fragment, and collision support through WTD, WDR, WDD, WFT, WBN, and WBD.
- Format-neutral model projection, stock shader and collision-material catalogs, and optional native acceleration for common decoding paths.
