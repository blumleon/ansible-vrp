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
module: vrp_config
short_description: Manage configuration lines on Huawei VRP devices
version_added: "2.14.0"
author: Leon Blum (@blumleon)
description:
  - Applies configuration changes to Huawei VRP devices in an idempotent way.
  - Supports adding, removing, or replacing lines inside a given configuration block.
  - Optionally creates a local backup of the current configuration.
options:
  parents:
    description:
      - 'Parent lines that define the context (e.g., C(interface GigabitEthernet0/0/1)).'
      - Can be a string or list of strings.
    type: raw
    required: false

  lines:
    description:
      - List of configuration lines to add or remove.
      - Lines should not include parent context lines.
      - 'Note: To remove lines, they must be specified explicitly. state: absent with lines=[] has no effect.'
    type: list
    elements: str
    required: false

  state:
    description:
      - Whether the configuration lines should be present, absent, or used to fully replace the block.
    type: str
    choices: [present, absent, replace]
    default: present

  keep_lines:
    description:
      - When using C(state=replace), these lines will be preserved even if not present in C(lines).
    type: list
    elements: str
    required: false
    default: []

  save_when:
    description:
      - When to save the device configuration.
    type: str
    choices: [never, changed, always]
    default: changed

  backup:
    description:
      - Whether to create a local backup of the running configuration.
    type: bool
    default: false

  backup_path:
    description:
      - Optional path to write the backup file to.
    type: str
    required: false

notes:
  - Requires C(ansible_connection=ansible.netcommon.network_cli).
  - Automatically enters and exits system-view mode if configuration changes are needed.
  - When C(state=replace) is used, existing lines in the context block are removed unless preserved via C(keep_lines).
  - "Special handling is implemented for C(arp anti-attack check user-bind enable), which is correctly undone when using C(state: absent)."

seealso:
  - module: blumleon.vrp.vrp_interface
  - module: blumleon.vrp.vrp_command
"""

EXAMPLES = r"""
- name: Set interface description
  blumleon.vrp.vrp_config:
    parents: interface GigabitEthernet1/0/1
    lines:
      - description Uplink to Core
    state: present
    save_when: changed

- name: Remove a specific line from AAA section
  blumleon.vrp.vrp_config:
    parents: aaa
    lines:
      - local-user test_user privilege level 15
    state: absent

- name: Replace entire block but keep specific line
  blumleon.vrp.vrp_config:
    parents: interface GigabitEthernet1/0/1
    lines:
      - shutdown
    state: replace
    keep_lines:
      - description KEEP_ME
"""

RETURN = r"""
changed:
  description: Whether the configuration was changed or a backup was created.
  type: bool
  returned: always

commands:
  description: List of CLI commands that were sent to the device.
  type: list
  elements: str
  returned: when changed

responses:
  description: Raw responses from the device for each command.
  type: list
  elements: str
  returned: when changed

backup_path:
  description: Path to the written backup file, if created.
  type: str
  returned: when backup was used
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            lines=dict(type="list", elements="str"),
            parents=dict(type="raw"),
            state=dict(
                type="str", choices=["present", "absent", "replace"], default="present"
            ),
            keep_lines=dict(type="list", elements="str", default=[]),
            save_when=dict(
                type="str", choices=["never", "changed", "always"], default="changed"
            ),
            backup=dict(type="bool", default=False),
            backup_path=dict(type="str"),
        ),
        supports_check_mode=True,
    )

    p = module.params
    conn = Connection(module._socket_path)
    running = vc.load_running_config(conn)
    parents = vc.to_parents(p["parents"])
    cand = vc.build_candidate(parents, p["lines"])

    body_cmds = vc.diff_line_match(
        running, parents, cand[len(parents) :], p["state"], p["keep_lines"]
    )
    changed_config = bool(body_cmds)

    backup_changed, backup_path = vc.backup_config(
        conn,
        do_backup=p["backup"],
        user_path=p.get("backup_path"),
        prefix="vrp_config_",
    )

    changed = changed_config or backup_changed

    # Check-Mode: Diff via finish_module
    if module.check_mode:
        vc.finish_module(module, changed=changed, cli_cmds=body_cmds)
        return

    # Live-Run
    cli_cmds, responses = [], []
    if changed_config:
        cli_cmds = (
            ["system-view"] + parents + body_cmds + ["return"] * (len(parents) + 1)
        )
        vc.append_save(cli_cmds, p["save_when"], changed=True)
        responses = conn.run_commands(cli_cmds)

    module.exit_json(
        changed=changed,
        commands=cli_cmds,
        responses=responses,
        backup_path=backup_path,
    )


if __name__ == "__main__":
    main()
