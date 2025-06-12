#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: vrp_command
short_description: Führt CLI-Befehle auf Huawei-VRP-Geräten aus
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Sendet beliebige Befehle an ein Gerät mit Huawei Versatile Routing Platform (VRP)
    über eine CLI-Verbindung (SSH) und gibt die Ausgaben zurück.
  - Unterstützt die Ausführung mehrerer Befehle sowie das Warten auf Bedingungen
    in der Befehlsausgabe.
options:
  commands:
    description:
      - Liste der CLI-Befehle, die ausgeführt werden sollen.
      - Jeder Eintrag kann ein einfacher String oder ein Dictionary sein,
        das die Schlüssel C(command), C(prompt) und C(answer) enthält.
      - "Beispiel: C({'command': 'reset saved-configuration', 'prompt': '[Y/N]', 'answer': 'Y'})"
    required: true
    type: list
    elements: raw
  wait_for:
    description:
      - Bedingungen, die in den Ausgaben geprüft werden, bevor das Modul erfolgreich zurückkehrt.
      - "Syntax z. B.: C(result[0] contains <Text>) oder C(result[1] not contains <Text>)."
    aliases: [waitfor]
    type: list
    elements: str
  match:
    description:
      - Gibt an, ob C(any) oder C(all) der C(wait_for)-Bedingungen erfüllt sein müssen.
    type: str
    choices: [any, all]
    default: all
  retries:
    description:
      - Maximale Anzahl von Versuchen, die Bedingungen zu erfüllen.
    type: int
    default: 10
  interval:
    description:
      - Sekunden zwischen zwei Versuchen.
    type: int
    default: 1
notes:
  - "Benötigt C(ansible_connection=ansible.netcommon.network_cli) und C(ansible_network_os=blumleon.vrp.vrp)."
  - "Paging wird automatisch durch das Terminal-Plugin deaktiviert."
seealso:
  - module: vrp_config
  - cliconf: blumleon.vrp.vrp
examples: |
  # Geräteversion anzeigen
  - hosts: huawei_switch
    gather_facts: no
    connection: ansible.netcommon.network_cli
    vars:
      ansible_network_os: blumleon.vrp.vrp
    tasks:
      - name: Version ausgeben
        blumleon.vrp.vrp_command:
          commands: display version

  # Interfaces & Routing abrufen und Bedingungen prüfen
  - hosts: huawei_switch
    gather_facts: no
    connection: ansible.netcommon.network_cli
    vars:
      ansible_network_os: blumleon.vrp.vrp
    tasks:
      - name: Interfaces & Routing
        blumleon.vrp.vrp_command:
          commands:
            - display interface brief
            - display ip routing-table
          wait_for:
            - "result[0] contains MEth0/0/0"
            - "result[1] contains 0.0.0.0/0"
          match: all
"""

import time
from typing import List

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible.module_utils._text import to_text

__all__ = ["main"]


def _conditions_met(
    outputs: List[str], wait_for: List[str], match: str = "all"
) -> bool:
    """Prüft conditions‐Syntax `result[i] (not )?contains TEXT`."""
    if not wait_for:
        return True

    def _check(cond: str) -> bool:
        neg = " not contains " in cond.lower()
        idx, _, text = cond.partition("contains")
        try:
            idx = int(idx[idx.find("[") + 1 : idx.find("]")])
        except ValueError:
            return False  # bad syntax

        text = text.strip().strip("'\"")
        found = text in outputs[idx]
        return not found if neg else found

    results = [_check(c) for c in wait_for]
    return all(results) if match == "all" else any(results)


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            commands=dict(type="list", elements="raw", required=True),
            wait_for=dict(type="list", elements="str", aliases=["waitfor"]),
            match=dict(type="str", choices=["any", "all"], default="all"),
            retries=dict(type="int", default=10),
            interval=dict(type="int", default=1),
        ),
        supports_check_mode=True,
    )

    # ---------------------------------------------------------------- params
    commands = module.params["commands"]
    if isinstance(commands, str):
        commands = [commands]

    wait_for = module.params.get("wait_for") or []
    match = module.params["match"]
    retries = module.params["retries"]
    interval = module.params["interval"]

    if module.check_mode:
        module.exit_json(changed=False)

    # ---------------------------------------------------------------- execute
    conn = Connection(module._socket_path)
    stdout: List[str] = []

    for attempt in range(1, retries + 1):
        try:
            stdout = conn.run_commands(commands)  # durch unser Cliconf-Plugin
        except Exception as err:
            module.fail_json(msg=f"CLI execution failed: {to_text(err)}")

        if _conditions_met(stdout, wait_for, match):
            break

        if attempt < retries:
            time.sleep(interval)
    else:  # Schleife ohne »break« → Bedingungen nicht erfüllt
        module.fail_json(
            msg="wait_for condition(s) not met",
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


if __name__ == "__main__":  # pragma: no cover
    main()
