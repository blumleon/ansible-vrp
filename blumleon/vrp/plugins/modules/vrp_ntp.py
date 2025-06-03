#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

import os
import tempfile

DOCUMENTATION = r'''
---
module: vrp_ntp
short_description: Minimal-NTP-Konfiguration auf Huawei-VRP
version_added: "1.3.0"
author: Leon Blum (@blumleon)
description:
  - Setzt Time-Zone, ein einmaliges Sommerzeit-Fenster und einen (unicast)-NTP-Server.
  - IPv4- und IPv6-NTP-Server-Funktionen werden deaktiviert, weil die meisten
    Access-Switches nur Client sein sollen.
  - Gibt *changed* zurück, wenn sich entweder die Gerätekonfiguration ODER
    das lokale Backup geändert hat.
options:
  server:
    description: IPv4-Adresse des NTP-Servers.
    type: str
    required: true
  source_interface:
    description: Optionales Source-Interface für NTP-Pakete.
    type: str
  timezone_name:
    description: Anzeigename der Zeitzone.
    type: str
    default: CET
  timezone_offset:
    description: Offset in Stunden zur UTC (z. B. 1 für +01:00).
    type: int
    default: 1
  dst_name:
    description: Anzeigename für die Sommerzeit.
    type: str
    default: Sommerzeit
  dst_start:
    description: Start-Zeitpunkt im Format C("HH:MM YYYY-MM-DD").
    type: str
    default: "02:00 2025-03-30"
  dst_end:
    description: End-Zeitpunkt im Format C("HH:MM YYYY-MM-DD").
    type: str
    default: "03:00 2025-10-26"
  disable_ipv4_server:
    description: Deaktiviert den integrierten IPv4-NTP-Server.
    type: bool
    default: true
  disable_ipv6_server:
    description: Deaktiviert den integrierten IPv6-NTP-Server.
    type: bool
    default: true
  state:
    description: present (konfigurieren) oder absent (rückgängig machen).
    choices: [present, absent]
    default: present
  save_when:
    description: Wann C(save) aufgerufen wird.
    choices: [never, changed, always]
    default: changed
  backup:
    description: Running-Config lokal sichern.
    type: bool
    default: false
  backup_path:
    description: Benutzerdefinierter Pfad für das Backup.
    type: str
'''

EXAMPLES = r'''
- name: Minimaler NTP-Client
  vrp_ntp:
    server: 10.30.1.7

- name: Mit Source-Interface und eigener Sommerzeit-Definition
  vrp_ntp:
    server: 10.30.1.7
    source_interface: Vlanif123
    timezone_offset: 1
    dst_start: "02:00 2026-03-29"
    dst_end:   "03:00 2026-10-25"
'''

RETURN = r'''
changed:
  description: Ob Gerätekonfiguration ODER Backup geändert wurden.
  type: bool
commands:
  description: CLI-Befehle, die abgesetzt wurden (nur wenn changed_config).
  returned: when changed
  type: list
backup_path:
  description: Pfad der gesicherten Config, falls backup=true.
  type: str
'''

def build_lines(p):
    """
    Erzeugt die benötigten CLI-Befehle für *state=present*.
    Bei state=absent werden die Befehle automatisch mit 'undo' versehen.
    """
    lines = [
        f"clock timezone {p['timezone_name']} add {p['timezone_offset']}",
        (f"clock daylight-saving-time {p['dst_name']} one-year "
         f"{p['dst_start']} {p['dst_end']}"),
        f"ntp unicast-server {p['server']}",
    ]

    if p['disable_ipv4_server']:
        lines.append("ntp server disable")
    if p['disable_ipv6_server']:
        lines.append("ntp ipv6 server disable")
    if p.get('source_interface'):
        lines.append(f"ntp server source-interface {p['source_interface']}")

    # Für absent alles mit »undo « versehen
    if p['state'] == 'absent':
        lines = [f"undo {l}" for l in lines]

    return lines

def main():
    module = AnsibleModule(
        argument_spec=dict(
            server               = dict(type='str', required=True),
            source_interface     = dict(type='str'),
            timezone_name        = dict(type='str', default='CET'),
            timezone_offset      = dict(type='int', default=1),
            dst_name             = dict(type='str', default='Sommerzeit'),
            dst_start            = dict(type='str', default='02:00 2025-03-30'),
            dst_end              = dict(type='str', default='03:00 2025-10-26'),
            disable_ipv4_server  = dict(type='bool', default=True),
            disable_ipv6_server  = dict(type='bool', default=True),
            state                = dict(type='str',
                                        choices=['present', 'absent'],
                                        default='present'),
            save_when            = dict(type='str',
                                        choices=['never','changed','always'],
                                        default='changed'),
            backup               = dict(type='bool', default=False),
            backup_path          = dict(type='str'),
        ),
        supports_check_mode=True,
    )

    p        = module.params
    conn     = Connection(module._socket_path)
    running  = vc.load_running_config(conn)

    # Build CLI lines
    cand_lines = build_lines(p)
    body_cmds  = vc.diff_line_match(running, [], cand_lines,
                                    'present', keep_lines=[])  # Elternkontext = Root

    changed_config = bool(body_cmds)

    # Backup-Handling (identisch zu vrp_config)
    backup_changed = False
    backup_path    = None
    if p['backup']:
        cfg_text = '\n'.join(running)
        if p.get('backup_path'):
            bp = p['backup_path']
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            if os.path.isfile(bp):
                with open(bp, 'r', encoding='utf-8', errors='ignore') as f:
                    backup_changed = (f.read() != cfg_text)
            else:
                backup_changed = True
            if backup_changed:
                with open(bp, 'w', encoding='utf-8') as f:
                    f.write(cfg_text)
            backup_path = bp
        else:
            os.makedirs("backups", exist_ok=True)
            fd, backup_path = tempfile.mkstemp(prefix="vrp_ntp_", suffix=".cfg",
                                               dir="backups")
            with os.fdopen(fd, 'w', encoding='utf-8') as tmpfile:
                tmpfile.write(cfg_text)
            backup_changed = True

    changed = changed_config or backup_changed

    if module.check_mode:
        module.exit_json(changed=changed,
                         commands=body_cmds,
                         backup_path=backup_path,
                         diff={'prepared': '\n'.join(body_cmds)})

    cli_cmds, responses = [], []
    if changed_config:
        cli_cmds = ['system-view'] + body_cmds + ['return']
        responses = conn.run_commands(cli_cmds)

        if p['save_when'] in ('always', 'changed'):
            responses += conn.run_commands([{
                'command': 'save',
                'prompt' : '[Y/N]',
                'answer' : 'Y'
            }])

    module.exit_json(changed=changed,
                     commands=cli_cmds,
                     responses=responses,
                     backup_path=backup_path)

if __name__ == '__main__':
    main()
