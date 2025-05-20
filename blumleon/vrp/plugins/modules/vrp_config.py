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
version_added: "1.0.0"
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
    description: Übergeordneter Konfig-Kontext (z. B. Interface-Block).
    type: list
    elements: str
  state:
    description: Ob Zeilen vorhanden sein sollen oder entfernt werden.
    type: str
    choices: [present, absent, replace]
    default: present
  match:
    description: Vergleichsstrategie mit der laufenden Konfiguration.
    type: str
    choices: [line, strict, exact]
    default: line
  save_when:
    description: Wann die Konfiguration gespeichert wird.
    type: str
    choices: [never, changed, always]
    default: changed
  backup:
    description: Erstellt eine Sicherungs­kopie der laufenden Konfiguration.
    type: bool
    default: false
'''

EXAMPLES = r'''
# Beschreibung an Interface setzen
- blumleon.vrp.vrp_config:
    parents: interface GigabitEthernet0/0/0
    lines: description Ansible_Test
'''

RETURN = r'''
commands:
  description: Liste der ausgeführten CLI-Kommandos.
  type: list
  elements: str
'''

# ---------------------------------------------------------------- helpers
def load_running_config(conn):
    """holt running-config als Zeilenliste"""
    out = conn.run_commands('display current-configuration')[0]
    return to_text(out, errors='surrogate_or_strict').splitlines()


def build_candidate(parents, lines):
    """parents-Kontext + gewünschte Zeilen"""
    return to_list(parents) + to_list(lines or [])


def find_parent_block(running, parents):
    """liefert Zeilen­bereich des parents-Blocks"""
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


def diff_line_match(running, parents, candidate_children, state):
    """
    vergleicht kinder-Zeilen (ohne führende Spaces) ⇒ erzeugt CLI-Kommandos
    """
    cmds = []
    start, end = find_parent_block(running, parents)
    block_stripped = {l.lstrip() for l in (running[start:end] if start >= 0 else [])}

    for raw in candidate_children:
        plain = raw.lstrip()
        if state == 'present' and plain not in block_stripped:
            cmds.append(plain)
        elif state == 'absent' and plain in block_stripped:
            cmds.append(f'undo {plain}')
    return cmds


# ---------------------------------------------------------------- main
def main():
    module = AnsibleModule(
        argument_spec=dict(
            lines=dict(type='list', elements='str'),
            parents=dict(type='list', elements='str'),
            state=dict(type='str', choices=['present', 'absent', 'replace'], default='present'),
            match=dict(type='str', choices=['line', 'strict', 'exact'], default='line'),
            save_when=dict(type='str', choices=['never', 'changed', 'always'], default='changed'),
            backup=dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )

    p     = module.params
    conn  = Connection(module._socket_path)
    run   = load_running_config(conn)
    cand  = build_candidate(p['parents'], p['lines'])

    if p['match'] != 'line' or p['state'] == 'replace':
        module.fail_json(msg='Derzeit nur match=line & state present/absent implementiert')

    parents   = to_list(p['parents'])
    body_cmds = diff_line_match(run, parents, cand[len(parents):], p['state'])
    changed   = bool(body_cmds)

    if module.check_mode:
        module.exit_json(changed=changed, commands=body_cmds)

    cli_cmds, responses = [], []
    if changed:
        cli_cmds = ['system-view']
        if parents:
            cli_cmds.append(parents[0])
        cli_cmds += body_cmds
        cli_cmds += ['return', 'return']

        responses = conn.run_commands(cli_cmds)

        if p['save_when'] in ('always', 'changed'):
            responses += conn.run_commands([{
                'command': 'save',
                'prompt' : '[Y/N]',
                'answer' : 'Y'
            }])

    module.exit_json(changed=changed, commands=cli_cmds, responses=responses)


if __name__ == '__main__':
    main()
