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
module: vrp_vlan
short_description: Manage VLANs on Huawei VRP devices
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Creates or deletes VLANs on Huawei VRP-based devices.
  - Optionally sets a name for the VLAN.
options:
  vlan_id:
    description:
      - ID of the VLAN to manage.
    type: int
    required: true
    aliases: [id]

  name:
    description:
      - Optional VLAN name (only applied when C(state=present)).
    type: str
    required: false

  state:
    description:
      - Whether the VLAN should be present or absent.
    type: str
    choices: [present, absent]
    default: present

  save_when:
    description:
      - When to save the device configuration.
    type: str
    choices: [never, changed, always]
    default: changed

notes:
  - Requires connection C(ansible_connection=ansible.netcommon.network_cli).
  - Automatically enters and exits system-view mode when changes are needed.
  - For state C(absent), the VLAN is removed via C(undo vlan <id>) without entering the config block.

seealso:
  - module: vrp_interface
  - module: vrp_config
"""

EXAMPLES = r"""
- name: Create VLAN 100 with name "TEST_VLAN_Ansible"
  blumleon.vrp.vrp_vlan:
    vlan_id: 100
    name: "TEST_VLAN_Ansible"
    state: present
    save_when: changed

- name: Delete VLAN 100
  blumleon.vrp.vrp_vlan:
    vlan_id: 100
    state: absent
"""

RETURN = r"""
changed:
  description: Whether the VLAN was created, renamed, or deleted. Removal reports changed=True even if the VLAN was already absent.
  type: bool
  returned: always

commands:
  description: List of CLI commands that were sent to the device.
  type: list
  elements: str
  returned: when changed
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def _build_body(vlan_id: int, name: str | None) -> list[str]:
    """
    Return the *child* lines for a VLAN context.
    Only the name is configurable so far.
    """
    return [f"name {name}"] if name else []


def main() -> None:
    arg_spec = dict(
        vlan_id=dict(type="int", required=True, aliases=["id"]),
        name=dict(type="str"),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str",
            choices=["never", "changed", "always"],
            default="changed",
        ),
    )
    module = AnsibleModule(argument_spec=arg_spec, supports_check_mode=True)
    p = module.params
    conn: Connection = Connection(module._socket_path)

    vlan_parent = f"vlan {p['vlan_id']}"
    body_lines = _build_body(p["vlan_id"], p.get("name"))

    # state=absent
    if p["state"] == "absent":
        running_cfg = vc.load_running_config(conn)
        vlan_exists = vlan_parent in running_cfg

        if not vlan_exists:
            module.exit_json(changed=False, commands=[], responses=[])

        # build the command list manually (undo vlan must be issued globally)
        commands = ["system-view", f"undo vlan {p['vlan_id']}", "return"]
        vc.append_save(commands, p["save_when"], changed=True)

        if module.check_mode:
            module.exit_json(changed=True, commands=commands)

        responses = conn.run_commands(commands)
        module.exit_json(changed=True, commands=commands, responses=responses)

    # state=present
    changed, commands = vc.diff_and_wrap(
        conn,
        parents=[vlan_parent],
        cand_children=body_lines,
        save_when=p["save_when"],
        state="replace",
        keep=[],
    )

    if module.check_mode:
        module.exit_json(changed=changed, commands=commands)

    responses = conn.run_commands(commands) if changed else []
    module.exit_json(changed=changed, commands=commands, responses=responses)


if __name__ == "__main__":
    main()
