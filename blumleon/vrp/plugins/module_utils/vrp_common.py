# -*- coding: utf-8 -*-
"""
Gemeinsame Helper für alle Huawei-VRP-Module der Collection.
Wird von Ansible automatisch in jedes AnsiballZ-Zip gepackt.
"""

from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import to_list

# ---------------------------------------------------------------------------
# Helfer für vrp_config ------------------------------------------------------
# ---------------------------------------------------------------------------

def load_running_config(conn):
    raw = conn.run_commands("display current-configuration")[0]
    return to_text(raw, errors="surrogate_or_strict").splitlines()


def to_parents(obj):
    """str → [str]  |  list → list (flach)"""
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
    """
    Vergleicht Running-Config & Wunschzustand und liefert CLI-Befehle,
    um die Differenz auszugleichen.
    """
    cmds = []
    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1 : end] if start >= 0 else []
    stripped = {l.lstrip() for l in blk_children}

    if state == "replace":
        desired = sorted({l.lstrip() for l in cand_children})
        removals = stripped - set(desired) - set(keep)
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


# ---------------------------------------------------------------------------
# Helfer für vrp_interface ---------------------------------------------------
# ---------------------------------------------------------------------------

def build_interface_lines(p):
    """
    Übersetzt die vrp_interface-Parameter → idempotente CLI-Zeilen.
    """
    ls = []
    if p.get("description") is not None:
        ls.append("undo description" if p["description"] == ""
                  else f"description {p['description']}")
    state = p.get("admin_state")
    if state == "up":
        ls.append("undo shutdown")
    elif state == "down":
        ls.append("shutdown")
    if p.get("speed"):
        ls.append(f"speed {p['speed']}")
    if p.get("vlan") is not None:
        ls.append(f"port default vlan {p['vlan']}")
    return ls
