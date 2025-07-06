# Copyright (C) 2025 Leon Blum
# This file is part of the blumleon.vrp Ansible Collection
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Terminal plugin for Huawei VRP devices – ensures prompt recognition and disables paging."""

import re

from ansible.errors import AnsibleConnectionFailure
from ansible.plugins.terminal import TerminalBase


class TerminalModule(TerminalBase):
    # VRP-Prompts: User-View <Hostname>, System-View [Hostname]
    terminal_stdout_re = [
        re.compile(br"(?:\r\n)?<[^>\r\n]+>\s?$"),
        re.compile(br"(?:\r\n)?\[[^\]\r\n]+\]\s?$"),
    ]

    # Error messages usually begin with "Error:"
    terminal_stderr_re = [re.compile(br"(?:\r\n)?Error:")]

    # (Optional) strip of ANSI sequences
    ansi_re = [re.compile(br"\x1b\[[0-9;]*[A-Za-z]")]

    def on_open_shell(self) -> None:
        try:
            self._exec_cli_command(b"screen-length 0 temporary")
            # Some VRP releases do not know `screen-width` - intentionally omitted.
        except Exception as err:  # pragma: no cover
            raise AnsibleConnectionFailure(f"Failed to disable paging: {err}")
