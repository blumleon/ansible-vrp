#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: vrp_command
version_added: "1.0.0"
author: Ihr Name (@IhrGitHubHandle)
short_description: Führt CLI-Befehle auf Huawei VRP Geräten aus
description:
  - Sendet beliebige Befehle an ein Huawei Versatile Routing Platform (VRP) Gerät über die CLI-Verbindung (SSH) und gibt die Ausgaben zurück.
  - Unterstützt die Ausführung mehrerer Befehle sowie das Warten auf bestimmte Bedingungen in der Befehlsausgabe.
options:
  commands:
    description:
      - Liste von CLI-Befehlen, die auf dem VRP-Gerät ausgeführt werden sollen.
      - Jeder Eintrag kann entweder ein einfaches String-Kommando oder ein Dictionary mit den Schlüsseln C(command), C(prompt) und C(answer) sein, um interaktive Bestätigungen zu handhaben.
      - 'Beispiel für interaktives Kommando: C({"command": "reset saved-configuration", "prompt": "[Y/N]", "answer": "Y"}).'
    required: true
    type: list
    elements: raw
  wait_for:
    description:
      - Liste von Bedingungen, die in den Kommando-Ausgaben geprüft werden sollen, bevor das Modul erfolgreich zurückkehrt.
      - "Format jeder Bedingung: C(result[index] <operator> <text>), wobei C(index) der 0-basierte Index des Befehls ist."
      - "Unterstützte Operatoren: C(contains) (Prüft, ob der Ausgabe-Text den <text> enthält) und C(not contains)."
    required: false
    aliases: [waitfor]
    type: list
    elements: str
  match:
    description:
      - Legt fest, ob alle oder mindestens eine der Bedingungen aus C(wait_for) erfüllt sein müssen.
    required: false
    type: str
    choices:
      - any
      - all
    default: all
  retries:
    description:
      - Anzahl der Versuche, die Befehle auszuführen und die C(wait_for)-Bedingungen zu prüfen, bevor das Modul aufgibt.
    required: false
    type: int
    default: 10
  interval:
    description:
      - Wartezeit in Sekunden zwischen zwei Ausführungsversuchen (wenn C(wait_for) nicht erfüllt ist).
    required: false
    type: int
    default: 1
notes:
  - Dieses Modul muss mit einer ansible.netcommon CLI-Verbindung genutzt werden (C(ansible_connection=ansible.netcommon.network_cli)) und erfordert C(ansible_network_os=blumleon.vrp.vrp) im Inventory.
  - Paging auf dem Gerät wird automatisch durch das Terminal-Plugin deaktiviert, sodass Befehlsausgaben nicht blockiert werden.
seealso:
  - vrp_config
  - blumleon.vrp.vrp
examples: |
  # Beispiel: Anzeigen der Geräteversion und Schnittstellenübersicht
  - hosts: huawei_routers
    gather_facts: no
    connection: ansible.netcommon.network_cli
    vars:
      ansible_network_os: blumleon.vrp.vrp
    tasks:
      - name: Geräteversion abfragen
        blumleon.vrp.vrp_command:
          commands: display version
      - name: Schnittstellenstatus abfragen
        blumleon.vrp.vrp_command:
          commands:
            - display interface brief
            - display ip interface brief
        register: intf_out
      - name: Auswertung - prüfen, ob GigabitEthernet0/0/0 up ist
        blumleon.vrp.vrp_command:
          commands: display interface GigabitEthernet0/0/0
          wait_for:
            - "result[0] contains current state : UP"
          retries: 5
          interval: 2
        register: iface_status
      - debug:
          msg: "Status Ausgabe: {{ intf_out.stdout[0] }}"
'''

EXAMPLES = r'''
# Einfacher Befehl ausführen
- name: Geräte-Name anzeigen
  blumleon.vrp.vrp_command:
    commands: display current-configuration | include sysname

# Mehrere Befehle ausführen und Ergebnisse prüfen
- name: Route und Schnittstellen prüfen
  blumleon.vrp.vrp_command:
    commands:
      - display ip routing-table | include 0.0.0.0
      - display interface brief
    wait_for:
      - "result[0] contains 0.0.0.0/0"
      - "result[1] contains GE0/0/0"
    match: all

