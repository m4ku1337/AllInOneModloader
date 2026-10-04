"""Decide whether a project truly loaded, not merely whether the server did.

This module exists because of a measured failure mode. Dropping a Fabric jar
into a NeoForge instance leaves the server reaching readiness while the loader
prints:

    Skipping jar. File mods/ferritecore-9.0.0-fabric.jar is a Fabric mod
    and cannot be loaded

A naive readiness check scores that as a pass. It is a false positive: nothing
loaded. Every predicate here is written to refuse that outcome.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The server reached a usable state.
READY = re.compile(r"Done \([\d.,]+s\)!|Server ready|Started @\s*"
                   r"|For help, type \"help\"", re.IGNORECASE)

# Signs the loader actively refused a jar. Any of these in the log for the
# project under test means it did not load.
REFUSED = re.compile(
    r"is a Fabric mod and cannot be loaded"
    r"|cannot be loaded"
    r"|Failed to load (?:mod|plugin)"
    r"|Failed to create mod instance"
    r"|ModLoadingException"
    r"|InvalidMixinException"
    r"|Mixin apply failed"
    r"|Failed to start the minecraft server"
    r"|Could not load plugin",
    re.IGNORECASE)

# NeoForge prints a mod table as "Display Name Version (mod_id)", one per line:
#     Ferrite Core 9.0.0 (ferritecore)
# The mod id in parentheses is the authoritative handle.
NEOFORGE_MODLIST = re.compile(r"^\s*(.+?)\s+\(([A-Za-z0-9_.\-]+)\)\s*$",
                              re.MULTILINE)
PAPER_PLUGINLIST = re.compile(
    r"\[[^\]]*\]\s+Loading\s+server plugin\s+([A-Za-z0-9_]+)", re.IGNORECASE)


@dataclass
class Verdict:
    passed: bool
    reason: str
    evidence: str = ""
    ready: bool = False
    saw_refusal: bool = False


def read_log(path: Path) -> str:
    if not path or not Path(path).exists():
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _tokens(slug: str, filename: str) -> list[str]:
    """Searchable names for a project, most specific first.

    The mod id is the loader's own handle and is the only token guaranteed to
    appear in a mod table, so it is derived first from the jar stem.
    """
    out: list[str] = []
    stem = re.sub(r"\.jar$", "", filename or "", flags=re.IGNORECASE)
    if stem:
        # Strip our own ordering prefix ("003-name.jar").
        stem = re.sub(r"^\d{3}-", "", stem)
    if stem:
        out.append(stem)
    if slug:
        out.append(slug)
    if stem:
        # "ferritecore-9.0.0-neoforge" -> "ferritecore"
        m = re.match(r"([A-Za-z0-9_]+)", stem)
        if m:
            out.append(m.group(1))
        # Some jars are named "<slug>-<loader>-<ver>" where the slug itself is
        # the second token; keep the two-token form as a fallback.
        m2 = re.match(r"[A-Za-z0-9_]+-([A-Za-z0-9_]+)", stem)
        if m2:
            out.append(m2.group(1))
    # Longest first: a bare short token like "core" would match far too much.
    seen: dict[str, None] = {}
    for t in sorted(out, key=len, reverse=True):
        if len(t) >= 4:
            seen.setdefault(t, None)
    return list(seen)


def judge(log_text: str, slug: str, filename: str,
          loader: str = "neoforge") -> Verdict:
    """PASS requires readiness AND presence AND no refusal for this project."""
    if not log_text:
        return Verdict(False, "log missing or empty")

    ready = bool(READY.search(log_text))

    # Scope refusal detection to lines mentioning this project, so an unrelated
    # mod's failure is not misattributed.
    toks = _tokens(slug, filename)
    refusal_hits = []
    for line in log_text.splitlines():
        if REFUSED.search(line) and any(t.lower() in line.lower() for t in toks):
            refusal_hits.append(line.strip())

    present = False
    evidence = ""
    if loader == "paper":
        for t in toks:
            m = re.search(rf"Loading server plugin\s+{re.escape(t)}",
                          log_text, re.IGNORECASE)
            if m:
                present = True
                evidence = m.group(0)
                break
    else:
        # Match the mod table entries: "Display Name Version (mod_id)".
        # The mod id is compared with the project tokens.
        for m in NEOFORGE_MODLIST.finditer(log_text):
            mod_id = m.group(2)
            if any(t.lower() == mod_id.lower() for t in toks):
                present = True
                evidence = m.group(0).strip()
                break
            # Fall back to a display-name containment check.
            if any(t.lower() in m.group(1).lower() for t in toks):
                present = True
                evidence = m.group(0).strip()
                break

    if refusal_hits:
        return Verdict(False, "loader refused the jar", refusal_hits[0][:300],
                       ready, True)
    if not ready:
        return Verdict(False, "server never reached readiness",
                       ready=ready)
    if not present:
        return Verdict(False, "server ready but project absent from mod list",
                       ready=ready)
    return Verdict(True, "loaded and announced", evidence, ready, False)
