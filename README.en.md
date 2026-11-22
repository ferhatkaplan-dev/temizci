# Temizci — Arch Linux Disk Cleaner & System Maintenance

A free, open-source **disk cleaner and system maintenance app for Arch Linux**
and Arch-based distributions such as CachyOS. Temizci finds application and
browser caches, old backups, developer leftovers, large files, and removable
Pacman package candidates. It is privacy-first and local-only: review every
proposed cleanup and explicitly confirm it. Temizci never silently deletes
files, removes packages, or disables system services.

[![Tests](https://github.com/ferhatkaplan-dev/temizci/actions/workflows/test.yml/badge.svg)](https://github.com/ferhatkaplan-dev/temizci/actions/workflows/test.yml)
[![MIT License](https://img.shields.io/github/license/ferhatkaplan-dev/temizci)](LICENSE)

**Arch Linux · CachyOS · Pacman · Linux disk cleanup · Python · PySide6**

**[Türkçe README](README.md)**

## Highlights

- Native PySide6 desktop app, optional loopback-only web UI, and CLI.
- Read-only scan previews, explicit confirmation, risk labels, and optional trash.
- Pacman inventory and orphan candidates; no package is preselected for removal.
- Pacman's own transaction preview is shown before a removal command is opened
  in a terminal. The user still reviews Pacman's prompt and enters any password.
- Read-only memory, boot, power-profile, SSD TRIM, and service diagnostics.
- Per-user autostart entries can be reversibly disabled and restored; system
  services are informational only.
- A privacy-conscious support report for community troubleshooting.
- Turkish and English native UI; switch languages instantly in **Settings → Language**.

## Install and run

Requirements: Python 3.11+, PySide6 for the native GUI. On Arch Linux or CachyOS:

```bash
sudo pacman -S python pyside6
git clone https://github.com/ferhatkaplan-dev/temizci.git
cd temizci
./install.sh
temizci gui
```

Run without installing with `./temizci gui`. Other interfaces:

```bash
temizci scan
temizci clean                 # preview only
temizci doctor
temizci support-report        # redacted JSON to stdout
temizci support-report -o report.json
temizci ui                    # optional UI at 127.0.0.1
```

Review a support report before sharing it. It omits usernames, hostnames, home
paths, disk identifiers, file paths, package names, service names, and autostart
commands. Hardware and system measurements may still be identifying in context.

## Safety

- Scans do not mutate the system; scheduled scans run only while the desktop app
  is open and never auto-clean.
- No package or risky file is automatically selected for removal.
- Core system packages are protected in the GUI; pacman remains responsible for
  its dependency checks and final transaction confirmation.
- Privileged commands are not executed by Temizci. They are presented in a
  terminal for the user to inspect and confirm.
- Performance recommendations are based on observed system signals; disabling
  services is intentionally not automated.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and safety expectations.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile temizci_app/*.py
node --check temizci_app/web/app.js
```

Temizci is licensed under the [MIT License](LICENSE).
