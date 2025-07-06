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
module: vrp_stp_global
short_description: Configure global STP protection on Huawei VRP
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Enables or disables global Spanning Tree protection features such as BPDU protection.
  - Always applies global (non-interface) settings.
options:
  bpdu_protect:
    description:
      - Enables or disables STP BPDU protection globally.
    type: bool

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
  - Only affects global config.
"""

EXAMPLES = r"""
- name: Enable global BPDU protection
  blumleon.vrp.vrp_stp_global:
    bpdu_protect: true

- name: Disable BPDU protection
  blumleon.vrp.vrp_stp_global:
    bpdu_protect: false

- name: Remove BPDU protection configuration explicitly
  blumleon.vrp.vrp_stp_global:
    bpdu_protect: true
    state: absent
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
    if p.get("bpdu_protect") is True:
        return ["stp bpdu-protection"]
    if p["state"] == "absent":
        return ["stp bpdu-protection"]
    return []


def main() -> None:
    arg_spec = dict(
        bpdu_protect=dict(type="bool"),
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
        conn, p["backup"], p.get("backup_path"), prefix="vrp_stp_"
    )

    # desired body
    desired_lines = _build_desired_lines(p)
    desired_state = "absent" if p["state"] == "absent" else "present"

    # diff & wrap
    cfg_changed, cli_cmds = vc.diff_and_wrap(
        conn,
        parents=[],
        cand_children=desired_lines,
        save_when=p["save_when"],
        state=desired_state,
        replace=(desired_state == "absent"),
        keep=[],
    )

    changed = cfg_changed or backup_changed

    if module.check_mode:
        module.exit_json(
            changed=changed,
            commands=cli_cmds,
            backup_path=backup_path,
        )

    responses = conn.run_commands(cli_cmds) if cfg_changed else []

    module.exit_json(
        changed=changed,
        commands=cli_cmds,
        responses=responses,
        backup_path=backup_path,
    )


if __name__ == "__main__":
    main()
