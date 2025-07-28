# Changelog

All notable changes to this collection will be documented in this file.

## [1.1.6] – 2025-07.28
### Fixed
- `vrp_config`: Added custom undo logic for `arp anti-attack check user-bind enable`

## [1.1.5] – 2025-07-10
### Fixed
- `vrp_vlan`, `vrp_ntp`, `vrp_stp_global`, `vrp_system`, `vrp_config`, `vrp_user`: Added `--diff` support with consistent use of `diff_and_wrap()` and `check_mode` handling.

## [1.1.4] – 2025-07-10
### Fixed
- `vrp_ntp`: Fixed invalid `undo clock timezone` command when using `state: absent` (no more syntax error).
- `vrp_ntp`: DST configuration is now only applied when all `dst_*` parameters are explicitly set.
- `vrp_common.diff_and_wrap`: Added special handling for `undo clock timezone` to ensure correct command generation.

## [1.1.3] – 2025-07-07
### Fixed
- README: correct tests link

## [1.1.2] – 2025-07-07
### Fixed
- README: license badge now shows GPL-3.0

## [1.1.1] – 2025-07.07
### Added
- Initial release on Ansible Galaxy.
- Modules: `vrp_command`, `vrp_config`, `vrp_backup`, `vrp_vlan`, `vrp_interface`, `vrp_user`, `vrp_ntp`, `vrp_system`, `vrp_stp_global`.
- CLI plugins: `cliconf`, `connection`, `terminal`.

## [1.0.0] – internal use
- First working version (unpublished).
