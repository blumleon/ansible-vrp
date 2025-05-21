#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type
"""
vrp_interface – konfiguriert ein einzelnes Interface auf Huawei-VRP-Geräten.

• baut die gewünschten CLI-Zeilen über vrp_common.build_interface_lines()
• vergleicht mit Running-Config → erzeugt nur die nötigen Kommandos
• ruft die CLI via network_cli-Connection direkt auf
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

# ---------------------------------------------------------------------------

def _diff_and_build_cmds(conn, parents, cand_children, save_when):
    """
    Ermittelt die Delta-Kommandos und verpackt sie mit system-view /
    return-Kaskade.  Gibt (changed, cli_cmds) zurück.
    """
    running  = vc.load_running_config(conn)
    body_cmd = vc.diff_line_match(running,
                                  parents=[parents],
                                  cand_children=cand_children,
                                  state='replace',      # alles andere wird entfernt
                                  keep=[])
    if not body_cmd:
        return False, []

    # system-view → Parent → Body → 2× return
    cli = ['system-view', parents] + body_cmd + ['return', 'return']
    if save_when in ('always', 'changed'):
        cli += [{
            'command': 'save',
            'prompt' : '[Y/N]',
            'answer' : 'Y'
        }]
    return True, cli

# ---------------------------------------------------------------------------

def main():
    spec = dict(
        name        = dict(type='str', required=True),
        description = dict(type='str'),
        admin_state = dict(type='str', choices=['up', 'down']),
        speed       = dict(type='str'),
        vlan        = dict(type='int'),
        state       = dict(type='str', choices=['present', 'absent'], default='present'),
        save_when   = dict(type='str', choices=['never','changed','always'], default='changed'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p      = module.params
    conn   = Connection(module._socket_path)

    parents = f"interface {p['name']}"
    lines   = vc.build_interface_lines(p)

    if p['state'] == 'absent':
        # Vollständiges Zurücksetzen auf Default
        lines = ['undo description', 'shutdown',
                 'undo speed', 'undo port default vlan']

    changed, cli_cmds = _diff_and_build_cmds(conn, parents, lines, p['save_when'])

    if module.check_mode:
        module.exit_json(changed=changed, commands=cli_cmds)

    responses = conn.run_commands(cli_cmds) if changed else []
    module.exit_json(changed=changed,
                     commands=cli_cmds,
                     responses=responses)

if __name__ == '__main__':
    main()

