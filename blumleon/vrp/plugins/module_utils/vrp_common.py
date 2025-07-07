# Copyright (C) 2025 Leon Blum
# This file is part of the blumleon.vrp Ansible Collection
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Core helper module used by all vrp_* Ansible modules.
# It provides:
#   • backup helper
#   • "save" helper
#   • diff engine (string normalisation, undo helper, wrapper)
#   • interface-specific helpers (L1/L2 line builders)

import hashlib
import re
from datetime import datetime
from pathlib import Path

from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import (
    to_list,
)


# Backup helper
def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _last_backup(dir_: Path, prefix: str) -> Path | None:
    """Returns the most recent backup file with a matching prefix."""
    files = sorted(
        (f for f in dir_.iterdir() if f.is_file() and f.name.startswith(prefix)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def backup_config(
    conn,
    do_backup: bool,
    user_path: str | None = None,
    prefix: str = "vrp_",
) -> tuple[bool, str | None]:
    """
    Retrieves the running config and saves it locally.
    Returns (changed, path).
    """
    if not do_backup:
        return False, None

    cfg_text = "\n".join(load_running_config(conn))

    # A) User-defined path
    if user_path:
        dst = Path(user_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        identical = dst.is_file() and dst.read_text() == cfg_text
        if not identical:
            dst.write_text(cfg_text)
        return (not identical), str(dst)

    # B) Automatic path in the ./backups directory
    bdir = Path("backups")
    bdir.mkdir(exist_ok=True)

    last = _last_backup(bdir, prefix)
    if last and _sha1(last.read_text()) == _sha1(cfg_text):
        return False, str(last)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    new_path = bdir / f"{prefix}{ts}.cfg"
    new_path.write_text(cfg_text)
    return True, str(new_path)


# helper (save)
def append_save(cli_cmds: list, save_when: str, changed: bool) -> list:
    """Append a 'save' command depending on *save_when*."""
    if save_when == "always" or (save_when == "changed" and changed):
        cli_cmds += [{"command": "save", "prompt": "[Y/N]", "answer": "Y"}]
    return cli_cmds


# Generic helpers (running‑config access, parent utils)
def load_running_config(conn):
    raw = conn.run_commands("display current-configuration")[0]
    return to_text(raw, errors="surrogate_or_strict").splitlines()


def to_parents(obj):
    return [obj] if isinstance(obj, str) else to_list(obj)


def build_candidate(parents, lines):
    """Concatenate parents + child body."""
    return to_parents(parents) + to_list(lines or [])


def find_parent_block(running: list[str], parents: list[str]):
    """Return *(start, end)* indices of the given parent block inside *running*."""
    if not parents:
        return 0, len(running)
    try:
        start = running.index(parents[0])
    except ValueError:
        return -1, -1
    end = start + 1
    while end < len(running) and running[end].startswith(" "):
        end += 1
    return start, end


# Helper to create appropriate "undo …" command  (extended)
def _undo_cmd(line: str) -> str:
    """Translate an *existing* config line into the matching VRP `undo...`"""
    tokens = line.split()
    if not tokens:
        return ""

    # Interface specific lines
    if tokens[0] == "port":
        if tokens[1:3] == ["link-type", tokens[-1]]:
            return "undo port link-type"
        if tokens[1:3] == ["default", "vlan"]:
            return "undo port default vlan"
        if tokens[1:3] == ["trunk", "allow-pass"]:
            return ""  # auto removed by VRP
        if tokens[1:4] == ["trunk", "pvid", "vlan"]:
            return ""  # auto removed by VRP
        return f"undo {' '.join(tokens[:-1])}"

    # Global config lines
    if tokens[:2] == ["ip", "domain-name"]:
        return "undo ip domain-name"

    if tokens[:2] == ["dns", "server"] and len(tokens) >= 3:
        if tokens[2] == "ipv6" and len(tokens) >= 4:
            return f"undo dns server ipv6 {tokens[3]}"
        return f"undo dns server {tokens[2]}"

    if tokens[:2] == ["clock", "timezone"]:
        return f"undo clock timezone {tokens[2]}"
    if tokens[:2] == ["clock", "daylight-saving-time"]:
        return "undo clock daylight-saving-time"

    if tokens[:2] == ["ntp", "unicast-server"]:
        return f"undo ntp unicast-server {tokens[2]}"
    if tokens[:3] == ["ntp", "server", "disable"]:
        return "undo ntp server disable"
    if tokens[:4] == ["ntp", "ipv6", "server", "disable"]:
        return "undo ntp ipv6 server disable"
    if tokens[:3] == ["ntp", "server", "source-interface"]:
        return f"undo ntp server source-interface {tokens[3]}"

    # ssh / rsa user management
    if tokens[:2] == ["ssh", "user"] and len(tokens) >= 3:
        # Remove the complete ssh-user entry in one shot
        return f"undo ssh user {tokens[2]}"
    if tokens[:2] == ["rsa", "peer-public-key"]:
        return f"undo rsa peer-public-key {tokens[2]}"

    # local-user root line (AAA)
    if tokens[0] == "local-user" and len(tokens) >= 2:
        return f"undo local-user {tokens[1]}"

    # STP interface features
    if tokens[:3] == ["stp", "edged-port", "enable"]:
        return "undo stp edged-port"

    # **NEU: STP BPDU-Protection (global)**
    if tokens[:2] == ["stp", "bpdu-protection"]:
        return "undo stp bpdu-protection"

    # Fallback
    return f"undo {tokens[0]}"


# Diff engine  ──  string normalisation & compare
_dash_map = {ord("–"): " ", ord("—"): " "}
_defrag = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = s.strip().translate(_dash_map)
    s = s.replace(" to ", "-")
    s = re.sub(r"\s*-\s*", "-", s)
    s = _defrag.sub(" ", s)
    low = s.lower()

    low = re.sub(r"add 0*([0-9]+):00:00", r"add \1", low)

    if low.startswith("port trunk allow-pass vlan "):
        prefix, vlans = low.split("vlan ", 1)
        ordered = " ".join(sorted(vlans.split(), key=lambda x: int(x.split("-")[0])))
        return f"{prefix}vlan {ordered}"

    if low.startswith("port hybrid tagged vlan "):
        prefix, vlans = low.split("vlan ", 1)
        ordered = " ".join(sorted(vlans.split(), key=lambda x: int(x.split("-")[0])))
        return f"{prefix}vlan {ordered}"

    return low


def diff_line_match(running, parents, cand_children, state, keep):
    cmds: list[str] = []

    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1 : end] if start >= 0 else []

    raw_by_norm = {_norm(c): c.lstrip() for c in blk_children}
    stripped = set(raw_by_norm)

    # state == replace
    if state == "replace":
        desired = {_norm(c) for c in cand_children}
        removals = stripped - desired - {_norm(k) for k in keep}
        for n in sorted(removals):
            if undo := _undo_cmd(raw_by_norm[n]):
                cmds.append(undo)

        for raw in cand_children:
            plain = _norm(raw)
            if plain == "port link-type access":
                if any(
                    line.startswith("port link-type ") and _norm(line) != plain
                    for line in raw_by_norm.values()
                ):
                    cmds.append(raw)
                continue
            if plain == "undo shutdown":
                if "shutdown" in stripped:
                    cmds.append(raw)
                continue
            if plain not in stripped:
                cmds.append(raw)

        if "undo port link-type" in cmds:
            idx = cmds.index("undo port link-type")
            last_undo = max(i for i, c in enumerate(cmds) if c.startswith("undo"))
            if last_undo < idx:
                cmds.insert(last_undo + 1, cmds.pop(idx))
        return cmds

    # state == present / absent
    for raw in cand_children:
        plain = _norm(raw)

        if state == "present":
            if plain == "undo shutdown":
                if "shutdown" in stripped:
                    cmds.append(raw)
                continue
            if plain == "port link-type access":
                if any(
                    line.startswith("port link-type ") and _norm(line) != plain
                    for line in raw_by_norm.values()
                ):
                    cmds.append(raw)
                continue
            if plain not in stripped:
                cmds.append(raw)

        elif state == "absent" and plain in stripped:
            if undo := _undo_cmd(raw_by_norm[plain]):
                cmds.append(undo)

    return cmds


def diff_and_wrap(
    conn,
    parents,
    cand_children,
    save_when,
    *,
    replace=True,
    keep=None,
    state: str | None = None,
):
    """Diff -> wrap with *system-view/return/save* boilerplate."""
    keep = keep or []
    desired_state = state or ("replace" if replace else "present")

    body_changed = diff_line_match(
        load_running_config(conn), parents, cand_children, desired_state, keep
    )
    if not body_changed:
        return False, []

    cli = ["system-view", *parents, *body_changed, *["return"] * (len(parents) + 1)]
    append_save(cli, save_when, changed=True)
    return True, cli


# Interface helpers (lines builder)
def _l1_lines(p):
    """Build Layer1 related lines (description / shutdown / speed / mtu)."""
    ls: list[str] = []
    if p.get("description") is not None:
        ls.append(
            "undo description"
            if p["description"] == ""
            else f"description {p['description']}"
        )
    if p.get("admin_state") == "up":
        ls.append("undo shutdown")
    elif p.get("admin_state") == "down":
        ls.append("shutdown")
    if p.get("speed"):
        ls.append(f"speed {p['speed']}")
    if p.get("mtu"):
        ls.append(f"mtu {p['mtu']}")
    return ls


def _normalize_vlan_list(raw: str) -> str:
    parts: list[str] = []
    for tok in re.split(r"[,\s]+", raw.strip()):
        if not tok:
            continue
        if "-" in tok:
            a, b = tok.split("-", 1)
            parts.append(f"{a.strip()} to {b.strip()}")
        else:
            parts.append(tok)
    return " ".join(parts)


def _l2_lines(p):
    ls: list[str] = []
    mode = p.get("port_mode")

    if mode:
        ls.append(f"port link-type {mode}")

    if mode == "access" and p.get("vlan") is not None:
        ls.append(f"port default vlan {p['vlan']}")

    raw_list = p.get("trunk_vlans")
    if mode == "trunk" and raw_list:
        ls.append(f"port trunk allow-pass vlan {_normalize_vlan_list(raw_list)}")
        if p.get("native_vlan") is not None:
            ls.append(f"port trunk pvid vlan {p['native_vlan']}")

    if mode == "hybrid" and raw_list:
        ls.append(f"port hybrid tagged vlan {_normalize_vlan_list(raw_list)}")
        if p.get("native_vlan") is not None:
            ls.append(f"port hybrid pvid vlan {p['native_vlan']}")

    if p.get("stp_edged"):
        ls.append("stp edged-port enable")

    return ls


def build_interface_lines(p):
    return _l1_lines(p) + _l2_lines(p)


#  Convenience helper
def lines_present(running: list[str], desired: list[str]) -> bool:
    flat = {line.strip() for line in running}
    return all(line.strip() in flat for line in desired)


def wrap_cmd(cmd, user=None, priv_cmd=None):
    """Return either plain string or dict with prompt/answer if confirmation needed."""
    if isinstance(cmd, dict):
        return cmd

    yn = r"[Yy][/ ]?[Nn]"
    confirm = {
        "save": yn,
        "continue": yn,
        "overwrite": yn,
    }

    if user:
        confirm.update(
            {
                f"rsa peer-public-key {user}": yn,
                f"ssh user {user} authentication-type rsa": yn,
                f"ssh user {user} assign rsa-key {user}": yn,
                f"local-user {user} password irreversible-cipher": yn,
                f"local-user {user}": yn,
                "assign rsa-key": yn,
            }
        )

    if priv_cmd:
        confirm[priv_cmd] = yn

    for key, regex in confirm.items():
        if key in cmd:
            return {"command": cmd, "prompt": regex, "answer": "Y"}
    return cmd
