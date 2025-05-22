#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type
"""
vrp_interface – idempotente Interface-Konfiguration (L1 & L2) auf Huawei-VRP.
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

# ---------------------------------------------------------------------------

def _validate_params(module, p):
    mode = p.get("port_mode")
    if mode == "access":
        if p.get("trunk_vlans") or p.get("native_vlan"):
            module.fail_json(msg="trunk_vlans / native_vlan dürfen bei port_mode=access nicht gesetzt sein")
    if mode in ("trunk", "hybrid") and p.get("vlan") is not None:
        module.fail_json(msg="Parameter 'vlan' ist nur bei port_mode=access erlaubt")

def _diff_and_build(conn, parents, body, save_when):
    running  = vc.load_running_config(conn)
    cmds_body = vc.diff_line_match(running, [parents], body,
                                   state='replace', keep=[])
    if not cmds_body:
        return False, []
    cli = ['system-view', parents] + cmds_body + ['return', 'return']
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
        # ---------- Basis
        name         = dict(type='str', required=True),
        admin_state  = dict(type='str', choices=['up','down']),
        description  = dict(type='str'),
        speed        = dict(type='str'),
        mtu          = dict(type='int'),
        # ---------- L2
        port_mode    = dict(type='str', choices=['access','trunk','hybrid']),
        vlan         = dict(type='int'),
        trunk_vlans  = dict(type='str'),
        native_vlan  = dict(type='int'),
        # ---------- Meta
        state        = dict(type='str', choices=['present','absent'], default='present'),
        save_when    = dict(type='str', choices=['never','changed','always'], default='changed'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p      = module.params
    _validate_params(module, p)

    conn    = Connection(module._socket_path)
    parents = f"interface {p['name']}"

    if p['state'] == 'absent':
        # vollständiger Reset – alles rückgängig
        body = ['undo description', 'shutdown', 'undo speed', 'undo mtu',
                'undo port link-type', 'undo port default vlan',
                'undo port trunk allow-pass vlan', 'undo port trunk pvid vlan',
                'undo port hybrid allow-pass vlan']
    else:
        body = vc.build_interface_lines(p)

    changed, cli_cmds = _diff_and_build(conn, parents, body, p['save_when'])

    if module.check_mode:
        module.exit_json(changed=changed, commands=cli_cmds)

    responses = conn.run_commands(cli_cmds) if changed else []
    module.exit_json(changed=changed,
                     commands=cli_cmds,
                     responses=responses)

if __name__ == '__main__':
    main()
