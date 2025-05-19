from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
author: "Ihr Name (@IhrGitHubHandle)"
name: vrp
short_description: Cliconf-Plugin für Huawei VRP Geräte
description:
  - Dieses Plugin bietet eine Abstraktionsschicht für das Senden und Empfangen von CLI-Befehlen auf Huawei VRP Netzwerkgeräten.
  - Es implementiert Methoden, um die laufende Konfiguration auszulesen und CLI-Befehle auszuführen.
notes:
  - Wird automatisch von Ansible geladen, wenn C(ansible_network_os=blumleon.vrp.vrp) eingestellt ist und C(ansible_connection=ansible.netcommon.network_cli) verwendet wird.
'''  # Hinweis: Cliconf-Plugins erscheinen nicht immer im Doku-Format, aber wir dokumentieren hier dennoch.

import re
import json
from ansible.module_utils._text import to_text
from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible.errors import AnsibleConnectionFailure
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import to_list

class Cliconf(CliconfBase):
    """Cliconf-Implementierung für Huawei VRP."""
    
    def get_device_info(self):
        """Liest Geräteinformationen (OS, Version, Modell, Hostname) aus."""
        device_info = {'network_os': 'vrp'}
        # 'display version' ausführen und Ergebnis parsen
        reply = self.get('display version')
        data = to_text(reply, errors='surrogate_or_strict').strip()
        # Version extrahieren (nach "Version")
        match = re.search(r'Version\s+(\S+)', data)
        if match:
            device_info['network_os_version'] = match.group(1).strip(',')
        # Modell extrahieren (Zeile beginnt mit "Huawei")
        match = re.search(r'^Huawei\s+(\S+)', data, re.M)
        if match:
            device_info['network_os_model'] = match.group(1)
        # Hostname extrahieren (Zeile mit "uptime")
        match = re.search(r'^(?:HUAWEI|Huawei)\s+(\S+)\s+uptime', data, re.M)
        if match:
            device_info['network_os_hostname'] = match.group(1)
        return device_info

    @enable_mode
    def get_config(self, source='running', flags=None, format='text'):
        """Liefert die laufende Konfiguration des Geräts zurück."""
        if source not in ('running',):
            # Nur running-config wird unterstützt
            return self.invalid_params(f"fetching configuration from {source} is not supported")
        # Paging sicherheitshalber deaktivieren (sollte bereits TerminalPlugin tun)
        cmd = 'display current-configuration'
        return self.send_command(cmd)
    
    def get(self, command, prompt=None, answer=None, sendonly=False, newline=True, check_all=False):
        """Hilfsmethode: Führt einen einzelnen Befehl aus und gibt die rohe Ausgabe zurück."""
        # Delegiert an send_command der Basisklasse
        return self.send_command(command, prompt=prompt, answer=answer, sendonly=sendonly, newline=newline, check_all=check_all)
    
    def get_capabilities(self):
        """Gibt die Fähigkeiten/Features des Geräts im JSON-Format zurück."""
        result = super(Cliconf, self).get_capabilities()  # Basisklasse liefert Dict mit capabilities
        return json.dumps(result)
    
    @enable_mode
    def edit_config(self, commands=None, commit=False):
        """Wechselt in den Konfigurationsmodus, führt Kommandos aus und verlässt den Modus wieder."""
        # Hinweis: Für Config-Module gedacht. Hier nicht ausführlich implementiert.
        if commands is None:
            return []
        responses = []
        # In VRP: Konfigurationsmodus betreten mit "system-view", verlassen mit "return"
        cmds = ['system-view'] + to_list(commands) + ['return']
        for cmd in cmds:
            responses.append(self.send_command(cmd))
        return responses[1:-1]  # ohne die Umschalt-Kommandos
    
    def run_commands(self, commands=None, check_rc=True):
        """Führt eine Liste von Befehlen auf dem Gerät aus und gibt die Liste der Ausgaben zurück."""
        if commands is None:
            raise ValueError("'commands' value is required")
        responses = []
        for cmd in to_list(commands):
            if isinstance(cmd, dict):
                # Interaktives Kommando mit Prompt/Antwort
                command = cmd.get('command')
                prompt = cmd.get('prompt')
                answer = cmd.get('answer')
                # 'newline' steuern: i.d.R. True, außer wenn prompt bereits durch device gestellt?
                newline = cmd.get('newline', True)
                if not command:
                    continue
                # Sende den Befehl, warte auf prompt und antworte
                out = self.send_command(command, prompt=prompt, answer=answer, sendonly=False, newline=newline)
            else:
                # Einfacher Befehl
                out = self.send_command(cmd, prompt=None, answer=None)
            responses.append(to_text(out, errors='surrogate_or_strict'))
        return responses
