# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-08-05

### Changed

- Runtime pins updated to official ZCode desktop app `3.6.5` (build
  `3.6.5.4145`, Linux package `3.6.5-4145`) and embedded CLI `0.16.1`.
- Refreshed all six canonical ZIP, AppImage, and Debian artifact sizes and
  SHA-512 identities from the per-platform official `latest.yml` channels.
- Recorded the CLI's native `--cwd`, `--settings`, and permission-mode surface
  after validating the isolated `doctor` path with the managed config.

## [0.1.2] - 2026-07-30

### Changed

- Runtime pins updated to the official ZCode desktop app `3.5.3` while
  retaining the embedded CLI at `0.15.2`.
- The adoption marker description now names its timestamp format without
  colliding with the unchanged runtime `created_at` key.
- Volatile verification-date evidence is no longer stored in the public
  runtime baseline.

## [0.1.1] - 2026-07-26

### Changed

- Runtime pins updated to the official ZCode desktop app `3.5.2` (build
  `3.5.2.3869`, Linux package `3.5.2-3869`) with the embedded CLI remaining
  `0.15.2`.
- All six native CDN artifacts were re-downloaded and pinned by exact filename,
  byte size, and SHA-512 for the `3.5.2` release.
- macOS identity verification now pins the observed Gatekeeper source per
  architecture: arm64 is `Notarized Developer ID`; x64 is
  `Unnotarized Developer ID`.
- Public baseline now records the official 2026-07-26 `3.5.2` changelog claims:
  built-in web app integration, PDF preview, unified appearance settings,
  Extension Marketplace icon improvements, and large-file reading improvements.

## [0.1.0] - 2026-07-24

Pre-release baseline. Version scheme realigned across the nddev setup modules:
`0.1.0` reflects that the `nddev-builder` tooling — the setup system for
building setups — is ready, while the working setups themselves are not yet
shipped. `1.0.0` is reserved for the first working setups.

### Added

- ZCode setup manager with target-explicit lifecycle and managed
  provider/model configuration.
- Native `nddev-builder` marketplace and core plugin.
- Runtime pinned to the official ZCode desktop app `3.3.6` (bundled CLI
  `0.15.2`, runtime GLM-5.2); every downloadable artifact is pinned by
  filename, byte size, and SHA-512.
