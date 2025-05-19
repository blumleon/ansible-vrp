#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: vrp_command
version_added: "1.0.0"
author: "Ihr Name (@IhrGitHubHandle)"
short_description: Führt CLI-Befehle auf Huawei VRP Geräten aus
description:
  - Sendet beliebige Befehle an ein Huawei Versatile Routing Platform (VRP) Gerät über die CLI-Verbindung (SSH) und gibt die Ausgaben zurück.
  - Unterstützt die Ausführung mehrerer Befehle sowie das Warten auf bestimmte Bedingungen in der Befehlsausgabe.
options:
  commands:
    description:
      - Liste von CLI-Befehlen, die auf dem VRP-Gerät ausgeführt werden sollen.
      - Jeder Eintrag kann entweder ein einfaches String-Kommando oder ein Dictionary mit den Schlüsseln C(command), C(prompt) und C(answer) sein, um interaktive Bestätigungen zu handhaben.
      - Beispiel für interaktives Kommando: C({"command": "reset saved-configuration", "prompt": "[Y/N]", "answer": "Y"}).
    required: true
    type: list
    elements: raw
  wait_for:
    description:
      - Liste von Bedingungen, die in den Kommando-Ausgaben geprüft werden sollen, bevor das Modul erfolgreich zurückkehrt.
      - Format jeder Bedingung: C(result[index] <operator> <text>), wobei C(index) der 0-basierte Index des Befehls ist.
      - Unterstützte Operatoren: C(contains) (Prüft, ob der Ausgabe-Text den <text> enthält) und C(not contains).
    required: false
    aliases: [ waitfor ]
    type: list
    elements: str
  match:
    description:
      - Legt fest, ob alle oder mindestens eine der Bedingungen aus C(wait_for) erfüllt sein müssen.
    required: false
    type: str
    choices: [ any, all ]
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
  - module: vrp_config (Konfigurations-Module für Huawei VRP)
  - plugin: blumleon.vrp.vrp (Cliconf-Plugin zur Implementierung der CLI-Kommunikation)
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
        prompt: "[Y/N]"    # Der Prompt, auf den gewartet wird
        answer: "Y"       # Antwort, die geschickt wird
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
  sample: ["result[0] contains BGP", "result[1] contains 10.0.0.1"]
msg:
  description: Beschreibende Fehlermeldung im Fehlerfall (z.B. wenn Wartebedingungen nicht erfüllt wurden).
  type: str
