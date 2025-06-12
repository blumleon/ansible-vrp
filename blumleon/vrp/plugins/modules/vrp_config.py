#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

DOCUMENTATION = r"""
---
module: vrp_config
short_description: Idempotente Konfig-Änderungen auf Huawei-VRP
version_added: "1.2.0"
author: Leon Blum (@blumleon)
description:
  - Fügt Zeilen hinzu, entfernt sie oder ersetzt Blöcke in der Running-Config.
  - Erstellt optional ein Backup der laufenden Konfiguration.
options:
  parents:      {type: raw}
  lines:        {type: list, elements: str}
  state:        {type: str, choices: [present, absent, replace], default: present}
  keep_lines:   {type: list, elements: str}
  save_when:    {type: str, choices: [never, changed, always], default: changed}
  backup:       {type: bool, default: false}
  backup_path:  {type: str}
"""


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

    # ------------------------------ Backup (neuer Helper)
    backup_changed, backup_path = vc.backup_config(
        conn,
        do_backup=p["backup"],
        user_path=p.get("backup_path"),
        prefix="vrp_config_",
    )

    changed = changed_config or backup_changed

    if module.check_mode:
        module.exit_json(changed=changed, commands=body_cmds, backup_path=backup_path)

    cli_cmds, responses = [], []
    if changed_config:
        cli_cmds = (
            ["system-view"] + parents + body_cmds + ["return"] * (len(parents) + 1)
        )
        vc.append_save(cli_cmds, p["save_when"])  # ← save anfügen
        responses = conn.run_commands(cli_cmds)

    module.exit_json(
        changed=changed, commands=cli_cmds, responses=responses, backup_path=backup_path
    )


if __name__ == "__main__":
    main()
