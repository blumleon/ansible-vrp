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
version_added: "1.0.0"
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


def main():
    args = dict(
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

    module = AnsibleModule(argument_spec=args, supports_check_mode=True)
    p = module.params
    conn = Connection(module._socket_path)

    # Step 1: optional backup
    changed, backup_file = vc.backup_config(conn, p["backup"], p.get("backup_path"))

    # Step 2: generate desired config lines
    cmds = []
    if p.get("domain_name"):
        cmd = f"ip domain-name {p['domain_name']}"
        if p["state"] == "absent":
            cmd = "undo " + cmd
        cmds.append(cmd)

    for ip in p.get("ipv4") or []:
        cmd = f"dns server {ip}"
        if p["state"] == "absent":
            cmd = "undo " + cmd
        cmds.append(cmd)

    for ip in p.get("ipv6") or []:
        cmd = f"dns ipv6 server {ip}"
        if p["state"] == "absent":
            cmd = "undo " + cmd
        cmds.append(cmd)

    # Step 3: exit early if nothing to do
    if not cmds:
        module.exit_json(changed=changed, backup_path=backup_file)

    # Step 4: compare running config
    running = vc.load_running_config(conn)
    if p["state"] == "present" and vc.lines_present(running, cmds):
        module.exit_json(changed=changed, backup_path=backup_file)

    # Step 5: prepare CLI + check mode
    diffed, cli = vc.diff_and_wrap(conn, [], cmds, p["save_when"], replace=False)
    if module.check_mode:
        module.exit_json(changed=changed or diffed, commands=cli)

    # Step 6: send commands
    responses = conn.run_commands(cli) if diffed else []
    module.exit_json(
        changed=changed or diffed,
        commands=cli,
        responses=responses,
        backup_path=backup_file,
    )


if __name__ == "__main__":
    main()
