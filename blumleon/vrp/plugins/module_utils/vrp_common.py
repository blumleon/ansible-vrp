# -*- coding: utf-8 -*-
"""
Zentrale Helfer für Huawei‑VRP‑Collection.

Changelog (2025‑06‑11)
----------------------
* _undo_cmd:
    • "port trunk pvid vlan …" erzeugt **kein** Undo mehr, weil VRP das Attribut
      beim Mode‑Wechsel automatisch entfernt.
* diff_line_match:
    • Unreachable Doppel‑Loop entfernt.
    • Stellt sicher, dass "undo port link-type" **immer zuletzt** gesendet wird,
      damit Trunk‑Attribute vorher sauber entfernt werden.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Tuple

from ansible.module_utils._text import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import (
    to_list,
)

# ---------------------------------------------------------------------------
#  backup helper                                                             #
# ---------------------------------------------------------------------------


def backup_config(
    conn,
    do_backup: bool,
    user_path: str | None = None,
    prefix: str = "vrp_",
) -> Tuple[bool, str | None]:
    """Sichert die Running‑Config lokal ab."""
    if not do_backup:
        return False, None

    cfg_text = "\n".join(load_running_config(conn))

    # Benutzerpfad
    if user_path:
        os.makedirs(os.path.dirname(user_path), exist_ok=True)
        identical = os.path.isfile(user_path) and open(user_path).read() == cfg_text
        if not identical:
            with open(user_path, "w", encoding="utf-8") as fh:
                fh.write(cfg_text)
        return (not identical), user_path

    # Auto‑Pfad
    os.makedirs("backups", exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".cfg", dir="backups")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(cfg_text)
    return True, path


# ---------------------------------------------------------------------------
#  save helper                                                               #
# ---------------------------------------------------------------------------


def append_save(cli_cmds: list, save_when: str) -> list:
    """Hängt bei Bedarf einen 'save'‑Befehl an."""
    if save_when in ("always", "changed"):
        cli_cmds += [{"command": "save", "prompt": "[Y/N]", "answer": "Y"}]
    return cli_cmds


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


# ---------------------------------------------------------------------------
#  Undo‑Generator                                                            #
# ---------------------------------------------------------------------------

def _undo_cmd(line: str) -> str:
    """Generiert Undo‑Befehle für VRP‑CLI.

    • port link-type <mode>   -> undo port link-type
    • port default vlan <id>  -> undo port default vlan
    • trunk‑Attribute, die beim Mode‑Wechsel von selbst verschwinden
      (allow-pass, pvid)      -> ''  (kein Undo)
    • sonst                   -> undo <erstes Keyword>
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

    # —— nichts zurückgeben: VRP räumt das automatisch weg ——
    if tokens[1:3] == ["trunk", "allow-pass"]:
        return ""
    if tokens[1:4] == ["trunk", "pvid", "vlan"]:
        return ""  # pvid wird beim Mode‑Wechsel implizit entfernt

    # Fallback (letztes Token kappen)
    return f"undo {' '.join(tokens[:-1])}"


# ---------------------------------------------------------------------------
#  Diff‑Logik                                                                #
# ---------------------------------------------------------------------------

def diff_line_match(running, parents, cand_children, state, keep):
    """Vergleicht laufende Konfiguration mit Wunsch-Config und erzeugt CLI."""

    cmds = []
    start, end = find_parent_block(running, parents)
    blk_children = running[start + 1 : end] if start >= 0 else []
    stripped = {child.lstrip() for child in blk_children}

    if state == "replace":
        # ---------- Removals -------------------------------------------------
        desired_set = {child.lstrip() for child in cand_children}
        removals = stripped - desired_set - set(keep)
        for line in sorted(removals):
            undo = _undo_cmd(line)
            if undo:
                cmds.append(undo)

        # ---------- Additions ------------------------------------------------
        #   Wichtig: NICHT sortieren – Originalreihenfolge beibehalten,
        #   damit semantische Abhängigkeiten (link‑type → default‑vlan …)
        #   gewahrt bleiben.
        for raw in cand_children:
            plain = raw.lstrip()
            if plain not in stripped:
                cmds.append(plain)

        # ---------- Reihenfolge fixen ---------------------------------------
        #   • "undo port link-type" muss VOR "port link-type …" stehen
        #   • Gleichzeitig soll der Undo aber NACH allen anderen Undos kommen,
        #     damit spezielle Trunk-Attribute vorher weg sind.
        if "undo port link-type" in cmds:
            idx = cmds.index("undo port link-type")
            # nach vorne ziehen, aber hinter mögliche andere Undos
            # (die alle mit "undo" anfangen):
            last_undo = max(i for i, c in enumerate(cmds) if c.startswith("undo"))
            if last_undo < idx:
                cmds.insert(last_undo + 1, cmds.pop(idx))
        return cmds

    # ---------- state == present / absent ----------------------------------
    for raw in cand_children:
        plain = raw.lstrip()
        if state == "present" and plain not in stripped:
            cmds.append(plain)
        elif state == "absent" and plain in stripped:
            undo = _undo_cmd(plain)
            if undo:
                cmds.append(undo)
    return cmds

    # state == present / absent
    for raw in cand_children:
        plain = raw.lstrip()
        if state == "present" and plain not in stripped:
            cmds.append(plain)
        elif state == "absent" and plain in stripped:
            undo = _undo_cmd(plain)
            if undo:
                cmds.append(undo)
    return cmds


# ---------- NEU ------------------------------------------------------------

def diff_and_wrap(conn, parents, cand_children, save_when, replace=True, keep=None):
    """Wrapper um diff_line_match + system-view‑Kaskade + optional save."""
    keep = keep or []
    state = "replace" if replace else "present"
    body_changed = diff_line_match(
        load_running_config(conn), parents, cand_children, state, keep
    )
    if not body_changed:
        return False, []

    cli = ["system-view"] + parents + body_changed + ["return"] * (len(parents) + 1)
    append_save(cli, save_when)
    return True, cli


# ---------------------------------------------------------------------------
#  interface helpers                                                         #
# ---------------------------------------------------------------------------

def _l1_lines(p):
    ls = []
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


def _normalize_vlan_list(raw):
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
    ls = []
    mode = p.get("port_mode")
    if mode:
        ls.append(f"port link-type {mode}")

    if mode == "access" and p.get("vlan") is not None:
        ls.append(f"port default vlan {p['vlan']}")

    raw_list = p.get("trunk_vlans")
    if mode in ("trunk", "hybrid") and raw_list:
        ls.append("port trunk allow-pass vlan all")
        ls.append(f"port {mode} allow-pass vlan {_normalize_vlan_list(raw_list)}")

    if mode == "trunk" and p.get("native_vlan") is not None:
        ls.append(f"port trunk pvid vlan {p['native_vlan']}")
    return ls


def build_interface_lines(p):
    return _l1_lines(p) + _l2_lines(p)

