# Performance and system tuning

## Improving the computer's performance

The desktop **Performance & startup** page combines read-only diagnostics with
explicit, reversible actions. The power-profile workflow offers Balanced,
Performance, or Power saver when `powerprofilesctl list` reports that the
hardware supports them. Temizci confirms before calling
`powerprofilesctl set <profile>` and stores the previous profile so it can be
restored from the same page. It runs as the logged-in user through
power-profiles-daemon; no sudo command or persistent kernel tweak is issued.
Depending on system policy, the desktop authorization agent may still request
permission to switch profiles.

Performance mode can improve responsiveness for CPU-bound work, but can also
increase power draw, heat, fan noise, and battery drain. Power saver trades peak
responsiveness for lower energy use. Balanced is the default recommendation;
the useful choice depends on the device, power source, cooling, and workload.
No profile guarantees a measurable speedup.

The page also reports RAM/swap usage, boot timing, enabled system units,
SSD discard support, and user autostart entries. User autostart entries can be
disabled individually and restored. System services are never disabled by an
automatic optimizer. SSD TRIM is offered only when support is detected; it is
periodic storage maintenance, not a CPU-performance setting. Freeing disk space
can make room for updates and applications but will not fix a CPU or RAM
bottleneck.

## Scan performance

Temizci scans local filesystems only. No network calls are made while scanning,
and no cleanup is performed by the scan engine.

## What the scan does

Each category is an independent collector. Collectors may walk cache trees,
inspect Pacman metadata, or run read-only system commands. The final result is
deduplicated by physical path and sorted by category, risk, and size.

## Tuning knobs

| Option | Default | Notes |
|---|---|---|
| `mode` | `balanced` | `fast` skips large-file discovery; `thorough` raises the large-file limit to 100. |
| `workers` | `2` | Runs independent collectors concurrently. |
| `categories` | all | Restricting categories avoids unnecessary filesystem walks. |
| `excludes` | empty | Excluded paths are pruned during large-file traversal and filtered from every result. |
| `large_file_limit` | `40` (`100` in thorough) | Caps the number of large-file rows, not the traversal itself. |

## Why 2 workers is the default

Most of a scan is Python code iterating over directory entries. Python threads
share the GIL, so adding workers does not scale linearly and can increase disk
contention. In local testing, two workers reduced wall-clock time for a typical
cache scan, while four or more workers were often slower. The setting is
therefore intentionally small by default and capped for sanity. Systems with
slow or network-backed storage may benefit from `workers=1`.

## Algorithmic choices

- Directory walks use `os.scandir` with `DirEntry.stat()` to avoid extra
  `Path`/`lstat` calls.
- Large-file discovery prunes hidden directories, known project/build
  directories, backup markers, and user-excluded paths.
- Large-file discovery retains only the top N candidates in a min-heap instead
  of storing and sorting every matching file. The traversal remains complete,
  but auxiliary memory is bounded by the result limit and selection work is
  `O(n log N)` rather than sorting all `n` candidates.
- `walk_size` checks `DirEntry.is_dir(follow_symlinks=False)` before requesting
  file metadata, avoiding a metadata call for directory entries on filesystems
  that report entry types directly.
- Collectors share an in-memory size cache during a scan. Concurrent collectors
  can still repeat work if they reach the same uncached path at the same time.
- Partial results are emitted after each collector completes, so the UI can show
  useful rows before the slowest collector finishes.
- Scans are serialized in the desktop UI; a second scan cannot start while one
  is running.

## Measuring

```bash
time temizci scan --mode balanced --stats --json > /tmp/scan.json
```

`--stats` reports total elapsed time and per-collector durations on `stderr`.
Use the same mode and category set when comparing runs. The first run after a
reboot is usually slower because the operating system's file cache is cold.

In a synthetic local test with 12,000 qualifying files, top-40 discovery took
about 0.06 s versus 0.28 s for collecting and sorting all candidates. This is a
microbenchmark, not a promised whole-scan speedup; actual results depend on
storage, filesystem, and directory contents.

## Correctness over speed

Temizci does not persist size estimates between scans. A cached directory size
can become stale when a file changes in place, and this app presents reclaimable
space as a safety signal. Recomputing sizes keeps previews honest at the cost of
repeat scan time; use `fast`, category scoping, or exclusions when that cost
matters.
