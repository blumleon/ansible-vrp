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
module: vrp_backup
short_description: Saves the running configuration of Huawei VRP devices
version_added: "1.0.0"
author: Leon Blum (@blumleon)
description:
  - Retrieves the current running configuration from a Huawei VRP device and saves it locally on the Ansible controller.
  - If no custom path is provided, the file will be stored automatically in a local C(backups/) directory.
options:
  backup_path:
    description:
      - Optional path (on the Ansible controller) to store the downloaded configuration file.
      - If the file already exists and has the same content, it will not be overwritten and C(changed) will be False.
    type: str
    required: false

notes:
  - This module saves the configuration locally on the controller, not on the device.
  - The configuration is retrieved via the active network connection (e.g., SSH).
  - Paging is automatically disabled through the VRP terminal plugin.

seealso:
  - module: vrp_command
  - module: vrp_config
"""

EXAMPLES = r"""
- name: Save running config to a specific file
  blumleon.vrp.vrp_backup:
    backup_path: /tmp/vrp_config_backup.cfg

- name: Use default path (under backups/)
  blumleon.vrp.vrp_backup: {}
"""

RETURN = r"""
backup_path:
  description: Path to the written configuration file on the controller.
  type: str
  returned: always

changed:
  description: Whether a new file was created or an existing one was updated.
  type: bool
  returned: always
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


if __name__ == "__main__":
    main()
