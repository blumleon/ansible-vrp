#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import to_list

DOCUMENTATION = r'''
---
module: vrp_config
short_description: Verwalten der Gerätekonfiguration auf Huawei-VRP
version_added: "1.1.1"
author: Leon Blum (@blumleon)
description:
  - Fügt Konfigurationszeilen hinzu, entfernt sie oder ersetzt Blöcke
    in der laufenden Konfiguration eines Huawei-VRP-Geräts.
options:
  lines:
    description: Konfigurationszeilen, die angewendet werden sollen.
    type: list
    elements: str
  parents:
    description: Übergeordneter Konfig-Kontext (z. B. C(interface GE1/0/1)).
    type: list
    elements: str
  state:
    description: present / absent / replace.
    type: str
    choices: [present, absent, replace]
    default: present
  match:
    description: Aktuell nur C(line) unterstützt.
    type: str
    choices: [line]
    default: line
  save_when:
    description: Wann C(save) ausgeführt wird.
    type: str
    choices: [never, changed, always]
    default: changed
  backup:
    description: Sichert die Running-Config lokal im C(backups/)-Ordner.
    type: bool
    default: false
'''

# ---------------------------------------------------------------- helpers
def load_running_config(conn):
    raw = conn.run_commands('display current-configuration')[0]
    return to_text(raw, errors='surrogate_or_strict').splitlines()

def build_candidate(parents, lines):
    """parent-Kontext + gewünschte Kinderzeilen"""
    return to_list(parents) + to_list(lines or [])

def find_parent_block(running, parents):
    """liefert (start,end) des parents-Blocks (ohne Zeile end)"""
    if not parents:
        return 0, len(running)
    try:
        start = running.index(parents[0])
    except ValueError:
        return -1, -1
    end = start + 1
    while end < len(running) and running[end].startswith(' '):
        end += 1
    return start, end

def _undo_cmd(line):
    """VRP braucht meist nur das erste Keyword – z. B. 'undo description'"""
    return f"undo {line.split()[0]}"

def diff_line_match(running, parents, candidate_children, state):
    """
    Vergleicht Kinderzeilen ⇒ erzeugt CLI-Kommandos
    (Parents-Zeile selbst bleibt unangetastet!)
    """
    cmds   = []
    start, end = find_parent_block(running, parents)
    block_children = running[start + 1:end] if start >= 0 else []   # ohne parent
    stripped = {l.lstrip() for l in block_children}

    if state == 'replace':
        desired = {l.lstrip() for l in candidate_children}
        for l in stripped - desired:
            cmds.append(_undo_cmd(l))
        for l in desired - stripped:
            cmds.append(l.lstrip())
        return cmds

    # state present / absent
    for raw in candidate_children:
        plain = raw.lstrip()
        if state == 'present' and plain not in stripped:
            cmds.append(plain)
        elif state == 'absent' and plain in stripped:
            cmds.append(_undo_cmd(plain))
    return cmds
# ---------------------------------------------------------------- main
def main():
    module = AnsibleModule(
        argument_spec=dict(
            lines     = dict(type='list', elements='str'),
            parents   = dict(type='list', elements='str'),
            state     = dict(type='str', choices=['present','absent','replace'], default='present'),
            match     = dict(type='str', choices=['line'], default='line'),
            save_when = dict(type='str', choices=['never','changed','always'], default='changed'),
            backup    = dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )

    p       = module.params
    conn    = Connection(module._socket_path)
    running = load_running_config(conn)
    cand    = build_candidate(p['parents'], p['lines'])
    parents = to_list(p['parents'])

    body_cmds = diff_line_match(running, parents, cand[len(parents):], p['state'])
    changed   = bool(body_cmds)

    # ---------- optional Backup
    backup_path = module.backup_local('\n'.join(running)) if p['backup'] else None

    if module.check_mode:
        module.exit_json(changed=changed, commands=body_cmds, backup_path=backup_path)

    cli_cmds = responses = []
    if changed:
        cli_cmds = ['system-view']
        if parents:
            cli_cmds.append(parents[0])
        cli_cmds += body_cmds + ['return', 'return']
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

