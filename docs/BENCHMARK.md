# RndMRBench 2 — verified results

All figures below were produced by `aiom/bench/rndmrbench2.py` on Windows 11
with JDK 25.0.4.1, against Minecraft **26.2**.

## Loader verification

Each loader was installed from its official source and booted to full
readiness. "Readiness" means the server emitted its own
`Done (...)` marker, not merely that a process exited without error.

| Loader | Version | Readiness line |
|--------|---------|-----------------|
| Fabric | Loader 0.19.5 | `Done (0.234s)!` |
| NeoForge | 26.2.0.88 | `Done (2.073s)!` |
| Forge | 26.2-65.1.3 | reached readiness |
| Paper | 26.2 build 129 | `Done (13.223s)!` |

## Benchmark run

Smoke run used to validate the harness (3 NeoForge projects, seed 20262):

```
sampled        : 3
counted        : 3   (skipped 0)
passed         : 3
failed         : 0
isolated rate  : 100.0%  (threshold 89%)
meets threshold: YES
duration       : 7.1 min
```

This is a **harness validation**, not a headline result. A 3-project sample
says nothing about the ecosystem; the 100-project run is the one that carries
statistical weight and is executed on demand rather than per-push.

## Why the full run is not in CI

Each isolated boot costs roughly 1–2 minutes of wall clock after the loader
profile is warm, so a 100-project run is on the order of hours and depends on
Modrinth's live catalogue. CI therefore re-verifies that every loader still
boots and runs a 2-project smoke test, and the full benchmark is invoked
manually:

```bash
python -m aiom.bench.rndmrbench2 -n 100 --seed 20262
```

## Known-good environment quirks

These are handled in code and are reproducible, not intermittent:

- **NeoForge 26.2 versioning** — all 89 published builds carry a `-beta`
  suffix. A non-beta version string such as `26.2.0.0` does not exist and
  404s, so version discovery must read the maven metadata rather than
  construct a URL.
- **Installer HTTP is blocked in sandboxes** — the NeoForge/Forge installers
  use a Java HTTP client that gets `SocketException: Connection reset`.
  `launcher.py` parses the coordinates the installer prints and pre-fetches
  those jars with `curl`, then re-runs the installer so it resolves locally.
- **Maven layout must include the full group path** — `org.ow2.asm:asm`
  belongs at `org/ow2/asm/asm/...`. Truncating the prefix produces a directory
  tree the installer silently rejects.
- **`+` in version strings is legal** — e.g. `sponge-mixin-0.17.3+mixin.0.8.7`.
  Filtering it out causes a missing-dependency failure that looks unrelated.
- **Windows needs `win_args.txt`** — NeoForge/Forge ship both `win_args.txt`
  and `unix_args.txt`; using the wrong one yields
  `ClassNotFoundException: net.neoforged.fml.startup.Server`.
- **netty `epoll`/`kqueue` errors on Windows are benign** — those are
  Linux/macOS native transports and log an error even on successful runs. The
  benchmark does not treat them as failures.