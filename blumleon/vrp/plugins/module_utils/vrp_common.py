# -*- coding: utf-8 -*-
"""
Zentrale Helfer für Huawei-VRP-Collection.
"""

from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import to_list
import re

# ---------------------------------------------------------------------------
#  generic helpers (config diff)                                             #
# ---------------------------------------------------------------------------

def load_running_config(conn):
    raw = conn.run_commands("display current-configuration")[0]
    return to_text(raw, errors="surrogate_or_strict").splitlines()

def to_parents(obj):
    return [obj] if isinstance(obj, str) else to_list(obj)

def build_candidate(parents, lines):
    return to_parents(parents) + to_list(lines or [])

def find_parent_block(running, parents):
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

def _undo_cmd(line):
    return f"undo {line.split()[0]}"

def diff_line_match(running, parents, cand_children, state, keep):
    cmds = []
    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1 : end] if start >= 0 else []
    stripped = {l.lstrip() for l in blk_children}

    if state == "replace":
        desired   = sorted({l.lstrip() for l in cand_children})
        removals  = stripped - set(desired) - set(keep)
        cmds += [_undo_cmd(l) for l in sorted(removals)]
        cmds += [l for l in desired if l not in stripped]
        return cmds

    for raw in cand_children:
        plain = raw.lstrip()
        if state == "present" and plain not in stripped:
            cmds.append(plain)
        elif state == "absent" and plain in stripped:
            cmds.append(_undo_cmd(plain))
    return cmds

# ---------- NEU ------------------------------------------------------------
def diff_and_wrap(conn, parents, cand_children, save_when, replace=True, keep=None):
    """
    Kombi-Helper für Module:
      • berechnet Delta über diff_line_match
      • baut system-view / return-Kaskade
      • hängt auf Wunsch eine save-Sequenz an

    Rückgabe: (changed: bool, cli_cmds: list)
    """
    keep   = keep or []
    state  = 'replace' if replace else 'present'
    running = load_running_config(conn)
    body    = diff_line_match(running, parents, cand_children, state, keep)

    if not body:
        return False, []

    cli = ['system-view'] + parents + body + ['return'] * (len(parents) + 1)
    if save_when in ('always', 'changed'):
        cli += [{'command': 'save', 'prompt': '[Y/N]', 'answer': 'Y'}]
    return True, cli
# ---------------------------------------------------------------------------

#  interface helpers                                                         #
# ---------------------------------------------------------------------------

def _l1_lines(p):
    ls = []
    if p.get("description") is not None:
        ls.append("undo description" if p["description"] == ""
                  else f"description {p['description']}")
    if p.get("admin_state") == "up":
        ls.append("undo shutdown")
    elif p.get("admin_state") == "down":
        ls.append("shutdown")
    if p.get("speed"):
        ls.append(f"speed {p['speed']}")
    if p.get("mtu"):
        ls.append(f"mtu {p['mtu']}")
    return ls

def _normalize_vlan_list(raw):
    parts = []
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
    ls   = []
    mode = p.get("port_mode")
    if mode:
        ls.append(f"port link-type {mode}")

    if mode == "access" and p.get("vlan") is not None:
        ls.append(f"port default vlan {p['vlan']}")

    raw_list = p.get("trunk_vlans")
    if mode in ("trunk", "hybrid") and raw_list:
        ls.append(f"port {mode} allow-pass vlan {_normalize_vlan_list(raw_list)}")

    if mode == "trunk" and p.get("native_vlan") is not None:
        ls.append(f"port trunk pvid vlan {p['native_vlan']}")
    return ls

def build_interface_lines(p):
    return _l1_lines(p) + _l2_lines(p)

