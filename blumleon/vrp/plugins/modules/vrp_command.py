# Copyright (C) 2025 Leon Blum
# This file is part of the blumleon.vrp Ansible Collection
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

DOCUMENTATION = r"""
---
module: vrp_command
short_description: Execute CLI commands on Huawei VRP devices
version_added: "1.0.0"
author:
  - Leon Blum (@blumleon)
description:
  - Sends arbitrary CLI commands to a Huawei device running VRP and returns their output.
  - Supports multiple commands as well as conditional waiting on command output.
options:
  commands:
    description:
      - List of CLI commands to run.
      - Each entry can be either a plain string or a dictionary with keys C(command), C(prompt), and C(answer).
      - Use dictionaries for interactive commands such as confirmations.
    required: true
    type: list
    elements: raw

  wait_for:
    description:
      - Conditions to wait for in the command output before returning success.
      - 'Example: C(result[0] contains "OK")'
      - 'Or: C(result[1] not contains "Error")'
      - Errors in wait_for expressions may not include precise position hints.
    type: list
    elements: str
    default: []
    aliases: [waitfor]

  match:
    description:
      - Whether C(any) or C(all) conditions in C(wait_for) must be true.
    type: str
    choices: [any, all]
    default: all

  retries:
    description:
      - Maximum number of retries to check the conditions.
    type: int
    default: 10

  interval:
    description:
      - Seconds to wait between retries.
    type: int
    default: 1

notes:
  - Requires C(ansible_connection=ansible.netcommon.network_cli) and C(ansible_network_os=blumleon.vrp.vrp).
  - Automatic paging disablement is handled via the VRP terminal plugin.

seealso:
  - module: vrp_config
"""

EXAMPLES = r"""
- name: Show device version
  blumleon.vrp.vrp_command:
    commands: display version

- name: Query interface and routing information, and check output
  blumleon.vrp.vrp_command:
    commands:
      - display interface brief
      - display ip routing-table
    wait_for:
      - "result[0] contains 'MEth0/0/0'"
      - "result[1] contains '0.0.0.0/0'"
    match: all
"""

RETURN = r"""
changed:
  description: Always false. This module does not report changes, even when prompts are handled.
  type: bool
  returned: always
  sample: false

stdout:
  description: List of raw command outputs as returned by the device.
  type: list
  elements: str
  returned: always

stdout_lines:
  description: List of command outputs split into individual lines.
  type: list
  elements: list
  returned: always
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
    """Check conditions‐Syntax `result[i] (not )?contains TEXT`."""
    if not wait_for:
        return True

    def _check(cond: str) -> bool:
        neg = " not contains " in cond.lower()
        idx, _sep, text = cond.partition("contains")
        try:
            idx = int(idx[idx.find("[") + 1 : idx.find("]")])
        except ValueError:
            return False

        text = text.strip().strip("'\"")
        found = text in outputs[idx]
        return not found if neg else found

    results = [_check(c) for c in wait_for]
    return all(results) if match == "all" else any(results)


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            commands=dict(type="list", elements="raw", required=True),
            wait_for=dict(type="list", elements="str", aliases=["waitfor"], default=[]),
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
            stdout = conn.run_commands(commands)
        except Exception as err:
            module.fail_json(msg=f"CLI execution failed: {to_text(err)}")

        if _conditions_met(stdout, wait_for, match):
            break

        if attempt < retries:
            time.sleep(interval)
    else:
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


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
