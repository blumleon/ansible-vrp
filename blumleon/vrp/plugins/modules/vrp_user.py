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
version_added: "2.14.0"
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
  - module: blumleon.vrp.vrp_config
  - module: blumleon.vrp.vrp_backup
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

import traceback

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def _split_key_vrp(pub: str) -> list[str]:
    """Return the key exactly as provided (single-line import)."""
    return [pub.strip()]


def _aaa_one_liners(p):
    n = p["name"]
    out: list[str] = []
    if p.get("password"):
        out.append(f"local-user {n} password irreversible-cipher {p['password']}")
    if p.get("level") is not None:
        out.append(f"local-user {n} privilege level {p['level']}")
    if p.get("service_type"):
        out.append(f"local-user {n} service-type {p['service_type']}")
    return out


def _ssh_user_block(p):
    n = p["name"]
    return [
        f"ssh user {n} authentication-type rsa",
        f"ssh user {n} service-type stelnet",
    ]


def _safe_run(conn, final, module):
    resp: list[str] = []
    try:
        for cmd in final:
            resp += conn.run_commands([cmd])
        return resp
    except Exception:
        module.fail_json(msg="Command execution failed", debug=[traceback.format_exc()])


def main() -> None:
    spec = dict(
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
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p, conn = module.params, Connection(module._socket_path)
    n = p["name"]

    cli: list = []
    changed = False

    if p["state"] == "present" and p.get("ssh_key"):
        cli += [
            "system-view",
            vc.wrap_cmd(f"rsa peer-public-key {n} encoding-type openssh", user=n),
            "public-key-code begin",
            *_split_key_vrp(p["ssh_key"]),
            "public-key-code end",
            "peer-public-key end",
            "return",
            "system-view",
            vc.wrap_cmd(f"ssh user {n} assign rsa-key {n}", user=n),
            "return",
            vc.wrap_cmd("save"),
        ]
        changed = True

        c2, cli2 = vc.diff_and_wrap(
            conn,
            ["aaa"],
            _aaa_one_liners(p),
            p["save_when"],
            replace=False,
            state="present",
        )
        c3, cli3 = vc.diff_and_wrap(
            conn, [], _ssh_user_block(p), p["save_when"], replace=False, state="present"
        )
        cli += [vc.wrap_cmd(cmd, user=n) for cmd in cli2]
        cli += [vc.wrap_cmd(cmd, user=n) for cmd in cli3]
        changed |= c2 or c3

    elif p["state"] == "present":
        c2, cli2 = vc.diff_and_wrap(
            conn,
            ["aaa"],
            _aaa_one_liners(p),
            p["save_when"],
            replace=False,
            state="present",
        )
        cli += [vc.wrap_cmd(cmd, user=n) for cmd in cli2]
        changed |= c2

    else:
        lines_global = [
            f"ssh user {n} authentication-type rsa",
            f"ssh user {n} assign rsa-key {n}",
            f"ssh user {n} service-type stelnet",
            f"rsa peer-public-key {n} encoding-type openssh",
        ]
        lines_aaa = [
            f"local-user {n} password irreversible-cipher dummy",
            f"local-user {n} privilege level 3",
            f"local-user {n} service-type ssh",
        ]

        c1, cli1 = vc.diff_and_wrap(
            conn, [], lines_global, p["save_when"], replace=False, state="absent"
        )
        c2, cli2 = vc.diff_and_wrap(
            conn, ["aaa"], lines_aaa, p["save_when"], replace=False, state="absent"
        )

        cli += [vc.wrap_cmd(cmd, user=n) for cmd in cli1]
        cli += [vc.wrap_cmd(cmd, user=n) for cmd in cli2]
        changed |= c1 or c2

    if module.check_mode:
        vc.finish_module(module, changed=changed, cli_cmds=cli)
        return

    responses = _safe_run(conn, cli, module) if changed else []
    module.exit_json(changed=changed, commands=cli, responses=responses)


if __name__ == "__main__":
    main()
