#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type
"""
vrp_vlan – erstellt / löscht VLAN-Objekte und vergibt Namen.
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc

def main():
    spec = dict(
        vlan_id    = dict(type='int', required=True, aliases=['id']),
        name       = dict(type='str'),
        state      = dict(type='str', choices=['present','absent'], default='present'),
        save_when  = dict(type='str', choices=['never','changed','always'], default='changed'),
    )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p      = module.params
    conn   = Connection(module._socket_path)

    parents = f"vlan {p['vlan_id']}"

    if p['state'] == 'absent':
        body = []          # wird durch ‚undo vlan X‘ erledigt
        cli  = [f"undo vlan {p['vlan_id']}"]
    else:
        body = [f"name {p['name']}"] if p.get('name') else []
        running = vc.load_running_config(conn)
        body = vc.diff_line_match(running, [parents], body,
                                  state='replace', keep=[])
        cli = ['system-view', parents] + body + ['return','return']

    changed = bool(body) or p['state'] == 'absent'

    if p['save_when'] in ('always','changed') and changed:
        cli += [{
            'command':'save',
            'prompt':'[Y/N]',
            'answer':'Y'
        }]

    if module.check_mode:
        module.exit_json(changed=changed, commands=cli)

    responses = conn.run_commands(cli) if changed else []
    module.exit_json(changed=changed, commands=cli, responses=responses)

if __name__ == '__main__':
    main()
