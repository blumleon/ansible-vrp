#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type
"""
vrp_user – legt / entfernt lokale Benutzer auf Huawei-VRP, künftig auch per SSH-Key.
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc
import textwrap

DOCUMENTATION = r'''
---
module: vrp_user
short_description: Verwalte lokale Benutzer im AAA- und SSH-Kontext
version_added: "1.3.0"
author: Leon Blum (@blumleon)
description:
  - Erstellt oder löscht Benutzer unter C(aaa).
  - Setzt Passwort (irreversible-cipher), Privilege-Level, Service-Typ.
  - Optional: Erstellt Benutzer nur mit SSH-Key (ohne Passwort).
options:
  name:         {type: str, required: true}
  password:     {type: str, no_log: true}
  ssh_key:      {type: str}
  level:        {type: int}
  service_type: {type: str, choices: [ssh, telnet]}
  state:        {type: str, choices: [present, absent], default: present}
  save_when:    {type: str, choices: [never, changed, always], default: changed}
'''

def _aaa_one_liners(p):
    """Reihenfolge: Passwort → Level → Service-Typ."""
    name = p['name']
    lines = []
    if p.get("password") is not None:
        lines.append(f"local-user {name} password irreversible-cipher {p['password']}")
    if p.get("level") is not None:
        lines.append(f"local-user {name} privilege level {p['level']}")
    if p.get("service_type"):
        lines.append(f"local-user {name} service-type {p['service_type']}")
    return lines

def _ssh_user_block(p):
    """SSH-User-Konfiguration (RSA-Auth + assign + stelnet)."""
    name = p['name']
    return [
        f"ssh user {name} authentication-type rsa",
        f"ssh user {name} assign rsa-key {name}",
        f"ssh user {name} service-type stelnet",
    ]

def main():
    args = dict(
        name         = dict(type="str", required=True),
        password     = dict(type="str", no_log=True),
        ssh_key      = dict(type="str"),
        level        = dict(type="int"),
        service_type = dict(type="str", choices=["ssh", "telnet"]),
        state        = dict(type="str", choices=["present", "absent"], default="present"),
        save_when    = dict(type="str", choices=["never", "changed", "always"], default="changed"),
    )
    module = AnsibleModule(argument_spec=args, supports_check_mode=True)
    p      = module.params
    conn   = Connection(module._socket_path)

    name     = p['name']
    all_cmds = []
    changed  = False

    if p["state"] == "present" and p.get("ssh_key") is not None:
        # -----------------------------
        # 1) Peer-Public-Key parent
        # -----------------------------
        parent_cmd = f"rsa peer-public-key {name} encoding-type openssh"
        c1, cmds1 = vc.diff_and_wrap(
            conn,
            parents       = [],
            cand_children = [parent_cmd],
            save_when     = p["save_when"],
            replace       = False
        )
        all_cmds.extend(cmds1)
        changed = changed or c1

        # -----------------------------
        # 2) Public-Key-Editor-Block
        # -----------------------------
        key = p['ssh_key']
        if changed and not module.check_mode:
            conn.run_commands([f"rsa peer-public-key {name} encoding-type openssh"])
            conn.run_commands(["public-key-code begin"])
            for line in textwrap.wrap(key, width=60):
                conn.run_commands([line])
            conn.run_commands(["public-key-code end", "peer-public-key end"])
            all_cmds.extend([
                f"rsa peer-public-key {name} encoding-type openssh",
                "public-key-code begin",
                *textwrap.wrap(key, width=60),
                "public-key-code end",
                "peer-public-key end"
            ])

        # -----------------------------
        # 3) AAA part (ohne Passwort)
        # -----------------------------
        aaa_lines = []
        if p.get("level") is not None:
            aaa_lines.append(f"local-user {name} privilege level {p['level']}")
        if p.get("service_type"):
            aaa_lines.append(f"local-user {name} service-type {p['service_type']}")

        c2, cmds2 = vc.diff_and_wrap(
            conn,
            parents       = ["aaa"],
            cand_children = aaa_lines,
            save_when     = p["save_when"],
            replace       = False
        )
        all_cmds.extend(cmds2)
        changed = changed or c2

        # -----------------------------
        # 4) SSH-User part
        # -----------------------------
        ssh_lines = _ssh_user_block(p)
        c3, cmds3 = vc.diff_and_wrap(
            conn,
            parents       = [],
            cand_children = ssh_lines,
            save_when     = p["save_when"],
            replace       = False
        )
        all_cmds.extend(cmds3)
        changed = changed or c3

    elif p["state"] == "present":
        # klassischer AAA-User (inkl. Passwort)
        c2, cmds2 = vc.diff_and_wrap(
            conn,
            parents       = ["aaa"],
            cand_children = _aaa_one_liners(p),
            save_when     = p["save_when"],
            replace       = False
        )
        all_cmds.extend(cmds2)
        changed = changed or c2

    else:
        # state == absent
        # 1) SSH und Peer-Key entfernen
        sys_removals = [
            f"undo ssh user {name} authentication-type rsa",
            f"undo ssh user {name} assign rsa-key {name}",
            f"undo ssh user {name} service-type stelnet",
            f"undo rsa peer-public-key {name}"
        ]
        c1, cmds1 = vc.diff_and_wrap(conn, [], sys_removals, p["save_when"], False)
        all_cmds.extend(cmds1)
        changed = changed or c1

        # 2) AAA entfernen
        c2, cmds2 = vc.diff_and_wrap(conn, ["aaa"], [f"undo local-user {name}"], p["save_when"], False)
        all_cmds.extend(cmds2)
        changed = changed or c2

    if module.check_mode:
        module.exit_json(changed=changed, commands=all_cmds)

    # Prompt-Handling für Level + Peer-Key-Undo
    priv_cmd = f"local-user {name} privilege level {p.get('level')}" if p.get("level") is not None else None
    final_cmds = []
    for cmd in all_cmds:
        if isinstance(cmd, dict):
            final_cmds.append(cmd)
            continue
        if priv_cmd and cmd == priv_cmd:
            final_cmds.append({
                "command": cmd,
                "prompt":  r"[Yy]/[Nn]",
                "answer":  "y"
            })
        elif cmd.startswith(f"undo rsa peer-public-key {name}"):
            final_cmds.append({
                "command": cmd,
                "prompt":  r"\[Y/N\]:",
                "answer":  "y"
            })
        else:
            final_cmds.append(cmd)

    responses = conn.run_commands(final_cmds) if changed else []
    module.exit_json(changed=changed, commands=final_cmds, responses=responses)

if __name__ == "__main__":
    main()

