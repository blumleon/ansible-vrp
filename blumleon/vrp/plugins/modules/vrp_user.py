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
module: vrp_user
short_description: Manage local AAA users and SSH key access on Huawei VRP devices
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Creates or removes local users on Huawei VRP platforms under the C(aaa) configuration hierarchy.
  - Supports both classic password-based accounts and SSH key-based authentication.
  - Configures optional privilege level and service type (e.g. SSH or Telnet).
  - Automatically handles RSA peer-public-key import and SSH user assignment if a public key is given.
options:
  name:
    description:
      - Name of the user account.
    type: str
    required: true

  password:
    description:
      - User password (stored using irreversible-cipher).
      - Ignored if C(ssh_key) is set.
    type: str
    required: false

  ssh_key:
    description:
      - Public key in OpenSSH format.
      - If specified, the user will be created without a password and authenticated via RSA.
    type: str
    required: false

  level:
    description:
      - Privilege level of the user (e.g. 1-3).
    type: int
    required: false

  service_type:
    description:
      - Protocols the user is allowed to use.
    type: str
    choices: [ssh, telnet]
    required: false

  state:
    description:
      - Whether the user should be present or removed.
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
  - Requires C(ansible_connection=ansible.netcommon.network_cli).
  - If C(ssh_key) is provided, the module will wrap the key automatically and inject it under C(rsa peer-public-key) with C(public-key-code).
  - Prompt confirmation for privilege or undo actions is automatically handled.
  - Password-based and SSH key-based users are mutually exclusive (password is ignored if key is present).

seealso:
  - module: vrp_config
  - module: vrp_backup
"""

EXAMPLES = r"""
- name: Create user with SSH key authentication
  blumleon.vrp.vrp_user:
    name: ansible_user
    ssh_key: "{{ lookup('file', 'files/ansible_keyuser.pub') }}"
    level: 3
    service_type: ssh
    save_when: changed

- name: Create a classic user with password and telnet access
  blumleon.vrp.vrp_user:
    name: legacy_admin
    password: <changeme>
    level: 3
    service_type: telnet
    save_when: changed

- name: Remove a local user completely
  blumleon.vrp.vrp_user:
    name: ansible_user
    state: absent
    save_when: always
"""

RETURN = r"""
changed:
  description: Whether the user configuration or key import caused any changes.
  type: bool
  returned: always

commands:
  description: List of CLI commands issued, including interactive confirmations.
  type: list
  elements: raw
  returned: when changed

responses:
  description: Raw CLI responses for each command.
  type: list
  elements: str
  returned: when changed
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


# ------------------------------------------------------------------- helpers
def _split_key_vrp(pub: str) -> list[str]:
    """
    Returns the OpenSSH key exactly as it was transferred,
    without wraps or formatting - necessary for VRP import.
    """
    return [pub.strip()]


def _aaa_one_liners(p):
    name = p["name"]
    l = []
    if p.get("password"):
        l.append(f"local-user {name} password irreversible-cipher {p['password']}")
    if p.get("level") is not None:
        l.append(f"local-user {name} privilege level {p['level']}")
    if p.get("service_type"):
        l.append(f"local-user {name} service-type {p['service_type']}")
    return l


def _ssh_user_block(p):
    n = p["name"]
    return [
        f"ssh user {n} authentication-type rsa",
        f"ssh user {n} assign rsa-key {n}",
        f"ssh user {n} service-type stelnet",
    ]


# ------------------------------------------------------------------- main
def main():
    args = dict(
        name=dict(type="str", required=True),
        password=dict(type="str", no_log=True),
        ssh_key=dict(type="str", no_log=True),
        level=dict(type="int"),
        service_type=dict(type="str", choices=["ssh", "telnet"]),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str", choices=["never", "changed", "always"], default="changed"
        ),
    )
    module = AnsibleModule(argument_spec=args, supports_check_mode=True)
    p = module.params
    conn = Connection(module._socket_path)

    name = p["name"]
    all_cmds, changed = [], False

    # ---------------------------------------------------- SSH-key-user
    if p["state"] == "present" and p.get("ssh_key"):
        parent_cmd = f"rsa peer-public-key {name} encoding-type openssh"
        c1, cmds1 = vc.diff_and_wrap(
            conn, [], [parent_cmd], save_when=p["save_when"], replace=False
        )
        all_cmds += cmds1
        changed |= c1

        if changed and not module.check_mode:
            key_lines = _split_key_vrp(p["ssh_key"])

            cmd_list = [
                "system-view",
                parent_cmd,
                "public-key-code begin",
                *key_lines,
                "public-key-code end",
                "peer-public-key end",
                "return",
            ]
            conn.run_commands(cmd_list)
            all_cmds += cmd_list

        aaa_lines = []
        if p.get("level") is not None:
            aaa_lines.append(f"local-user {name} privilege level {p['level']}")
        if p.get("service_type"):
            aaa_lines.append(f"local-user {name} service-type {p['service_type']}")
        c2, cmds2 = vc.diff_and_wrap(
            conn, ["aaa"], aaa_lines, save_when=p["save_when"], replace=False
        )
        all_cmds += cmds2
        changed |= c2

        c3, cmds3 = vc.diff_and_wrap(
            conn, [], _ssh_user_block(p), save_when=p["save_when"], replace=False
        )
        all_cmds += cmds3
        changed |= c3

    # ---------------------------------------------------- classic user
    elif p["state"] == "present":
        c2, cmds2 = vc.diff_and_wrap(
            conn, ["aaa"], _aaa_one_liners(p), save_when=p["save_when"], replace=False
        )
        all_cmds += cmds2
        changed |= c2

    # ---------------------------------------------------- remove user
    else:
        sys_un = [
            f"undo ssh user {name} authentication-type rsa",
            f"undo ssh user {name} assign rsa-key {name}",
            f"undo ssh user {name} service-type stelnet",
            f"undo rsa peer-public-key {name}",
        ]
        c1, cmds1 = vc.diff_and_wrap(conn, [], sys_un, p["save_when"], False)
        all_cmds += cmds1
        changed |= c1

        c2, cmds2 = vc.diff_and_wrap(
            conn, ["aaa"], [f"undo local-user {name}"], p["save_when"], False
        )
        all_cmds += cmds2
        changed |= c2

    if module.check_mode:
        module.exit_json(changed=changed, commands=all_cmds)

    # Prompt-Handling
    priv_cmd = (
        f"local-user {name} privilege level {p.get('level')}"
        if p.get("level") is not None
        else None
    )
    final_cmds = []
    for cmd in all_cmds:
        if isinstance(cmd, str):
            if priv_cmd and cmd == priv_cmd:
                final_cmds.append(
                    {"command": cmd, "prompt": r"[Yy]/[Nn]", "answer": "y"}
                )
            elif cmd.startswith(f"undo rsa peer-public-key {name}"):
                final_cmds.append(
                    {"command": cmd, "prompt": r"\[Y/N\]:", "answer": "y"}
                )
            else:
                final_cmds.append(cmd)
        else:
            # dict or already prepared prompt → simply pass through
            final_cmds.append(cmd)

    resp = conn.run_commands(final_cmds) if changed else []
    module.exit_json(changed=changed, commands=final_cmds, responses=resp)


if __name__ == "__main__":
    main()
