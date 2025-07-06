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
module: vrp_interface
short_description: Configures Huawei VRP interfaces (L1 & L2) idempotently
version_added: "1.0.0"
author:
  - Leon Blum (@blumleon)
description:
  - This module enables consistent configuration of interface parameters on Huawei VRP devices.
  - Supports Layer-1 (description, admin status, MTU, speed) and Layer-2 (access/trunk/hybrid modes).
  - Automatically detects existing configuration and only applies necessary changes.
  - Supports check mode and optionally saves the configuration persistently.
options:
  name:
    description:
      - Interface name, e.g. C(MultiGE1/0/20)
    required: true
    type: str
  admin_state:
    description:
      - Administrative interface state
    type: str
    choices: [up, down]
  description:
    description:
      - Interface description (empty = remove)
    type: str
  speed:
    description:
      - Fixed speed, e.g. C(1000), depending on the model
    type: str
  mtu:
    description:
      - Maximum packet size in bytes, e.g. C(1500)
    type: int
  port_mode:
    description:
      - Layer-2 port mode
    type: str
    choices: [access, trunk, hybrid]
  vlan:
    description:
      - VLAN ID for access ports
    type: int
  trunk_vlans:
    description:
      - VLAN list for trunk or hybrid ports, e.g. C(10,20-30)
    type: str
  native_vlan:
    description:
      - Native VLAN for trunk ports (sets PVID)
    type: int
  stp_edged:
    description:
      - Enables STP edge port mode (fast transition to forwarding)
      - Only valid in access mode
    type: bool
    default: false
  state:
    description:
      - Sets the interface to C(present) (configure) or C(absent) (reset)
    default: present
    type: str
    choices: [present, absent]
  save_when:
    description:
      - When to save the configuration
    type: str
    default: changed
    choices: [never, changed, always]
notes:
  - Recommended for switchports – not suitable for loopbacks or management interfaces.
  - C(trunk_vlans) is passed as a list like C("10,20-25") and automatically formatted.
  - C(vlan) may only be set on access ports, C(native_vlan) only on trunk ports.
  - The module automatically detects if e.g. C(undo shutdown) is implicitly active.
"""

EXAMPLES = r"""
- name: Simple access port (VLAN 20)
  blumleon.vrp.vrp_interface:
    name: MultiGE1/0/14
    port_mode: access
    vlan: 20
    description: "Client port"
    admin_state: up
    save_when: changed

- name: Trunk port with VLAN list (native VLAN 55)
  blumleon.vrp.vrp_interface:
    name: MultiGE1/0/30
    port_mode: trunk
    trunk_vlans: "10-20,55,60"
    native_vlan: 55
    description: "Uplink to Core"
    admin_state: up
    save_when: always

- name: Hybrid port with VLAN tagging
  blumleon.vrp.vrp_interface:
    name: MultiGE1/0/31
    port_mode: hybrid
    trunk_vlans: "100,200"
    native_vlan: 1
    description: "IoT Segment"
    admin_state: up

- name: Reset interface to factory default
  blumleon.vrp.vrp_interface:
    name: MultiGE1/0/31
    state: absent
"""

RETURN = r"""
commands:
  description: List of CLI commands sent
  returned: always
  type: list
  elements: raw
  sample:
    - system-view
    - interface MultiGE1/0/14
    - description Test-Port
    - port link-type access
    - port default vlan 3999
    - undo shutdown
    - return
    - return
    - command: save
      prompt: '[Y/N]'
      answer: 'Y'

responses:
  description: CLI responses from the device (if commands were sent)
  returned: when changed
  type: list
  elements: str
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def _validate_params(module, p):
    """Fail fast on mutually-exclusive interface parameters."""
    mode = p.get("port_mode")

    if mode == "access":
        if p.get("trunk_vlans") or p.get("native_vlan"):
            module.fail_json(
                msg="'trunk_vlans' and 'native_vlan' are not allowed in access mode"
            )

    if mode in ("trunk", "hybrid") and p.get("vlan") is not None:
        module.fail_json(
            msg="'vlan' can only be used when port_mode is set to 'access'"
        )

    if p.get("stp_edged") and mode != "access":
        module.fail_json(
            msg="'stp_edged' is only supported when port_mode is set to 'access'"
        )


def main() -> None:
    spec = dict(
        # Layer-1 options
        name=dict(type="str", required=True),
        admin_state=dict(type="str", choices=["up", "down"]),
        description=dict(type="str"),
        speed=dict(type="str"),
        mtu=dict(type="int"),
        # Layer-2 options
        port_mode=dict(type="str", choices=["access", "trunk", "hybrid"]),
        vlan=dict(type="int"),
        trunk_vlans=dict(type="str"),
        native_vlan=dict(type="int"),
        stp_edged=dict(type="bool", default=False),
        # Meta
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str", choices=["never", "changed", "always"], default="changed"
        ),
    )

    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p = module.params
    _validate_params(module, p)

    conn = Connection(module._socket_path)
    parents = [f"interface {p['name']}"]

    # desired body / state
    if p["state"] == "absent":
        body = ["shutdown"]
        diff_state = "replace"
    else:
        body = vc.build_interface_lines(p)
        diff_state = "replace"

    # diff + wrapper
    changed, cli_cmds = vc.diff_and_wrap(
        conn,
        parents=parents,
        cand_children=body,
        save_when=p["save_when"],
        state=diff_state,
        keep=[],
    )

    if module.check_mode:
        module.exit_json(changed=changed, commands=cli_cmds)

    responses = conn.run_commands(cli_cmds) if changed else []
    module.exit_json(changed=changed, commands=cli_cmds, responses=responses)


if __name__ == "__main__":
    main()
