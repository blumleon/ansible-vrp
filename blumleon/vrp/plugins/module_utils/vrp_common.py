# Copyright (C) 2025 Leon Blum
# This file is part of the blumleon.vrp Ansible Collection
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Core helper module used by all vrp_* Ansible modules.
# It provides:
#   • backup helper
#   • “save” helper
#   • diff engine (string normalisation, undo helper, wrapper)
#   • interface-specific helpers (L1/L2 line builders)

import os
import re
import tempfile
from typing import Tuple

from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import (
    to_list,
)

# ──────────────────────────────────────────────────────────────────────────────
#  Backup helper
# ──────────────────────────────────────────────────────────────────────────────


def backup_config(
    conn,
    do_backup: bool,
    user_path: str | None = None,
    prefix: str = "vrp_",
) -> Tuple[bool, str | None]:
    """
    Retrieve the running configuration and write it to disk.

    Returns (changed, path)
    """
    if not do_backup:
        return False, None

    cfg_text = "\n".join(load_running_config(conn))

    # User-supplied path: write only when content really changed
    if user_path:
        os.makedirs(os.path.dirname(user_path), exist_ok=True)
        identical = os.path.isfile(user_path) and open(user_path).read() == cfg_text
        if not identical:
            with open(user_path, "w", encoding="utf-8") as fh:
                fh.write(cfg_text)
        return not identical, user_path

    # Automatic path inside ./backups
    os.makedirs("backups", exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".cfg", dir="backups")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(cfg_text)
    return True, path


# ──────────────────────────────────────────────────────────────────────────────
#  “save” helper
# ──────────────────────────────────────────────────────────────────────────────


def append_save(cli_cmds: list, save_when: str, changed: bool) -> list:
    """
    Append a 'save' command depending on *save_when*.

      • "always"  – always send 'save'
      • "changed" – only when we already generated CLI commands
      • "never"   – never
    """
    if save_when == "always" or (save_when == "changed" and changed):
        cli_cmds += [{"command": "save", "prompt": "[Y/N]", "answer": "Y"}]
    return cli_cmds


# ──────────────────────────────────────────────────────────────────────────────
#  Generic helpers (running-config access, parent utils)
# ──────────────────────────────────────────────────────────────────────────────


def load_running_config(conn):
    raw = conn.run_commands("display current-configuration")[0]
    return to_text(raw, errors="surrogate_or_strict").splitlines()


def to_parents(obj):
    return [obj] if isinstance(obj, str) else to_list(obj)


def build_candidate(parents, lines):
    """Concatenate parents + child body."""
    return to_parents(parents) + to_list(lines or [])


def find_parent_block(running, parents):
    """
    Return (start, end) indices of the given parent block inside *running*.
    If parent not present -> (-1, -1).
    """
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


# ──────────────────────────────────────────────────────────────────────────────
#  Helper to create appropriate “undo …” command
# ──────────────────────────────────────────────────────────────────────────────


def _undo_cmd(line: str) -> str:
    """
    Translate an *existing* config line into the matching “undo …” command
    understood by VRP, handling Huawei's special cases.
    """
    tokens = line.split()
    if not tokens:
        return ""

    if tokens[0] != "port":
        return f"undo {tokens[0]}"

    if tokens[1:3] == ["link-type", tokens[-1]]:
        return "undo port link-type"
    if tokens[1:3] == ["default", "vlan"]:
        return "undo port default vlan"

    # These two are auto-removed by VRP – no CLI necessary
    if tokens[1:3] == ["trunk", "allow-pass"]:
        return ""
    if tokens[1:4] == ["trunk", "pvid", "vlan"]:
        return ""

    return f"undo {' '.join(tokens[:-1])}"


# ──────────────────────────────────────────────────────────────────────────────
#  Diff engine  ──  string normalisation & compare
# ──────────────────────────────────────────────────────────────────────────────

# Convert exotic dash characters → SPACE
# Keep the plain "-" intact so VLAN ranges stay connected
_dash_map = {
    ord("–"): " ",  # en-dash
    ord("—"): " ",  # em-dash
}

_defrag = re.compile(r"\s+")


def _norm(s: str) -> str:
    """
    Normalise a single config line for *string* comparison.

      * strip
      * exotic dashes → " "
      * " to " → "-"
      * remove spaces around "-"
      * collapse multiple spaces
      * lower-case
      * VLAN-lists are additionally sorted so order does not matter
    """
    s = s.strip().translate(_dash_map)
    s = s.replace(" to ", "-")
    s = re.sub(r"\s*-\s*", "-", s)
    s = _defrag.sub(" ", s)
    low = s.lower()

    # Sort VLAN fragments so "100-102 200" == "200 100-102"
    if low.startswith("port trunk allow-pass vlan "):
        prefix, vlans = low.split("vlan ", 1)
        parts = vlans.split()
        parts_sorted = " ".join(
            sorted(parts, key=lambda x: int(x.split("-")[0]) if "-" in x else int(x))
        )
        return f"{prefix}vlan {parts_sorted}"

    if low.startswith("port hybrid tagged vlan "):
        prefix, vlans = low.split("vlan ", 1)
        parts = vlans.split()
        parts_sorted = " ".join(
            sorted(parts, key=lambda x: int(x.split("-")[0]) if "-" in x else int(x))
        )
        return f"{prefix}vlan {parts_sorted}"

    return low


