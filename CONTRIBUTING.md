# Contributing to Temizci

Thank you for helping make Linux maintenance safer and more approachable.

## Before opening an issue

- Search existing issues first and describe one problem per issue.
- Include your distro/version, desktop environment, Python version, Temizci version (e.g. 1.3.0),
  and exact reproduction steps.
- Prefer the GUI's **Tanı raporu** button (or `temizci support-report`) and review
  the JSON before attaching it. Never post passwords, tokens, private paths, or
  unredacted logs.
- Feature requests should explain the user problem, expected behavior, and safety
  or reversibility implications.

## Development

Temizci targets Arch Linux and Arch-based distributions. Keep the core usable
without Qt so safety behavior can be tested independently.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile temizci_app/*.py
node --check temizci_app/web/app.js
QT_QPA_PLATFORM=offscreen python3 -m temizci_app gui
```

For GUI smoke tests, close the window to finish. PySide6 is required for GUI
development; core tests use only the Python standard library.

## Safety requirements

- Never run destructive or privileged operations during scans.
- Require a clear preview and explicit confirmation for mutations.
- Do not silently choose risky items or infer that software is unused.
- Prefer reversible actions; explain what cannot be undone and what may be
  re-downloaded or reconfigured.
- Validate paths and command arguments at the point of use; never trust UI input.
- Add tests for both the intended operation and unsafe inputs.
- Don't claim a performance improvement unless it is measured and reproducible.

## Pull requests

Keep changes focused, include tests and documentation, and state which commands
you ran. UI changes should include a screenshot when practical. New dependencies
need a clear justification and a supported-version note.

Temizci provides Turkish and English UI copy. Add translations to
`temizci_app/i18n.py` for new user-facing strings, keep both languages clear,
and avoid unexplained technical jargon.