# Interaktives Kommando mit Bestätigung ausführen (Factory Reset Beispiel)
- name: Konfiguration zurücksetzen (Bestätigung mit 'Y')
  blumleon.vrp.vrp_command:
    commands:
      - command: reset saved-configuration
        prompt: "[Y/N]"
        answer: "Y"
'''

RETURN = r'''
stdout:
  description: Liste der vollständigen Kommandoausgaben (eine pro ausgeführtem Befehl), wie vom Gerät zurückgegeben.
  type: list
  elements: str
  sample:
    - "Huawei Versatile Routing Platform Software\nVRP (R) software, Version 8.180 (AR2200 V300R003C00SPC200)\n<Ausgabe gekürzt>\n"
    - "Interface                         PHY   Protocol   Description\nEth0/0/0                           up    up         ---\n<Ausgabe gekürzt>\n"
stdout_lines:
  description: Ausgabe der Befehle, zerlegt in Listen von Zeilen (jede Liste entspricht einem Befehl aus stdout).
  type: list
  elements: list
  sample:
    - ["Huawei Versatile Routing Platform Software,", "VRP (R) software, Version 8.180 (AR2200 V300R003C00SPC200)", "..."]
    - ["Interface                         PHY   Protocol   Description", "Eth0/0/0                           up    up         ---", "..."]
failed_conditions:
  description: Liste der C(wait_for)-Bedingungen, die am Ende nicht erfüllt wurden (nur gesetzt, wenn das Modul fehlschlägt).
  type: list
  elements: str
  sample:
    - "result[0] contains BGP"
    - "result[1] contains 10.0.0.1"
msg:
  description: Beschreibende Fehlermeldung im Fehlerfall (z.B. wenn Wartebedingungen nicht erfüllt wurden).
  type: str
'''

import time
from typing import List

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible.module_utils._text import to_text

__all__ = ['main']


def _conditions_met(
    outputs: List[str], wait_for: List[str], match: str = 'all'
) -> bool:
    """Prüft conditions‐Syntax `result[i] (not )?contains TEXT`."""
    if not wait_for:
        return True

    def _check(cond: str) -> bool:
        neg = ' not contains ' in cond.lower()
        idx, _, text = cond.partition('contains')
        try:
            idx = int(idx[idx.find('[') + 1 : idx.find(']')])
        except ValueError:
            return False  # bad syntax

        text = text.strip().strip('\'"')
        found = text in outputs[idx]
        return not found if neg else found

    results = [_check(c) for c in wait_for]
    return all(results) if match == 'all' else any(results)


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            commands=dict(type='list', elements='raw', required=True),
            wait_for=dict(type='list', elements='str', aliases=['waitfor']),
            match=dict(type='str', choices=['any', 'all'], default='all'),
            retries=dict(type='int', default=10),
            interval=dict(type='int', default=1),
        ),
        supports_check_mode=True,
    )

    # ---------------------------------------------------------------- params
    commands = module.params['commands']
    if isinstance(commands, str):
        commands = [commands]

    wait_for = module.params.get('wait_for') or []
    match = module.params['match']
    retries = module.params['retries']
    interval = module.params['interval']

    if module.check_mode:
        module.exit_json(changed=False)

    # ---------------------------------------------------------------- execute
    conn = Connection(module._socket_path)
    stdout: List[str] = []

    for attempt in range(1, retries + 1):
        try:
            stdout = conn.run_commands(commands)  # durch unser Cliconf-Plugin
        except Exception as err:
            module.fail_json(msg=f'CLI execution failed: {to_text(err)}')

        if _conditions_met(stdout, wait_for, match):
            break

        if attempt < retries:
            time.sleep(interval)
    else:  # Schleife ohne »break« → Bedingungen nicht erfüllt
        module.fail_json(
            msg='wait_for condition(s) not met',
            failed_conditions=wait_for,
            stdout=stdout,
            stdout_lines=[o.splitlines() for o in stdout],
        )

    module.exit_json(
        changed=False,
        stdout=stdout,
        stdout_lines=[o.splitlines() for o in stdout],
    )


def main() -> None:  # pragma: no cover
    run_module()


if __name__ == '__main__':  # pragma: no cover
    main()
