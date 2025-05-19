from __future__ import absolute_import, division, print_function
__metaclass__ = type

import re
from ansible.plugins.terminal import TerminalBase
from ansible.errors import AnsibleConnectionFailure

class TerminalModule(TerminalBase):
    # Prompt-Erkennung: VRP-Prompt im User-View: <Name>, im System-View: [Name]
    terminal_stdout_re = [
        re.compile(br"[\r\n]?<[^>\r\n]+> ?$"),   # z.B. <Huawei>
        re.compile(br"[\r\n]?\[[^\]\r\n]+\] ?$")  # z.B. [Huawei]
    ]
    # Fehler-Erkennung: Zeilen, die mit "Error:" beginnen
    terminal_stderr_re = [
        re.compile(br"[\r\n]Error:")
    ]
    # ANSI-Steuersequenzen herausfiltern (optional, falls VRP Farben o.ä. nutzt - i.d.R. nicht der Fall)
    ansi_re = [
        re.compile(br"\x1b\[?[0-9;]*[A-Za-z]")  # generische ANSI Escape-Sequenz
    ]
    
    def on_open_shell(self):
        # Wird aufgerufen, sobald die SSH-Verbindung aufgebaut und der Shell-Prompt erreicht ist.
        # Hier schalten wir Paging ab.
        try:
            # Sende den Befehl zum Deaktivieren der Seitenumbrüche
            self._exec_cli_command(b"screen-length 0 temporary")
        except Exception as err:
            raise AnsibleConnectionFailure(f"Failed to disable paging on VRP device: {err}")
