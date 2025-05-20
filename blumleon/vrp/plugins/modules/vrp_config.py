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
short_description: Idempotente Konfig-Änderungen auf Huawei-VRP
version_added: "1.2.0"
author: Leon Blum (@blumleon)
description:
  - Fügt Zeilen hinzu, entfernt sie oder ersetzt Blöcke in der Running-Config.
options:
  parents:
    description:
      - Ein oder mehrere Parent-Kontexte, z. B.
        C("interface GE1/0/1") oder
        C(["ospf 1", "area 0"]).
    type: raw               # str ODER list
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
    description: Sichere Running-Config lokal (Verzeichnis C(backups/)).
    type: bool
    default: false
'''

# ---------------------------------------------------------------- helpers
def load_running_config(conn):
    raw = conn.run_commands('display current-configuration')[0]
    return to_text(raw, errors='surrogate_or_strict').splitlines()

def to_parents(obj):
    """str -> [str] | list -> list"""
    return [obj] if isinstance(obj, str) else to_list(obj)

def build_candidate(parents, lines):
    return to_parents(parents) + to_list(lines or [])

def find_parent_block(running, parents):
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
    return f"undo {line.split()[0]}"

def diff_line_match(running, parents, cand_children, state, keep):
    cmds   = []
    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1:end] if start >= 0 else []
    stripped = {l.lstrip() for l in blk_children}

    if state == 'replace':
        desired = sorted({l.lstrip() for l in cand_children})
        removals = stripped - set(desired) - set(keep)
        for l in sorted(removals):
            cmds.append(_undo_cmd(l))
        for l in desired:
            if l not in stripped:
                cmds.append(l)
        return cmds

    # state present / absent
    for raw in cand_children:
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
            parents   = dict(type='raw'),
            state     = dict(type='str', choices=['present','absent','replace'], default='present'),
            keep_lines= dict(type='list', elements='str', default=[]),
            save_when = dict(type='str', choices=['never','changed','always'], default='changed'),
            backup    = dict(type='bool', default=False),
        ),
        supports_check_mode=True,
    )

    p        = module.params
    conn     = Connection(module._socket_path)
    running  = load_running_config(conn)
    parents  = to_parents(p['parents'])
    cand     = build_candidate(parents, p['lines'])

    body_cmds = diff_line_match(running,
                                parents,
                                cand[len(parents):],
                                p['state'],
                                p['keep_lines'])
    changed   = bool(body_cmds)

    # ---------- optional Backup
    backup_path = module.backup_local('\n'.join(running)) if p['backup'] else None

    # ---------- Check-Mode mit Diff-Ausgabe
    if module.check_mode:
        module.exit_json(changed=changed,
                         commands=body_cmds,
                         backup_path=backup_path,
                         diff={'prepared': '\n'.join(body_cmds)})

    # ---------- Apply
    cli_cmds, responses = [], []
    if changed:
        # system-view → alle Parents → Body → Return-Cascade
        cli_cmds = ['system-view'] + parents + body_cmds + ['return'] * (len(parents)+1)
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

