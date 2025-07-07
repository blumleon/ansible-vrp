# Copyright (C) 2025 Leon Blum
# This file is part of the blumleon.vrp Ansible Collection
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

DOCUMENTATION = r"""
---
module: vrp_system
short_description: Configure system-level settings on Huawei VRP devices
version_added: "2.14.0"
author: Leon Blum (@blumleon)
description:
  - Configures IPv4/IPv6 DNS name servers and domain name on Huawei VRP.
  - Always applies global (non-interface) settings.
options:
  domain_name:
    description:
      - Domain name to set globally (e.g., example.com).
    type: str

  ipv4:
    description:
      - List of IPv4 DNS servers.
    type: list
    elements: str

  ipv6:
    description:
      - List of IPv6 DNS servers.
    type: list
    elements: str

  state:
    description:
      - Whether to apply or remove the configuration.
    type: str
    choices: [present, absent]
    default: present

  save_when:
    description:
      - When to save the device configuration.
    type: str
    choices: [never, changed, always]
    default: changed

  backup:
    description:
      - Whether to back up the current configuration.
    type: bool
    default: false

  backup_path:
    description:
      - Optional path to save the backup file on the controller.
    type: str
    required: false

notes:
  - Requires C(ansible_connection=ansible.netcommon.network_cli).
  - Always affects global config.
"""

EXAMPLES = r"""
- name: Set domain and DNS servers
  blumleon.vrp.vrp_system:
    domain_name: example.com
    ipv4:
      - 192.0.2.1
      - 192.0.2.2
    save_when: changed

- name: Remove all DNS and domain config
  blumleon.vrp.vrp_system:
    domain_name: example.com
    ipv4:
      - 192.0.2.1
      - 192.0.2.2
    ipv6:
      - 2001:db8::1
    state: absent
    save_when: always
"""

RETURN = r"""
changed:
  description: Whether anything changed or a backup was triggered.
  type: bool
  returned: always

commands:
  description: CLI commands sent to the device.
  type: list
  elements: str
  returned: when changed

responses:
  description: Raw device responses.
  type: list
  elements: str
  returned: when changed

backup_path:
  description: Backup file path (if created).
  type: str
  returned: when backup was requested
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def _build_desired_lines(p: dict) -> list[str]:
    """Return the *desired* configuration lines – never pre-prended with "undo"."""
    lines: list[str] = []

    if p.get("domain_name"):
        lines.append(f"ip domain-name {p['domain_name']}")

    for ip in p.get("ipv4") or []:
        lines.append(f"dns server {ip}")

    for ip in p.get("ipv6") or []:
        lines.append(f"dns server ipv6 {ip}")

    return lines


def main() -> None:
    arg_spec = dict(
        domain_name=dict(type="str"),
        ipv4=dict(type="list", elements="str"),
        ipv6=dict(type="list", elements="str"),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str", choices=["never", "changed", "always"], default="changed"
        ),
        backup=dict(type="bool", default=False),
        backup_path=dict(type="str"),
    )

    module = AnsibleModule(argument_spec=arg_spec, supports_check_mode=True)
    p = module.params
    conn = Connection(module._socket_path)

    # optional backup
    backup_changed, backup_path = vc.backup_config(
        conn, p["backup"], p.get("backup_path"), prefix="vrp_system_"
    )

    # build desired body
    desired_lines = _build_desired_lines(p)
    desired_state = "absent" if p["state"] == "absent" else "present"

    # diff & wrap
    cfg_changed, cli_cmds = vc.diff_and_wrap(
        conn,
        parents=[],
        cand_children=desired_lines,
        save_when=p["save_when"],
        state=desired_state,
        replace=False,
        keep=[],
    )

    changed = cfg_changed or backup_changed

    # check-mode
    if module.check_mode:
        module.exit_json(
            changed=changed,
            commands=cli_cmds,
            backup_path=backup_path,
        )

    # execute & return
    responses = conn.run_commands(cli_cmds) if cfg_changed else []

    module.exit_json(
        changed=changed,
        commands=cli_cmds,
        responses=responses,
        backup_path=backup_path,
    )


if __name__ == "__main__":
    main()
