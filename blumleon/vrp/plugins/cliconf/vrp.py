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
name: vrp
short_description: CLI connection plugin for Huawei VRP-based devices
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Provides a CLI abstraction for Huawei switches running
    Versatile Routing Platform (VRP).
  - Implements the methods C(get), C(get_config), C(edit_config)
    and C(run_commands) to support modules like
    M(blumleon.vrp.vrp_command).
notes:
  - Automatically loaded when
    C(ansible_network_os=blumleon.vrp.vrp) and
    C(ansible_connection=ansible.netcommon.network_cli) are set.
seealso:
  - module: vrp_command
"""

import json
import re
from typing import List, Union

from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import (
    to_list,
)
from ansible.errors import AnsibleError
from ansible.module_utils._text import to_text


class Cliconf(CliconfBase):
    """CLI context for VRP devices."""

    # ------------------------------------------------------------------ helpers
    def _send(self, cmd: str, **kwargs) -> str:
        """Unique wrapper around `self.send_command`."""
        return to_text(self.send_command(cmd, **kwargs), errors="surrogate_or_strict")

    # ---------------------------------------------------------------- single-GET
    def get(self, command, **kwargs):
        """Compatible single version (requires CliconfBase)."""
        return self._send(command, **kwargs)

    # ---------------------------------------------------------------- device-info
    def get_device_info(self) -> dict:
        """Reads version, model & hostname from `display version`."""
        data = self._send("display version")
        info = {"network_os": "vrp"}

        if m := re.search(r"Version +([\w\.]+)", data):
            info["network_os_version"] = m.group(1).rstrip(",")

        if m := re.search(r"^Huawei +(\S+)", data, re.M):
            info["network_os_model"] = m.group(1)

        if m := re.search(r"^\S+ uptime is", data, re.M):
            info["network_os_hostname"] = m.group(0).split()[0]

        return info

    # -------------------------------------------------------------- config ops
    @enable_mode
    def get_config(self, source="running", flags=None, format="text"):
        if source != "running":
            raise AnsibleError("Only running-config is supported on VRP")
        return self._send("display current-configuration")

    @enable_mode
    def edit_config(self, commands=None, commit=False):
        """Simple Edit-Config: system-view → Commands → return."""
        if not commands:
            return []
        cmds = ["system-view"] + to_list(commands) + ["return"]
        return [self._send(c) for c in cmds][1:-1]

    # ---------------------------------------------------------------- commands
    def run_commands(
        self, commands: Union[str, List[Union[str, dict]]], check_rc=True
    ) -> List[str]:
        """API that is called by the `vrp_command` module."""
        if not commands:
            raise AnsibleError("'commands' argument is required")

        results = []
        for item in to_list(commands):
            if isinstance(item, dict):
                cmd = item.get("command")
                if not cmd:
                    raise AnsibleError("'command' key missing in dict entry")

                results.append(
                    self._send(
                        cmd,
                        prompt=item.get("prompt"),
                        answer=item.get("answer"),
                        newline=item.get("newline", True),
                    )
                )
            else:
                results.append(self._send(item))
        return results

    # ---------------------------------------------------------------- misc
    def get_capabilities(self) -> str:
        """For `ansible-doc -t cliconf blumleon.vrp.vrp`."""
        return json.dumps(super().get_capabilities())
