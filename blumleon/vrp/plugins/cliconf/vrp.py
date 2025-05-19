#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Cliconf-Plugin für Huawei VRP (AR-/CE-/CloudEngine-Familien)."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import re
from typing import List, Union

from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import to_list
from ansible.errors import AnsibleError
from ansible.module_utils._text import to_text


class Cliconf(CliconfBase):
    """CLI-Kontext für VRP-Geräte."""

    # ------------------------------------------------------------------ helpers
    def _send(self, cmd: str, **kwargs) -> str:
        """Einmaliger Wrapper rund um `self.send_command`."""
        return to_text(
            self.send_command(cmd, **kwargs), errors='surrogate_or_strict'
        )

    # ---------------------------------------------------------------- single-GET (Pflichtmethode)
    def get(self, command, **kwargs):
        """Kompatible Einzelausführung (erfordert CliconfBase)."""
        return self._send(command, **kwargs)

    # ---------------------------------------------------------------- device-info
    def get_device_info(self) -> dict:
        """Liest Version, Modell & Hostname aus `display version`."""
        data = self._send('display version')
        info = {'network_os': 'vrp'}

        if m := re.search(r'Version +([\w\.]+)', data):
            info['network_os_version'] = m.group(1).rstrip(',')

        if m := re.search(r'^Huawei +(\S+)', data, re.M):
            info['network_os_model'] = m.group(1)

        if m := re.search(r'^\S+ uptime is', data, re.M):
            info['network_os_hostname'] = m.group(0).split()[0]

        return info

    # -------------------------------------------------------------- config ops
    @enable_mode
    def get_config(self, source='running', flags=None, format='text'):
        if source != 'running':
            raise AnsibleError('Only running-config is supported on VRP')
        return self._send('display current-configuration')

    @enable_mode
    def edit_config(self, commands=None, commit=False):
        """Einfaches Edit-Config: system-view → Kommandos → return."""
        if not commands:
            return []
        cmds = ['system-view'] + to_list(commands) + ['return']
        return [self._send(c) for c in cmds][1:-1]  # ohne Wechsel-Kommandos

    # ---------------------------------------------------------------- commands
    def run_commands(
        self, commands: Union[str, List[Union[str, dict]]], check_rc=True
    ) -> List[str]:
        """API, die vom Modul `vrp_command` aufgerufen wird."""
        if not commands:
            raise AnsibleError("'commands' argument is required")

        results = []
        for item in to_list(commands):
            if isinstance(item, dict):
                cmd = item.get('command')
                if not cmd:
                    raise AnsibleError("'command' key missing in dict entry")

                results.append(
                    self._send(
                        cmd,
                        prompt=item.get('prompt'),
                        answer=item.get('answer'),
                        newline=item.get('newline', True),
                    )
                )
            else:
                results.append(self._send(item))
        return results

    # ---------------------------------------------------------------- misc
    def get_capabilities(self) -> str:
        """Für `ansible-doc -t cliconf blumleon.vrp.vrp`."""
        return json.dumps(super().get_capabilities())

