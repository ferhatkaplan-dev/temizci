"""Güvenlik ve silme davranışı testleri."""

from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

from temizci_app import core
from temizci_app import i18n


class TemizciSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = {
            "HOME": core.HOME,
            "TRASH_DIR": core.TRASH_DIR,
            "ALLOWED_ROOTS": list(core.ALLOWED_ROOTS),
            "AUTOSTART_DIR": core.AUTOSTART_DIR,
            "DISABLED_AUTOSTART_DIR": core.DISABLED_AUTOSTART_DIR,
        }
        self.root = Path(tempfile.mkdtemp(prefix="temizci-test-", dir="/tmp")).resolve()
        core.HOME = self.root
        core.TRASH_DIR = self.root / "Trash"
        core.ALLOWED_ROOTS = [self.root]
        core.AUTOSTART_DIR = self.root / ".config" / "autostart"
        core.DISABLED_AUTOSTART_DIR = self.root / ".local" / "state" / "temizci" / "autostart-disabled"
        (self.root / ".config").mkdir()
        (self.root / ".ssh").mkdir()

    def tearDown(self) -> None:
        core.HOME = self.original["HOME"]
        core.TRASH_DIR = self.original["TRASH_DIR"]
        core.ALLOWED_ROOTS = self.original["ALLOWED_ROOTS"]
        core.AUTOSTART_DIR = self.original["AUTOSTART_DIR"]
        core.DISABLED_AUTOSTART_DIR = self.original["DISABLED_AUTOSTART_DIR"]
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    # -- yol doğrulama ---------------------------------------------------
    def test_rejects_relative_path(self) -> None:
        with self.assertRaises(core.SafetyError):
            core.assert_safe_path("relative/path")

    def test_rejects_parent_traversal(self) -> None:
        target = self.root / "cache" / ".." / "secret"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
        with self.assertRaises(core.SafetyError):
            core.assert_safe_path(target)

    def test_rejects_home_itself(self) -> None:
        with self.assertRaises(core.SafetyError):
            core.assert_safe_path(self.root)

    def test_rejects_protected_directories(self) -> None:
        for protected in (self.root / ".config", self.root / ".ssh"):
            with self.assertRaises(core.SafetyError):
                core.assert_safe_path(protected)

    def test_rejects_outside_allowed_roots(self) -> None:
        with self.assertRaises(core.SafetyError):
            core.assert_safe_path("/etc/passwd")

    def test_allows_nested_cache(self) -> None:
        cache = self.root / ".cache" / "app"
        cache.mkdir(parents=True)
        (cache / "file.bin").write_bytes(b"x" * 64)
        self.assertEqual(core.assert_safe_path(cache), cache)

    def test_symlink_is_unlinked_not_followed(self) -> None:
        target = self.root / "important.txt"
        target.write_text("korunmalı")
        link = self.root / ".cache" / "link"
        link.parent.mkdir()
        link.symlink_to(target)
        core.delete_permanently(link)
        self.assertFalse(link.exists())
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "korunmalı")

    def test_symlink_outside_allowed_parent_rejected(self) -> None:
        link = Path("/tmp") / "temizci-outside-link"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to("/etc")
        try:
            with self.assertRaises(core.SafetyError):
                core.assert_safe_path(link)
        finally:
            link.unlink(missing_ok=True)

    # -- silme -----------------------------------------------------------
    def test_permanent_delete_directory(self) -> None:
        cache = self.root / ".cache" / "big"
        cache.mkdir(parents=True)
        (cache / "a.bin").write_bytes(b"a" * 2048)
        freed = core.delete_permanently(cache)
        self.assertFalse(cache.exists())
        self.assertGreater(freed, 0)

    def test_move_to_trash_creates_info(self) -> None:
        cache = self.root / ".cache" / "movable"
        cache.mkdir(parents=True)
        (cache / "a.bin").write_bytes(b"a" * 1024)
        freed = core.move_to_trash(cache)
        self.assertFalse(cache.exists())
        self.assertGreater(freed, 0)
        files = list((core.TRASH_DIR / "files").iterdir())
        infos = list((core.TRASH_DIR / "info").glob("*.trashinfo"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(infos), 1)
        self.assertIn("Path=", infos[0].read_text())

    def test_empty_trash(self) -> None:
        cache = self.root / ".cache" / "trashme"
        cache.mkdir(parents=True)
        (cache / "a.bin").write_bytes(b"a" * 1024)
        core.move_to_trash(cache)
        freed, count = core.empty_trash()
        self.assertEqual(count, 1)
        self.assertGreater(freed, 0)
        self.assertFalse(any((core.TRASH_DIR / "files").iterdir()))

    # -- temizlik seçimi -------------------------------------------------
    def _item(self, action: str = "delete", command: str | None = None) -> core.Item:
        path = self.root / ".cache" / "x"
        path.mkdir(parents=True, exist_ok=True)
        return core.Item(
            id="test:1",
            rule_id="test",
            title="Test",
            detail="",
            path=str(path),
            size=10,
            files=1,
            risk="safe",
            category="caches",
            action=action,
            paths=[str(path)] if action == "delete" else [],
            command=command,
            selected=True,
        )

    def test_clean_rejects_unknown_id(self) -> None:
        results = core.clean_items({}, ["yok:1"], "delete")
        self.assertEqual(results[0]["status"], "error")

    def test_command_is_not_executed(self) -> None:
        item = self._item(action="command", command="touch /tmp/temizci-should-not-run")
        results = core.clean_items({item.id: item}, [item.id], "delete")
        self.assertEqual(results[0]["status"], "needs_terminal")
        self.assertEqual(results[0]["command"], "touch /tmp/temizci-should-not-run")
        self.assertFalse(Path("/tmp/temizci-should-not-run").exists())

    def test_trash_mode_never_empties_trash(self) -> None:
        trash_files = core.TRASH_DIR / "files"
        trash_files.mkdir(parents=True)
        protected = trash_files / "keep-me.txt"
        protected.write_text("geri alınabilir")
        item = core.Item(
            id="trash:test",
            rule_id="trash",
            title="Çöp kutusu",
            detail="",
            path=str(trash_files),
            size=20,
            files=1,
            risk="caution",
            category="trash",
            action="empty_trash",
            paths=[str(trash_files)],
        )
        results = core.clean_items({item.id: item}, [item.id], mode="trash")
        self.assertEqual(results[0]["status"], "error")
        self.assertTrue(protected.exists())

    def test_delete_item(self) -> None:
        item = self._item()
        results = core.clean_items({item.id: item}, [item.id], "delete")
        self.assertEqual(results[0]["status"], "deleted")
        self.assertFalse(Path(item.path).exists())

    def test_clean_honors_excluded_paths(self) -> None:
        item = self._item()
        results = core.clean_items(
            {item.id: item},
            [item.id],
            "delete",
            excludes=[str(self.root / ".cache")],
        )
        self.assertEqual(results[0]["status"], "error")
        self.assertTrue(Path(item.path).exists())

    def test_exclude_validation_rejects_relative_and_root(self) -> None:
        with self.assertRaises(ValueError):
            core.normalize_excludes(["relative/path"])
        with self.assertRaises(ValueError):
            core.normalize_excludes(["/"])
        allowed = self.root / "Projects"
        allowed.mkdir()
        self.assertEqual(core.normalize_excludes([str(allowed)]), (allowed,))

    def test_scan_options_filter_categories_exclusions_and_fast_mode(self) -> None:
        keep = self.root / ".cache" / "keep"
        blocked = self.root / ".cache" / "blocked"
        large = self.root / "Downloads" / "large.bin"
        keep.mkdir(parents=True)
        blocked.mkdir()
        large.parent.mkdir()
        large.write_bytes(b"x" * 16)

        def keep_collector(cache):
            return [core._make_item("keep", "keep", "", keep, 10, 1, "safe", "caches")]

        def blocked_collector(cache):
            return [core._make_item("blocked", "blocked", "", blocked, 10, 1, "safe", "caches")]

        def files_collector(cache):
            return [core._make_item("large", "large", "", large, 10, 1, "caution", "files", "trash")]

        active_limits: list[int] = []

        def limit_collector(cache):
            active_limits.append(core._ACTIVE_LARGE_LIMIT.get())
            return []

        original = core.COLLECTORS
        core.COLLECTORS = [
            ("caches", "A", keep_collector),
            ("caches", "B", blocked_collector),
            ("files", "C", files_collector),
            ("files", "limit", limit_collector),
        ]
        try:
            partials: list[list[core.Item]] = []
            stats: dict = {}
            items = core.scan_all(
                options=core.ScanOptions(
                    categories=("caches",),
                    excludes=(str(blocked),),
                    workers=2,
                ),
                stats=stats,
                on_partial=partials.append,
            )
            self.assertEqual([item.title for item in items], ["keep"])
            self.assertEqual(stats["items"], 1)
            self.assertEqual(stats["workers"], 2)
            self.assertTrue(partials)

            fast_items = core.scan_all(options=core.ScanOptions(mode="fast", workers=1))
            self.assertEqual({item.title for item in fast_items}, {"keep", "blocked"})
            thorough_stats: dict = {}
            core.scan_all(options=core.ScanOptions(mode="thorough", workers=1), stats=thorough_stats)
            self.assertIn(100, active_limits)
            self.assertEqual(core._ACTIVE_LARGE_LIMIT.get(), 40)
        finally:
            core.COLLECTORS = original

    def test_workflow_profiles_select_expected_items(self) -> None:
        def make(ident: str, risk: str, category: str, running: bool = False) -> core.Item:
            return core.Item(
                id=ident,
                rule_id="test",
                title=ident,
                detail="",
                path=None,
                size=1,
                files=1,
                risk=risk,
                category=category,
                action="delete",
                meta={"running": running},
            )

        items = [
            make("safe-cache", "safe", "caches"),
            make("safe-browser", "safe", "browsers"),
            make("caution-dev", "caution", "dev"),
            make("caution-backup", "caution", "backups"),
            make("running-cache", "safe", "caches", running=True),
            make("risky-file", "risky", "files"),
        ]
        self.assertEqual(core.select_items(items, "recommended"), {"safe-cache", "safe-browser"})
        self.assertEqual(
            core.select_items(items, "deep"),
            {"safe-cache", "safe-browser", "caution-dev", "caution-backup"},
        )
        self.assertEqual(
            core.select_items(items, "developer"),
            {"safe-cache", "safe-browser", "caution-dev"},
        )
        self.assertEqual(
            core.select_items(items, "low-disk"),
            {"safe-cache", "safe-browser", "caution-dev"},
        )
        self.assertEqual(core.select_items(items, "privacy"), {"safe-cache", "safe-browser"})
        self.assertEqual(core.select_items(items, "manual"), set())

    # -- biçimlendirme ---------------------------------------------------
    def test_parse_size(self) -> None:
        self.assertEqual(core.parse_size("1.63 GiB"), int(1.63 * 1024**3))
        self.assertEqual(core.parse_size("46.4M"), int(46.4 * 1024**2))
        self.assertEqual(core.parse_size("512 B"), 512)

    def test_parse_pacman_info(self) -> None:
        output = """Name            : sample-app
Version         : 2.1-1
Description     : Example package
Installed Size  : 1,25 MiB
Install Reason  : Explicitly installed
Required By     : None
"""
        parsed = core.parse_pacman_info(output)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "sample-app")
        self.assertEqual(parsed[0]["size"], int(1.25 * 1024**2))

    def test_protected_package_commands_rejected(self) -> None:
        with self.assertRaises(ValueError):
            core.package_removal_command(["glibc"])

    def test_user_autostart_disable_and_restore_is_reversible(self) -> None:
        core.AUTOSTART_DIR.mkdir(parents=True)
        source = core.AUTOSTART_DIR / "demo.desktop"
        contents = "[Desktop Entry]\nType=Application\nName=Demo\nExec=demo --start\n"
        source.write_text(contents, encoding="utf-8")
        self.assertEqual(core.list_user_autostart()[0]["name"], "Demo")
        self.assertTrue(core.disable_user_autostart(["demo.desktop"])[0]["ok"])
        self.assertFalse(source.exists())
        self.assertEqual(core.list_disabled_autostart()[0]["filename"], "demo.desktop")
        self.assertTrue(core.restore_user_autostart(["demo.desktop"])[0]["ok"])
        self.assertEqual(source.read_text(encoding="utf-8"), contents)

    def test_community_report_omits_personal_paths_and_names(self) -> None:
        report = core.community_support_report()
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertTrue(report["privacy"]["redacted"])
        self.assertNotIn(str(core.HOME), serialized)
        self.assertNotIn(os.environ.get("USER", "__missing_user__"), serialized)
        self.assertNotIn("root_device", report["performance"])
        self.assertNotIn("enabled_units", report["performance"])
        self.assertNotIn("autostart", report["performance"])

    def test_boot_summary_only_contains_timing(self) -> None:
        value = "Startup finished in 800ms (kernel) + 1.2s (initrd) + 19.4s (userspace) = 21.4s."
        summary = core._redact_boot_summary(value)
        self.assertEqual(summary, "800ms (kernel) + 1.2s (initrd) + 19.4s (userspace) = 21.4s")
        self.assertEqual(core._redact_boot_summary("host-specific output /home/alice"), "ölçülemedi")

    def test_support_report_file_is_private_and_valid_json(self) -> None:
        destination = self.root / "report.json"
        report = {"privacy": {"redacted": True}, "example": "ok"}
        self.assertEqual(core.write_community_support_report(destination, report), destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_english_and_turkish_runtime_translations(self) -> None:
        original = i18n.get_language()
        try:
            i18n.set_language("en")
            self.assertEqual(i18n.tr("Uygulamalar ve paketler"), "Apps & packages")
            self.assertEqual(i18n.tr("3 öğe seçildi · 1.5 MB"), "3 items selected · 1.5 MB")
            self.assertEqual(i18n.tr("85% dolu"), "85% used")
            self.assertEqual(i18n.tr("3 seçili · 12 / 303 paket gösteriliyor"), "3 selected · showing 12 of 303 packages")
            self.assertEqual(i18n.tr("Artık paketler (5 adet)"), "Orphan packages (5)")
            self.assertEqual(i18n.tr("Tarama tamamlandı · 3 öğe · 1.2 sn"), "Scan complete · 3 items · 1.2 s")
            self.assertEqual(i18n.tr("Tarama sürüyor · 3 öğe bulundu…"), "Scan in progress · 3 items found…")
            self.assertEqual(i18n.tr("Hariç tutulan yol mutlak olmalı: x"), "Excluded path must be absolute: x")
            self.assertEqual(i18n.tr("Kök dizin hariç tutulamaz: /"), "The filesystem root cannot be excluded: /")
            self.assertEqual(i18n.tr("Düşük disk alanı"), "Low disk space")
            self.assertEqual(i18n.tr("Geliştirici"), "Developer")
            i18n.set_language("tr")
            self.assertEqual(i18n.tr("Apps & packages"), "Uygulamalar ve paketler")
            self.assertEqual(i18n.tr("85% used"), "85% dolu")
            self.assertEqual(i18n.tr("Scan complete · 3 items · 1.2 s"), "Tarama tamamlandı · 3 öğe · 1.2 sn")
            self.assertEqual(i18n.tr("Low disk space"), "Düşük disk alanı")
        finally:
            i18n.set_language(original)

    def test_human_size(self) -> None:
        self.assertEqual(core.human_size(0), "0 B")
        self.assertIn("GB", core.human_size(5 * 1024**3))


if __name__ == "__main__":
    unittest.main()
