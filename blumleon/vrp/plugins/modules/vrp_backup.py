#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Einfaches Backup-Modul: sichert die Running-Config."""

from __future__ import annotations

__metaclass__ = type

DOCUMENTATION = r"""
---
module: vrp_backup
short_description: Sichert die Running-Config von Huawei-VRP-Geräten
version_added: "1.4.0"
author: Leon Blum (@blumleon)
description:
  - Lädt die aktuelle Running-Config des Geräts herunter und legt sie lokal ab.
options:
  backup_path:
    description: Benutzerdefinierter Zielpfad inkl. Dateiname.
    type: str
"""

EXAMPLES = r"""
- name: Config sichern
  blumleon.vrp.vrp_backup:
    backup_path: backups/before_upgrade.cfg
"""

RETURN = r"""
backup_path:
  description: Pfad der geschriebenen Datei.
  type: str
changed:
  description: Ob die Datei neu oder geändert wurde.
  type: bool
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(backup_path=dict(type="str")),
        supports_check_mode=True,
    )

    conn = Connection(module._socket_path)
    changed, path = vc.backup_config(
        conn,
        do_backup=True,
        user_path=module.params.get("backup_path"),
        prefix="vrp_",
    )

    module.exit_json(changed=changed, backup_path=path)


if __name__ == "__main__":  # pragma: no cover
    main()
