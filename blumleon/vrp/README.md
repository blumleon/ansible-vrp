# blumleon.vrp – Ansible Collection for Huawei VRP Switches
[![Ansible Galaxy](https://img.shields.io/badge/galaxy-blumleon.vrp-blue.svg)](https://galaxy.ansible.com/blumleon/vrp)
[![license](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)

> Manage Huawei VRP devices idempotently and reliably using native Ansible modules.

---

## Table of Contents

1. [Features](#features)  
2. [Supported Platforms & Requirements](#supported-platforms--requirements)  
3. [Installation](#installation)  
4. [Quick Start](#quick-start)  
5. [Included Plugins & Modules](#included-plugins--modules)  
6. [Examples](#examples)  
7. [Contributing](#contributing)  
8. [License](#license)  
9. [Author](#author)  

---

## Features

- Clean CLI abstraction via `network_cli`
- Native modules for VLAN, Interface, NTP, User, DNS, Config Backup
- Idempotent logic & check-mode support  (except `vrp_user`: check-mode supported, idempotency limited)
- Built-in `cliconf` and `terminal` plugin

## Supported Platforms & Requirements

| Category             | Version / Notes                                                                  |
|----------------------|----------------------------------------------------------------------------------|
| **Ansible**          | 2.14+ or newer (tested with 2.17.9)                                              |
| **Python**           | 3.8+ (tested with 3.10.12)                                                       |
| **VRP OS**           | Tested on VRP V600R022SPH121 (YunShan OS 1.22.0.1) – CloudEngine S5732-H-V2      |
| **Collection deps**  | `ansible.netcommon >= 2.5.0` (tested with 6.1.3)                                 |

This collection was built and tested using a Huawei CloudEngine S5732-H-V2 switch.  
It may work on other VRP-based devices, but support is untested.

## Installation

```bash
# From Ansible Galaxy
ansible-galaxy collection install blumleon.vrp

# Or build & install locally
ansible-galaxy collection build .
ansible-galaxy collection install blumleon-vrp-*.tar.gz
```

## Quick Start

```yaml
- hosts: switches
  gather_facts: no
  connection: ansible.netcommon.network_cli
  tasks:
    - name: Run basic command
      blumleon.vrp.vrp_command:
        commands: display version
```

## Included Plugins & Modules

| Type     | Name           | Purpose                                        |
|----------|----------------|------------------------------------------------|
| cliconf  | `vrp`          | Low-level CLI abstraction (auto-loaded)        |
| terminal | `vrp`          | Prompt matching & paging off                   |
| module   | `vrp_command`  | Run arbitrary CLI commands with wait_for logic |
| module   | `vrp_config`   | Line-oriented config (present/absent/replace)  |
| module   | `vrp_interface`| Layer-1 & Layer-2 interface management         |
| module   | `vrp_vlan`     | VLAN creation/deletion + name                  |
| module   | `vrp_ntp`      | NTP server, timezone, DST                      |
| module   | `vrp_system`   | DNS name-servers & domain name                 |
| module   | `vrp_user`     | Local AAA user & SSH-key handling              |
| module   | `vrp_backup`   | Pull running-config to controller              |
| module   | `vrp_stp_global` | Global STP BPDU-protection                   |

See `ansible-doc blumleon.vrp.<plugin>` for complete options.

## Examples

Example playbooks for local testing are provided in the `tests/` folder.
*(they require access to a lab VRP switch).*
https://github.com/blumleon/ansible-vrp/tree/main/tests

## Contributing

PRs and issues are highly appreciated!  
Please open issues in English if possible.  

## License

GPL-3.0-or-later – see [LICENSE](LICENSE).

## Author

Leon Blum - <blumleon@users.noreply.github.com>

This collection was created during an IT apprenticeship at the Swiss Federal Institute for Forest, Snow and Landscape Research (WSL)  
and is published as an open, standalone reference implementation.

Please note: The author no longer has access to VRP infrastructure – contributions are welcome, but cannot be verified live.
