#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type
"""
vrp_user – legt / entfernt lokale Benutzer auf Huawei-VRP.
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

DOCUMENTATION = r'''
---
module: vrp_user
short_description: Verwalte lokale Benutzer im AAA-Kontext
version_added: "1.3.0"
author: Leon Blum (@blumleon)
description:
  - Erstellt oder löscht Benutzer unter C(aaa).
  - Setzt Passwort (irreversible-cipher), Privilege-Level, Service-Typ.
options:
  name:         {type: str, required: true}
  password:     {type: str, no_log: true}
  level:        {type: int}
  service_type: {type: str, choices: [ssh, telnet]}
  state:        {type: str, choices: [present, absent], default: present}
  save_when:    {type: str, choices: [never, changed, always], default: changed}
'''

# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------

def main():
    args = dict(
        name         = dict(type="str", required=True),
        password     = dict(type="str", no_log=True),
        level        = dict(type="int"),
        service_type = dict(type="str", choices=["ssh", "telnet"]),
        state        = dict(type="str", choices=["present", "absent"], default="present"),
        save_when    = dict(type="str", choices=["never", "changed", "always"], default="changed"),
    )
    module = AnsibleModule(argument_spec=args, supports_check_mode=True)
    p      = module.params
    conn   = Connection(module._socket_path)

    parents = ["aaa"]
    desired = _aaa_one_liners(p) if p["state"] == "present" \
              else [f"undo local-user {p['name']}"]

    # Erzeuge das CLI-Block mit diff_and_wrap (Strings only!)
    changed, cli_cmds = vc.diff_and_wrap(
        conn,
        parents       = parents,
        cand_children = desired,
        save_when     = p["save_when"],
        replace       = False
    )

    # Im Check-Mode reicht uns das Ergebnis
    if module.check_mode:
        module.exit_json(changed=changed, commands=cli_cmds)

    # **Prompt-Handling:** ersetze genau das Privilege-Kommando durch ein Dict
    if changed and p.get("level") is not None:
        priv_cmd = f"local-user {p['name']} privilege level {p['level']}"
        new_cli = []
        for cmd in cli_cmds:
            if cmd == priv_cmd:
                new_cli.append({
                    "command": cmd,
                    "prompt":  r"[Yy]/[Nn]",
                    "answer":  "y"
                })
            else:
                new_cli.append(cmd)
        cli_cmds = new_cli

    # Jetzt wirklich ausführen
    responses = conn.run_commands(cli_cmds) if changed else []
    module.exit_json(changed=changed, commands=cli_cmds, responses=responses)

if __name__ == "__main__":
    main()

