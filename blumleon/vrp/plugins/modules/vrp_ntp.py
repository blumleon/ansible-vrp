#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

DOCUMENTATION = r"""
---
module: vrp_ntp
short_description: Minimal-NTP-Konfiguration auf Huawei-VRP
version_added: "1.3.1"
author: Leon Blum (@blumleon)
description:
  - Konfiguriert Zeitzone, Sommerzeit und einen externen NTP-Server.
  - Erstellt optional ein Backup der Running-Config.
options:
  server:               {type: str, required: true}
  source_interface:     {type: str}
  timezone_name:        {type: str, default: CET}
  timezone_offset:      {type: int, default: 1}
  dst_name:             {type: str, default: Sommerzeit}
  dst_start:            {type: str, default: "02:00 2025-03-30"}
  dst_end:              {type: str, default: "03:00 2025-10-26"}
  dst_offset:           {type: str, default: "01:00"}
  disable_ipv4_server:  {type: bool, default: true}
  disable_ipv6_server:  {type: bool, default: true}
  state:                {type: str, choices: [present, absent], default: present}
  save_when:            {type: str, choices: [never, changed, always], default: changed}
  backup:               {type: bool, default: false}
  backup_path:          {type: str}
"""


def build_lines(p):
    lines = [
        f"clock timezone {p['timezone_name']} add {p['timezone_offset']}",
        f"clock daylight-saving-time {p['dst_name']} one-year {p['dst_start']} {p['dst_end']} {p['dst_offset']}",
        f"ntp unicast-server {p['server']}",
    ]
    if p["disable_ipv4_server"]:
        lines.append("ntp server disable")
    if p["disable_ipv6_server"]:
        lines.append("ntp ipv6 server disable")
    if p.get("source_interface"):
        lines.append(f"ntp server source-interface {p['source_interface']}")
    if p["state"] == "absent":
        lines = [f"undo {cmd}" for cmd in lines]
    return lines


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            server=dict(type="str", required=True),
            source_interface=dict(type="str"),
            timezone_name=dict(type="str", default="CET"),
            timezone_offset=dict(type="int", default=1),
            dst_name=dict(type="str", default="Sommerzeit"),
            dst_start=dict(type="str", default="02:00 2025-03-30"),
            dst_end=dict(type="str", default="03:00 2025-10-26"),
            dst_offset=dict(type="str", default="01:00"),
            disable_ipv4_server=dict(type="bool", default=True),
            disable_ipv6_server=dict(type="bool", default=True),
            state=dict(type="str", choices=["present", "absent"], default="present"),
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

    body_cmds = vc.diff_line_match(running, [], build_lines(p), "present", keep=[])
    changed_config = bool(body_cmds)

    # ------------------------------ Backup (neuer Helper)
    backup_changed, backup_path = vc.backup_config(
        conn,
        do_backup=p["backup"],
        user_path=p.get("backup_path"),
        prefix="vrp_ntp_",
    )

    changed = changed_config or backup_changed

    if module.check_mode:
        module.exit_json(changed=changed, commands=body_cmds, backup_path=backup_path)

    cli_cmds, responses = [], []
    if changed_config:
        cli_cmds = ["system-view"] + body_cmds + ["return"]
        vc.append_save(cli_cmds, p["save_when"])
        responses = conn.run_commands(cli_cmds)

    module.exit_json(
        changed=changed, commands=cli_cmds, responses=responses, backup_path=backup_path
    )


if __name__ == "__main__":
    main()
