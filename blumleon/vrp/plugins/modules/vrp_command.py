#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = '''
---
module: vrp_command
short_description: Run commands on Huawei VRP devices
description:
  - Sends arbitrary commands to Huawei VRP devices using the network_cli connection.
options:
  commands:
    description: List of commands to send to the device.
    required: true
    type: list
    elements: str
author:
  - Dein Name (@deinHandle)
'''

EXAMPLES = '''
- name: Run display version
  blumleon.vrp.vrp_command:
    commands:
      - display version
'''

RETURN = '''
stdout:
  description: Output from the device for each command
  type: list
  elements: str
  returned: always
'''

def main():
    argument_spec = dict(
        commands=dict(type='list', elements='str', required=True)
    )
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Hier: Später die Netcommon/Basisklassen nutzen!
    # Zum Start: Simulierte Ausgabe
    results = []
    for cmd in module.params['commands']:
        results.append(f"SIMULATED OUTPUT: {cmd}")

    module.exit_json(changed=False, stdout=results)

if __name__ == '__main__':
    main()
