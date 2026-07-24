# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
