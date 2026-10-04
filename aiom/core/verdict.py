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

from . import jarid

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

# Paper announces what it actually initialised, in two comma-separated lines
# that follow a "Paper plugins (N):" / "Bukkit plugins (N):" header:
#     [PluginInitializerManager] Initialized 31 plugins
#     [PluginInitializerManager] Bukkit plugins (26):
#      - AxGraves (1.32.1), BlueMap (5.28), Orebfuscator (5.6.2), ...
#
# This list, not the per-plugin "Loading server plugin X" lines, is the
# authoritative record of what is live. The latter is emitted by only some of
# the load paths, and a later `ModernPluginLoadingStrategy` retry prints
# "Could not load 'plugins\046-orebfuscator...jar'" for plugins that are in fact
# running -- reading that as a failure produced 13 false negatives.
PAPER_INITIALISED = re.compile(r"Initialized\s+(\d+)\s+plugins", re.IGNORECASE)
PAPER_LIST_HEADER = re.compile(
    r"(?:Paper|Bukkit)\s+plugins\s*\((\d+)\)\s*:", re.IGNORECASE)
PAPER_PLUGINLIST = re.compile(
    r"\[[^\]]*\]\s+Loading\s+server plugin\s+([A-Za-z0-9_]+)", re.IGNORECASE)


def paper_plugins(log_text: str) -> set[str]:
    """Plugin names Paper reports as initialised, lower-cased.

    Returns an empty set when the announcement is absent, so the caller can
    fall back to the per-plugin log lines rather than reporting a clean server
    as empty.
    """
    names: set[str] = set()
    lines = log_text.splitlines()
    for i, line in enumerate(lines):
        if not PAPER_LIST_HEADER.search(line):
            continue
        # The names sit on the following line, prefixed with " - ".
        for follow in lines[i + 1:i + 2]:
            body = follow.strip().lstrip("-").strip()
            if not body or not body.endswith(","):
                # Either the list wrapped or this is not the list line.
                if not body:
                    continue
            for entry in body.split(","):
                entry = entry.strip().lstrip("-").strip()
                m = re.match(r"([A-Za-z0-9_.\-]+)", entry)
                if m:
                    names.add(m.group(1).lower())
            break
    return names


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


def _tokens(slug: str, filename: str, jar_path: str = "") -> list[str]:
    """Searchable names for a project, most specific first.

    The authoritative mod id comes first, read out of the jar's own
    `META-INF/neoforge.mods.toml`. Deriving it from the file name instead is
    what made JEI a false negative:

        jar  028-jei-26.2-neoforge-30.39.0.232.jar
        log  Just Enough Items 30.39.0.232 (jei)

    The slug `jei` shares no substring with the display name, and it is only
    three characters, so the length filter below would drop it anyway. The jar
    itself always knows.
    """
    out: list[str] = []
    if jar_path:
        mid = jarid.mod_id(jar_path)
        if mid:
            out.append(mid)
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
    # The jar-declared id is exempt from the length filter -- it is a handle,
    # not a guessed word, so even "jei" or "mru" is safe to match exactly.
    seen: dict[str, None] = {}
    authoritative = jarid.mod_id(jar_path) if jar_path else None
    for t in sorted(out, key=len, reverse=True):
        if len(t) >= 4 or (authoritative and t == authoritative):
            seen.setdefault(t, None)
    return list(seen)


def judge(log_text: str, slug: str, filename: str,
          loader: str = "neoforge", jar_path: str = "") -> Verdict:
    """PASS requires readiness AND presence AND no refusal for this project."""
    if not log_text:
        return Verdict(False, "log missing or empty")

    ready = bool(READY.search(log_text))

    # Scope refusal detection to lines mentioning this project, so an unrelated
    # mod's failure is not misattributed.
    toks = _tokens(slug, filename, jar_path)
    refusal_hits = []
    for line in log_text.splitlines():
        if REFUSED.search(line) and any(t.lower() in line.lower() for t in toks):
            refusal_hits.append(line.strip())

    # The jar's own declared id, if we could read one. It is compared for exact
    # equality against the mod table, which no prose can fake.
    declared = jarid.mod_id(jar_path) if jar_path else None

    present = False
    evidence = ""
    if loader == "paper":
        # Prefer the initialised-plugins announcement; it is the only complete
        # record. The per-plugin lines are a fallback for older logs.
        names = paper_plugins(log_text)
        hay = names or set()
        alt = re.compile(r"Loading server plugin\s+([A-Za-z0-9_.\-]+)",
                         re.IGNORECASE)
        for m in alt.finditer(log_text):
            hay.add(m.group(1).lower())
        # A Bukkit plugin declares its own name in plugin.yml / paper-plugin.yml.
        # That name is what Paper prints, and it often differs from both the
        # project slug and the jar file name.
        pname = jarid.plugin_name(jar_path) if jar_path else None
        candidates = {t.lower() for t in toks}
        if pname:
            candidates.add(pname.lower())
        # Plugin names are CamelCase while slugs are hyphenated, so compare with
        # every separator removed: "LeashablePlayers" vs "leashable-players".
        flat = {c.replace("-", "").replace("_", "") for c in candidates}
        for cand in candidates:
            for known in hay:
                if known == cand or known.replace("_", "").lower() == \
                        cand.replace("_", "").lower():
                    present = True
                    evidence = f"plugin listed by Paper: {known}"
                    break
            if present:
                break
        if not present:
            for known in hay:
                if known.replace("-", "").replace("_", "") in flat:
                    present = True
                    evidence = f"plugin listed by Paper: {known}"
                    break
    else:
        # Match the mod table entries: "Display Name Version (mod_id)".
        # The mod id is compared with the project tokens.
        for m in NEOFORGE_MODLIST.finditer(log_text):
            mod_id = m.group(2)
            if declared and mod_id.lower() == declared.lower():
                present = True
                evidence = m.group(0).strip()
                break
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
