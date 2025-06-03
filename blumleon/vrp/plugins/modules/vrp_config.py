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
module: vrp_config
short_description: Idempotente Konfig-Änderungen auf Huawei-VRP
version_added: "1.2.0"
author: Leon Blum (@blumleon)
description:
  - Fügt Zeilen hinzu, entfernt sie oder ersetzt Blöcke in der Running-Config.
  - Gibt nun zusätzlich *changed* zurück, wenn sich beim Backup die Datei-Inhalte ändern.
options:
  parents:
    description:
      - Ein oder mehrere Parent-Kontexte, z. B.
        C("interface GE1/0/1") oder
        C(["ospf 1", "area 0"]).
    type: raw
  lines:
    description: Kinder-Zeilen im Parent-Kontext.
    type: list
    elements: str
  state:
    description: present / absent / replace.
    type: str
    choices: [present, absent, replace]
    default: present
  keep_lines:
    description: Zeilen, die bei C(state=replace) NIE gelöscht werden.
    type: list
    elements: str
  save_when:
    description: Wann C(save) ausgeführt wird.
    type: str
    choices: [never, changed, always]
    default: changed
  backup:
    description: Sichere Running-Config lokal (Verzeichnis C(backups/) oder benutzerdefiniert mit C(backup_path)).
    type: bool
    default: false
  backup_path:
    description: Benutzerdefinierter Pfad für das Backup (inkl. Dateiname).
    type: str
    required: false
'''

def main():
    module = AnsibleModule(
        argument_spec=dict(
            lines        = dict(type='list', elements='str'),
            parents      = dict(type='raw'),
            state        = dict(type='str', choices=['present','absent','replace'], default='present'),
            keep_lines   = dict(type='list', elements='str', default=[]),
            save_when    = dict(type='str', choices=['never','changed','always'], default='changed'),
            backup       = dict(type='bool', default=False),
            backup_path  = dict(type='str', required=False),
        ),
        supports_check_mode=True,
    )

    p        = module.params
    conn     = Connection(module._socket_path)
    running  = vc.load_running_config(conn)
    parents  = vc.to_parents(p['parents'])
    cand     = vc.build_candidate(parents, p['lines'])

    body_cmds = vc.diff_line_match(running,
                                   parents,
                                   cand[len(parents):],
                                   p['state'],
                                   p['keep_lines'])

    # 1) Hat sich die Konfiguration geändert?
    changed_config = bool(body_cmds)

    # 2) Wurde beim Backup tatsächlich eine neue bzw. geänderte Datei geschrieben?
    backup_changed = False
    backup_path    = None

    if p['backup']:
        cfg_text = '\n'.join(running)

        if p.get('backup_path'):
            user_path = p['backup_path']
            # Verzeichnis sicherstellen
            os.makedirs(os.path.dirname(user_path), exist_ok=True)

            # Inhalt vergleichen, falls Datei bereits existiert
            if os.path.isfile(user_path):
                with open(user_path, 'r', encoding='utf-8', errors='ignore') as f:
                    backup_changed = (f.read() != cfg_text)
            else:
                backup_changed = True  # Erstellt neue Datei

            # Nur schreiben, wenn sich etwas geändert hat
            if backup_changed:
                with open(user_path, 'w', encoding='utf-8') as f:
                    f.write(cfg_text)
            backup_path = user_path
        else:
            # Automatischer Temp‑Dateiname im backups/‑Ordner – immer "neu", daher changed = True
            os.makedirs("backups", exist_ok=True)
            fd, backup_path = tempfile.mkstemp(prefix="vrp_config_", suffix=".cfg", dir="backups")
            with os.fdopen(fd, 'w', encoding='utf-8') as tmpfile:
                tmpfile.write(cfg_text)
            backup_changed = True

    # Endgültiger changed‑Wert: Konfig‑Änderung ODER geändertes Backup
    changed = changed_config or backup_changed

    if module.check_mode:
        module.exit_json(changed=changed,
                         commands=body_cmds,
                         backup_path=backup_path,
                         diff={'prepared': '\n'.join(body_cmds)})

    cli_cmds, responses = [], []
    if changed_config:
        cli_cmds = ['system-view'] + parents + body_cmds + ['return'] * (len(parents)+1)
        responses = conn.run_commands(cli_cmds)

        if p['save_when'] in ('always', 'changed'):
            responses += conn.run_commands([
                {
                    'command': 'save',
                    'prompt' : '[Y/N]',
                    'answer' : 'Y'
                }
            ])

    module.exit_json(changed=changed,
                     commands=cli_cmds,
                     responses=responses,
                     backup_path=backup_path)

if __name__ == '__main__':
    main()