'''
  
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError

def run_module():
    module_args = dict(
        commands=dict(type='list', elements='raw', required=True),
        wait_for=dict(type='list', elements='str', aliases=['waitfor']),
        match=dict(type='str', choices=['all', 'any'], default='all'),
        retries=dict(type='int', default=10),
        interval=dict(type='int', default=1),
    )
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
  
    commands = module.params['commands']
    wait_for = module.params.get('wait_for') or []
    match = module.params['match']
    retries = module.params['retries']
    interval = module.params['interval']
  
    # Befehle in Listenform bringen (einfacher String -> Liste mit einem Element)
    if isinstance(commands, str) or not hasattr(commands, '__iter__'):
        commands = [commands]
  
    # Verbindungs-Objekt erhalten (Netconf/Cliconf Verbindung über persistent socket)
    conn = Connection(module._socket_path)
  
    # In Check Mode: keine Befehle wirklich senden, nur Abbruch (da reine Abfragebefehle ohne Config-Änderung, könnte man auch durchlassen)
    if module.check_mode:
        module.exit_json(changed=False)
  
    # Funktion zur Auswertung der Bedingungen
    def conditions_met(outputs):
        """Prüft die Wartebedingungen auf Basis der Ausgabe-Liste."""
        if not wait_for:
            return True
        for cond in wait_for:
            cond = cond.strip()
            # Unterstützte Syntax: "result[i] contains <TEXT>" oder "result[i] not contains <TEXT>"
            # Einfaches Parsen:
            if cond.lower().startswith("result") and " contains " in cond:
                negate = " not contains " in cond.lower()
                # result[0] contains XYZ -> index = 0, substr = "XYZ"
                try:
                    idx_str, _, text_val = cond.partition("contains")
                    idx = int(idx_str.strip()[len("result["): -1])  # Zahl zwischen result[ und ]
                except Exception:
                    continue  # ungültiges Format -> ignorieren
                text_val = text_val.lstrip()
                if text_val.lower().startswith(("\"", "'")):
                    # Entferne Anführungszeichen, falls vorhanden
                    text_val = text_val.strip().strip('\'"')
                # Prüfen ob Bedingung erfüllt
                if negate:
                    # "not contains"
                    if text_val in outputs[idx]:
                        return False  # sollte NICHT enthalten sein, ist aber vorhanden
                else:
                    # "contains"
                    if text_val not in outputs[idx]:
                        return False  # sollte enthalten sein, ist aber nicht vorhanden
            else:
                # Unbekannte Bedingung oder Operator -> ignorieren (oder als nicht erfüllt behandeln)
                return False
        return True if match == 'all' else False
  
    stdout = []
    failed_conditions = []
    # Wiederholtes Ausführen der Befehle bis Bedingungen erfüllt oder max. Versuche erreicht
    for attempt in range(1, retries + 1):
        try:
            # Befehle ausführen über Connection (nutzt unser cliconf Plugin intern)
            outputs = conn.run_commands(commands)
        except ConnectionError as e:
            module.fail_json(msg=f"Fehler beim Ausführen der Befehle: {to_text(e)}")
        # Prüfen der Bedingungen
        if conditions_met(outputs):
            stdout = outputs
            break
        # Wenn match=any, check conditions in loop differently:
        if module.params['match'] == 'any':
            # Bei 'any': wenn *eine* Bedingung erfüllt ist, success -> hier schon abgedeckt, sonst:
            any_met = False
            for cond in wait_for:
                if " not contains " in cond.lower():
                    idx_str, _, text_val = cond.partition("not contains")
                    idx = int(idx_str.strip()[len("result["): -1])
                    text_val = text_val.lstrip().strip('\'"')
                    if text_val not in outputs[idx]:
                        any_met = True
                        break
                elif " contains " in cond.lower():
                    idx_str, _, text_val = cond.partition("contains")
                    idx = int(idx_str.strip()[len("result["): -1])
                    text_val = text_val.lstrip().strip('\'"')
                    if text_val in outputs[idx]:
                        any_met = True
                        break
            if any_met:
                stdout = outputs
                break
        # Noch nicht erfüllt -> ggf. letzter Versuch?
        if attempt < retries:
            # Kurze Pause, dann erneut versuchen
            import time
            time.sleep(interval)
        else:
            # Bedingungen nach letztem Versuch immer noch nicht erfüllt
            stdout = outputs
    else:
        # Schleife ohne break verlassen -> Bedingungen gescheitert
        # Bestimme unerfüllte Bedingungen (grob, ohne Sonderfälle)
        for cond in wait_for:
            cond_low = cond.lower()
            if " contains " in cond_low:
                idx_str, _, text_val = cond.partition("contains")
                idx = int(idx_str.strip()[len("result["): -1])
                text_val = text_val.lstrip().strip('\'"')
                if ((" not contains " in cond_low) and text_val in stdout[idx]) or \
                   ((" not contains " not in cond_low) and text_val not in stdout[idx]):
                    failed_conditions.append(cond)
            else:
                failed_conditions.append(cond)
        module.fail_json(msg="Wartebedingung(en) nicht erfüllt.", failed_conditions=failed_conditions, stdout=stdout, stdout_lines=[out.splitlines() for out in stdout])
  
    # Erfolg: Ergebnisse zurückgeben
    module.exit_json(changed=False, stdout=stdout, stdout_lines=[out.splitlines() for out in stdout])

def main():
    run_module()
