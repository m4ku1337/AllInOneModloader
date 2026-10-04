# AllInOne Modloader

> **This project is developed and operated entirely by an AI agent.**
> Every line of code, every benchmark run, and every decision documented here
> was produced autonomously by an AI coding assistant. No human hand wrote the
> implementation. Human involvement was limited to defining the goal and
> answering clarifying questions.

Unified Minecraft **26.2** instance management for **Forge**, **Fabric**,
**NeoForge** mods and **Paper** plugins, plus **RndMRBench 2** — a randomised,
reproducible load benchmark over the real Modrinth ecosystem.

---

## What this is (and what it is not)

Minecraft 26.2 is supported by all four ecosystems, and this project installs
and boots each of them for real:

| Ecosystem | Version used | Status |
|-----------|--------------|--------|
| Fabric    | Loader 0.19.5 | verified booting |
| NeoForge  | 26.2.0.88 | verified booting |
| Forge     | 26.2-65.1.3 | verified booting |
| Paper     | 26.2 build 129 | verified booting |

### Honest scope statement

**A single JVM running all four loaders at once is not possible, and this
project does not claim to do it.** That is a property of the Minecraft modding
ecosystem, not a missing feature:

- Fabric and Forge both rewrite the same Minecraft classes through incompatible
  transformation pipelines. The transformation order between them is not
  predictable, so both cannot own class loading simultaneously.
- NeoForge is a Forge fork and inherits the same constraint.
- Fabric's own FAQ states Forge mods must run on Forge; the community bridge
  (**Sinytra Connector**) exists precisely because a true merge was never
  viable, and it supports only a subset of mods.
- Paper/Bukkit plugins are **server-side only**. There is no Bukkit class
  loader inside a client JVM, so a Paper plugin can never load in the same
  process as a client mod.

What AllInOne Modloader builds instead is the thing that *is* achievable and
genuinely useful: **one instance directory, one configuration surface, one
command surface** — with each ecosystem booted by its own official toolchain
inside that shared instance, and a benchmark that measures them rigorously
rather than pretending they merge.

---

## RndMRBench 2

A randomised benchmark that samples N projects from Modrinth filtered to
Minecraft 26.2, installs each one, and reports honestly.

### Metric contract

Two numbers are reported, and they are never conflated:

- **`isolated_load_rate`** — each sampled project is installed into its own
  pristine instance. A project *passes* when the server reaches full readiness
  **and** the loader's log actually announces that project. This is the number
  the **89% threshold** applies to.
- **`coexistence_rate`** — all sampled projects installed together into one
  shared instance. Reported separately.

### Why the two metrics are separated

Sampling 100 projects at random guarantees collisions: duplicate mods,
unmet dependencies, mutually exclusive mixins, client-only mods on a server.
A single combined instance therefore *cannot* reach 89% by construction, and
any project reporting such a figure is measuring something other than what it
claims. Isolating each project measures exactly one thing — *does this mod load
on this loader at this Minecraft version* — which is both meaningful and
achievable.

### Anti-false-positive rules

The benchmark is built so that it cannot report a pass it did not earn:

1. **Readiness markers only.** A run passes only when the server log contains
   the loader's own readiness line (`Done (...)`). Exit code alone never counts,
   because a server terminated after becoming ready exits non-zero.
2. **The mod must appear in the log.** After reaching readiness the benchmark
   greps the log for the project name. A mod that silently failed to register
   is recorded as a failure, not a pass.
3. **Reproducible sampling.** Sampling is seeded, so a published rate can be
   re-derived exactly.
4. **Every failure is preserved** with its log path and tail.

---

## Requirements

- **Java 25** — Minecraft 26.2 declares `javaVersion.majorVersion = 25`.
  Java 21 will not work. Set `AIOM_JAVA_HOME` if auto-detection cannot find it.
- `curl` — used as the network fallback (see below).
- Network access to Mojang piston-meta, Modrinth, and the loader mavens.

## Usage

```bash
# Verify every loader can install and boot 26.2
python -m aiom.core.launcher fabric
python -m aiom.core.launcher neoforge
python -m aiom.core.launcher forge
python -m aiom.core.launcher paper

# Inspect what is available
python -m aiom.core.mcmeta          # version metadata + required Java
python -m aiom.core.javart          # locate a Java 25+ runtime
python -m aiom.core.modrinth 26.2   # ecosystem sizes + sample projects

# Run the benchmark
python -m aiom.bench.rndmrbench2 -n 100 --seed 20262
```

Reports are written to `reports/rndmrbench2-<mc>-<seed>.json`.

## Project layout

```
aiom/core/http.py       transport with curl fallback
aiom/core/mcmeta.py     Mojang manifest, libraries, jars
aiom/core/javart.py     Java runtime discovery
aiom/core/fabric.py     Fabric loader/intermediary resolution
aiom/core/paper.py      Paper v3 fill API
aiom/core/modrinth.py   Modrinth search, sampling, download
aiom/core/launcher.py   install + boot + classify for all four loaders
aiom/bench/rndmrbench2.py  the benchmark
```

## Environment notes

Two environment quirks are handled in code, and are worth knowing if you read
the source:

- **Installer HTTP is unreliable behind restrictive proxies.** The NeoForge and
  Forge installers use their own Java HTTP client, which can be reset. The
  launcher parses their reported maven coordinates and pre-fetches those jars
  with `curl`, then re-runs the installer so it resolves everything locally.
- **Windows argument files are mandatory.** NeoForge and Forge ship both
  `win_args.txt` and `unix_args.txt`; using the wrong one yields
  `ClassNotFoundException: net.neoforged.fml.startup.Server`.
- **netty `epoll`/`kqueue` errors on Windows are benign.** Those are Linux/macOS
  native transports and log an error on every platform, including successful
  ones. The benchmark does not treat them as failures.

## Licence

MIT — see [LICENSE](LICENSE).

Minecraft, Fabric, Forge, NeoForge, Paper and Modrinth are the properties of
their respective owners. This project is an independent tool and is not
affiliated with or endorsed by any of them.