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
module: vrp_ntp
short_description: Configure NTP server, timezone, and daylight saving time on Huawei VRP
version_added: "2.14.0"
author: Leon Blum (@blumleon)
description:
  - Configures an NTP unicast server, timezone settings, and daylight saving time on Huawei VRP devices.
  - Optionally disables the built-in NTP server and stores the configuration locally.
  - The configuration is applied globally (not per interface).
options:
  server:
    description:
      - IP address or hostname of the NTP server.
    type: str
    required: true

  source_interface:
    description:
      - Optional source interface for outbound NTP packets.
    type: str

  timezone_name:
    description:
      - Name of the timezone.
    type: str
    default: CET

  timezone_offset:
    description:
      - Offset in hours from UTC (e.g., C(1) for UTC+1).
    type: int
    default: 1

  dst_name:
    description:
      - Name used for daylight saving time.
    type: str

  dst_start:
    description:
      - Start time of DST in the format C(HH:MM YYYY-MM-DD).
      - If omitted, no daylight-saving-time configuration is applied.
    type: str

  dst_end:
    description:
      - End time of DST in the format C(HH:MM YYYY-MM-DD).
      - Must be provided together with C(dst_start).
    type: str

  dst_offset:
    description:
      - Time offset applied during DST (e.g., C(01:00)).
    type: str

  manage_timezone:
    description:
      - Whether to configure timezone and daylight-saving settings.
      - If omitted, timezone is configured only when C(state=present) and relevant parameters are provided.
    type: bool

  disable_ipv4_server:
    description:
      - Whether to disable the device's built-in IPv4 NTP server.
    type: bool
    default: true

  disable_ipv6_server:
    description:
      - Whether to disable the device's built-in IPv6 NTP server.
    type: bool
    default: true

  state:
    description:
      - Whether the configuration should be present or removed (undo all).
    type: str
    choices: [present, absent]
    default: present

  save_when:
    description:
      - When to save the device configuration.
    type: str
    choices: [never, changed, always]
    default: changed

  backup:
    description:
      - Whether to create a local backup of the current configuration.
    type: bool
    default: false

  backup_path:
    description:
      - Optional path on the controller to store the backup file.
    type: str

notes:
  - Requires C(ansible_connection=ansible.netcommon.network_cli).
  - The module applies all configuration commands globally.
  - This is not a full-featured time service configuration tool. It is meant for basic NTP/DST setup.

seealso:
  - module: blumleon.vrp.vrp_config
  - module: blumleon.vrp.vrp_backup
"""

EXAMPLES = r"""
- name: Configure NTP with default timezone (no DST)
  blumleon.vrp.vrp_ntp:
    server: ntp.example.net
    save_when: changed

- name: Configure custom DST and timezone with source interface
  blumleon.vrp.vrp_ntp:
    server: 192.0.2.10
    source_interface: Vlanif10
    timezone_name: UTC
    timezone_offset: 0
    dst_name: MyDST
    dst_start: "01:00 2026-03-29"
    dst_end:   "01:00 2026-10-25"
    dst_offset: "01:00"
    save_when: changed
"""

RETURN = r"""
changed:
  description: Whether any configuration was changed or a backup was created.
  type: bool
  returned: always

commands:
  description: List of CLI commands sent to the device.
  type: list
  elements: str
  returned: when changed

responses:
  description: Output returned by the device for each command.
  type: list
  elements: str
  returned: when changed

backup_path:
  description: Path to the configuration backup file, if created.
  type: str
  returned: when backup was requested
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible_collections.blumleon.vrp.plugins.module_utils import vrp_common as vc


def _build_desired_lines(p: dict) -> list[str]:
    """Return a list of CLI lines that should be present or absent."""
    lines: list[str] = []

    # Manage timezone/DST only when explicitly requested
    if p["manage_timezone"]:
        lines.append(f"clock timezone {p['timezone_name']} add {p['timezone_offset']}")

        # Add daylight-saving configuration only if both dates are provided
        if (
            p.get("dst_start")
            and p.get("dst_end")
            and p.get("dst_name")
            and p.get("dst_offset")
        ):
            lines.append(
                f"clock daylight-saving-time {p['dst_name']} one-year "
                f"{p['dst_start']} {p['dst_end']} {p['dst_offset']}"
            )

    # NTP server is always considered
    lines.append(f"ntp unicast-server {p['server']}")

    if p["disable_ipv4_server"]:
        lines.append("ntp server disable")
    if p["disable_ipv6_server"]:
        lines.append("ntp ipv6 server disable")
    if p.get("source_interface"):
        lines.append(f"ntp server source-interface {p['source_interface']}")

    return lines


def main() -> None:
    arg_spec = dict(
        # required
        server=dict(type="str", required=True),
        # optional
        source_interface=dict(type="str"),
        timezone_name=dict(type="str", default="CET"),
        timezone_offset=dict(type="int", default=1),
        dst_name=dict(type="str"),
        dst_start=dict(type="str"),
        dst_end=dict(type="str"),
        dst_offset=dict(type="str"),
        disable_ipv4_server=dict(type="bool", default=True),
        disable_ipv6_server=dict(type="bool", default=True),
        manage_timezone=dict(type="bool"),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        save_when=dict(
            type="str", choices=["never", "changed", "always"], default="changed"
        ),
        backup=dict(type="bool", default=False),
        backup_path=dict(type="str"),
    )

    module = AnsibleModule(argument_spec=arg_spec, supports_check_mode=True)
    p = module.params

    # Default behavior: manage timezone for present, skip for absent
    if p["manage_timezone"] is None:
        p["manage_timezone"] = p["state"] == "present"

    conn = Connection(module._socket_path)

    # optional backup
    backup_changed, backup_path = vc.backup_config(
        conn, p["backup"], p.get("backup_path"), prefix="vrp_ntp_"
    )

    # desired configuration
    desired_lines = _build_desired_lines(p)
    desired_state = "absent" if p["state"] == "absent" else "present"

    # generate CLI commands
    cfg_changed, cli_cmds = vc.diff_and_wrap(
        conn,
        parents=[],
        cand_children=desired_lines,
        save_when=p["save_when"],
        state=desired_state,
        replace=False,
        keep=[],
    )

    changed = cfg_changed or backup_changed

    # check-mode handling
    if module.check_mode:
        vc.finish_module(module, changed=changed, cli_cmds=cli_cmds)
        return

    # execute commands if needed
    responses = conn.run_commands(cli_cmds) if cfg_changed else []
    module.exit_json(
        changed=changed,
        commands=cli_cmds,
        responses=responses,
        backup_path=backup_path,
    )


if __name__ == "__main__":
    main()
