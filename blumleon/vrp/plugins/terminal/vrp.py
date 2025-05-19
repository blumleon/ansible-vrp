#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Terminal-Plugin: sorgt für zuverlässigen Prompt-Match und schaltet Paging ab."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import re
from ansible.plugins.terminal import TerminalBase
from ansible.errors import AnsibleConnectionFailure


class TerminalModule(TerminalBase):
    # VRP-Prompts: User-View <Hostname>, System-View [Hostname]
    terminal_stdout_re = [
        re.compile(br'(?:\r\n)?<[^>\r\n]+>\s?$'),
        re.compile(br'(?:\r\n)?\[[^\]\r\n]+\]\s?$'),
    ]

    # Fehlermeldungen beginnen i. d. R. mit »Error:«
    terminal_stderr_re = [re.compile(br'(?:\r\n)?Error:')]

    # (Optionales) Herausfiltern von ANSI-Sequences
    ansi_re = [re.compile(br'\x1b\[[0-9;]*[A-Za-z]')]

    def on_open_shell(self) -> None:
        """Shell erreicht → Paging temporär deaktivieren."""
        try:
            self._exec_cli_command(b'screen-length 0 temporary')
            # Einige VRP-Releases kennen `screen-width` nicht – deshalb weggelassen.
        except Exception as err:  # pragma: no cover
            raise AnsibleConnectionFailure(f'Failed to disable paging: {err}')