def diff_line_match(running, parents, cand_children, state, keep):
    """
    Compare running config with desired config and return **CLI commands only
    for real differences**.
    """
    cmds: list[str] = []

    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1 : end] if start >= 0 else []

    raw_by_norm = {_norm(c): c.lstrip() for c in blk_children}
    stripped = set(raw_by_norm)

    # ────────────── state == replace ──────────────
    if state == "replace":
        desired_set = {_norm(c) for c in cand_children}
        removals = stripped - desired_set - {_norm(k) for k in keep}
        for n in sorted(removals):
            undo = _undo_cmd(raw_by_norm[n])
            if undo:
                cmds.append(undo)

        for raw in cand_children:  # keep author order
            plain = _norm(raw)

            # special-case 1: link-type access
            if plain == "port link-type access":
                if any(
                    l.startswith("port link-type ") and _norm(l) != plain
                    for l in raw_by_norm.values()
                ):
                    cmds.append(raw)
                continue

            # special-case 2: undo shutdown
            if plain == "undo shutdown":
                if "shutdown" in stripped:
                    cmds.append(raw)
                continue

            if plain not in stripped:
                cmds.append(raw)

        # keep VRP syntax ordering
        if "undo port link-type" in cmds:
            idx = cmds.index("undo port link-type")
            last_undo = max(i for i, c in enumerate(cmds) if c.startswith("undo"))
            if last_undo < idx:
                cmds.insert(last_undo + 1, cmds.pop(idx))
        return cmds

    # ────────────── state == present / absent ──────────────
    for raw in cand_children:
        plain = _norm(raw)

        if state == "present":
            # special-case 1: undo shutdown
            if plain == "undo shutdown":
                if "shutdown" in stripped:
                    cmds.append(raw)
                continue

            # special-case 2: link-type access
            if plain == "port link-type access":
                if any(
                    l.startswith("port link-type ") and _norm(l) != plain
                    for l in raw_by_norm.values()
                ):
                    cmds.append(raw)
                continue

            if plain not in stripped:
                cmds.append(raw)

        elif state == "absent" and plain in stripped:
            undo = _undo_cmd(raw_by_norm[plain])
            if undo:
                cmds.append(undo)

    return cmds


def diff_and_wrap(conn, parents, cand_children, save_when, replace=True, keep=None):
    """
    Convenience wrapper:

      diff → enter system-view → apply parents/body → exit → optional save
    """
    keep = keep or []
    desired_state = "replace" if replace else "present"

    body_changed = diff_line_match(
        load_running_config(conn), parents, cand_children, desired_state, keep
    )
    if not body_changed:
        return False, []

    cli = ["system-view"] + parents + body_changed + ["return"] * (len(parents) + 1)
    append_save(cli, save_when, changed=True)
    return True, cli


# ──────────────────────────────────────────────────────────────────────────────
#  Interface helpers (lines builder)
# ──────────────────────────────────────────────────────────────────────────────


def _l1_lines(p):
    """Build Layer-1 related lines (description / shutdown / speed / mtu)."""
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
    """Convert '10-12,20  30' → '10 to 12 20 30' (VRP syntax)."""
    parts = []
    for tok in re.split(r"[,\\s]+", raw.strip()):
        if not tok:
            continue
        if "-" in tok:
            a, b = tok.split("-", 1)
            parts.append(f"{a.strip()} to {b.strip()}")
        else:
            parts.append(tok)
    return " ".join(parts)


def _l2_lines(p):
    """Build Layer-2 related lines (link-type, vlan lists, PVID …)."""
    ls: list[str] = []
    mode = p.get("port_mode")

    if mode:
        ls.append(f"port link-type {mode}")

    # access
    if mode == "access" and p.get("vlan") is not None:
        ls.append(f"port default vlan {p['vlan']}")

    # trunk
    raw_list = p.get("trunk_vlans")
    if mode == "trunk" and raw_list:
        ls.append(f"port trunk allow-pass vlan {_normalize_vlan_list(raw_list)}")
        if p.get("native_vlan") is not None:
            ls.append(f"port trunk pvid vlan {p['native_vlan']}")

    # hybrid
    if mode == "hybrid" and raw_list:
        ls.append(f"port hybrid tagged vlan {_normalize_vlan_list(raw_list)}")

    return ls


def build_interface_lines(p):
    """Return L1 + L2 lines ready for diffing."""
    return _l1_lines(p) + _l2_lines(p)


# ──────────────────────────────────────────────────────────────────────────────
#  Simple helper: are *all* desired lines present?
# ──────────────────────────────────────────────────────────────────────────────


def lines_present(running: list[str], desired: list[str]) -> bool:
    flat = {line.strip() for line in running}
    return all(line.strip() in flat for line in desired)
