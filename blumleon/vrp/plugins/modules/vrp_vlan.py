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


def main():
    spec = dict(
        vlan_id=dict(type="int", required=True, aliases=["id"]),
        name=dict(type="str"),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str", choices=["never", "changed", "always"], default="changed"
        ),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p = module.params
    conn = Connection(module._socket_path)

    parents = f"vlan {p['vlan_id']}"

    if p["state"] == "absent":
        body = []
        cli = [f"undo vlan {p['vlan_id']}"]
    else:
        body = [f"name {p['name']}"] if p.get("name") else []
        running = vc.load_running_config(conn)
        body = vc.diff_line_match(running, [parents], body, state="replace", keep=[])
        cli = ["system-view", parents] + body + ["return", "return"]

    changed = bool(body) or p["state"] == "absent"

    if changed:
        vc.append_save(cli, p["save_when"])

    if module.check_mode:
        module.exit_json(changed=changed, commands=cli)

    responses = conn.run_commands(cli) if changed else []
    module.exit_json(changed=changed, commands=cli, responses=responses)


if __name__ == "__main__":
    main()
