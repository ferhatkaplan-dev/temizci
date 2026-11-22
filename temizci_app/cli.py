"""Temizci komut satırı arayüzü."""

from __future__ import annotations

import argparse
import json
import sys

from . import core, server

RISK_LABELS = {"safe": "güvenli", "caution": "dikkat", "risky": "riskli"}


def _print_scan(items: list[core.Item]) -> None:
    if not items:
        print("Temizlenecek bir şey bulunamadı.")
        return
    current_category = None
    total = 0
    for item in items:
        if item.category != current_category:
            current_category = item.category
            title = core.CATEGORIES.get(item.category, {}).get("title", item.category)
            print(f"\n{title.upper()}")
            print("-" * 78)
        total += item.size
        flags = []
        if item.requires_root:
            flags.append("sudo")
        if item.action == "command":
            flags.append("terminal")
        if item.action == "empty_trash":
            flags.append("çöp")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{core.human_size(item.size):>10}  {RISK_LABELS.get(item.risk, item.risk):<7}  {item.title}{suffix}")
        print(f"{'':>10}  {'':<7}  {item.detail}")
        if item.path:
            print(f"{'':>10}  {'':<7}  {item.path}")
        print(f"{'':>10}  {'':<7}  id: {item.id}")
    print("-" * 78)
    print(f"Toplam bulunan: {core.human_size(core.reclaimable_total(items))}")


def cmd_scan(args: argparse.Namespace) -> int:
    def progress(done: int, total: int, label: str) -> None:
        if not args.json:
            print(f"\r[{done}/{total}] {label}…".ljust(60), end="", file=sys.stderr, flush=True)

    items = core.scan_all(progress=progress)
    if not args.json:
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
    if args.json:
        print(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
    else:
        _print_scan(items)
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    print("Tarama yapılıyor…", file=sys.stderr)
    items = core.scan_all()
    by_id = {item.id: item for item in items}

    if args.ids:
        ids = [part.strip() for part in args.ids.split(",") if part.strip()]
        missing = [i for i in ids if i not in by_id]
        if missing:
            print(f"Bilinmeyen kimlik: {', '.join(missing)}", file=sys.stderr)
            return 2
    elif args.include_risky:
        ids = [item.id for item in items if item.action != "command"]
    else:
        ids = [item.id for item in items if item.risk == "safe" and item.action == "delete"]

    selected = [by_id[i] for i in ids]
    commands = [item for item in selected if item.action == "command"]
    deletable = [item for item in selected if item.action != "command"]
    total = sum(item.size for item in deletable)

    if not selected:
        print("Seçili ölçütlere uyan öğe yok.")
        return 0

    print(f"\n{len(deletable)} öğe, yaklaşık {core.human_size(total)}:")
    for item in deletable:
        print(f"  • [{RISK_LABELS.get(item.risk, item.risk)}] {item.title} ({core.human_size(item.size)})")
    if commands:
        print("\nTerminalde çalıştırılması gerekenler (bu komut çalıştırılmadı):")
        for item in commands:
            print(f"  $ {item.command}")

    if not args.yes:
        print("\nBu bir önizlemedir. Uygulamak için --yes ekleyin.")
        return 0
    if not deletable:
        return 0

    mode = "trash" if args.trash else "delete"
    results = core.clean_items(by_id, [item.id for item in deletable], mode=mode)
    freed = sum(r.get("freed", 0) for r in results)
    errors = [r for r in results if r.get("status") in {"error", "partial"}]
    for result in results:
        if result["status"] in {"deleted", "trashed"}:
            print(f"  ✓ {result['title']} — {core.human_size(result.get('freed', 0))}")
        elif result["status"] == "error":
            print(f"  ✗ {result['title']} — {result.get('error')}")
        elif result["status"] == "partial":
            print(f"  ! {result['title']} — kısmen silindi: {result.get('error')}")
    print(f"\nToplam boşaltılan: {core.human_size(freed)}")
    core.append_history(
        {
            "time": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": mode,
            "freed": freed,
            "items": [{"title": r["title"], "status": r["status"], "freed": r.get("freed", 0)} for r in results],
        }
    )
    return 1 if errors else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = core.system_report()
    disk = report["disk"]
    print(f"Temizci {report['version']} — {report['os']} ({report['kernel']})")
    print(f"Kullanıcı: {report['user']} (uid {report['euid']})  Ev: {report['home']}")
    print(
        f"Disk: {core.human_size(disk['used'])} / {core.human_size(disk['total'])} kullanılıyor "
        f"(%{disk['percent']}), boş: {core.human_size(disk['free'])}"
    )
    print(f"Araçlar: pacman={report['has_pacman']} paccache={report['has_paccache']} journalctl={report['has_journalctl']}")
    if report["snapshots"]:
        print(f"Btrfs snapshot sayısı: {len(report['snapshots'])} (silinen dosyalar alanı hemen boşaltmayabilir)")
    else:
        print("Btrfs snapshot: yok")
    if args.scan:
        print()
        _print_scan(core.scan_all())
    return 0


def cmd_support_report(args: argparse.Namespace) -> int:
    report = core.community_support_report()
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = core.write_community_support_report(args.output)
        print(f"Kişisel tanımlayıcıları ayıklanmış tanı raporu yazıldı: {destination}")
    else:
        sys.stdout.write(serialized)
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    server.run(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    try:
        from .desktop import main as desktop_main
    except ImportError as exc:
        print("PySide6 kurulu değil. CachyOS'ta: sudo pacman -S pyside6", file=sys.stderr)
        print(f"Ayrıntı: {exc}", file=sys.stderr)
        return 2
    return desktop_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="temizci",
        description="CachyOS/Arch için güvenli disk temizleyici.",
    )
    parser.add_argument("--version", action="version", version=f"Temizci {core.VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    gui = sub.add_parser("gui", help="Yerel masaüstü penceresini aç (PySide6)")
    gui.set_defaults(func=cmd_gui)

    ui = sub.add_parser("ui", help="İsteğe bağlı yerel web arayüzünü başlat")
    ui.add_argument("--port", type=int, default=8765, help="Dinlenecek port (varsayılan 8765)")
    ui.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    ui.set_defaults(func=cmd_ui)

    scan = sub.add_parser("scan", help="Sistemi tara ve nelerin silinebileceğini göster")
    scan.add_argument("--json", action="store_true", help="JSON çıktısı ver")
    scan.set_defaults(func=cmd_scan)

    clean = sub.add_parser("clean", help="Temizlik yap (varsayılan olarak yalnızca önizleme)")
    clean.add_argument("--ids", help="Virgülle ayrılmış öğe kimlikleri")
    clean.add_argument("--trash", action="store_true", help="Kalıcı silmek yerine çöp kutusuna taşı")
    clean.add_argument("--include-risky", action="store_true", help="Riskli öğeleri de seç")
    clean.add_argument("--yes", action="store_true", help="Önizlemeyi uygula")
    clean.set_defaults(func=cmd_clean)

    doctor = sub.add_parser("doctor", help="Sistem ve disk bilgilerini göster")
    doctor.add_argument("--scan", action="store_true", help="Ayrıca tarama yap")
    doctor.set_defaults(func=cmd_doctor)

    support = sub.add_parser(
        "support-report",
        help="Topluluk desteği için kişisel tanımlayıcıları ayıklanmış sistem raporu üret",
    )
    support.add_argument("--output", "-o", help="JSON raporunu dosyaya yaz (varsayılan: stdout)")
    support.set_defaults(func=cmd_support_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nİptal edildi.", file=sys.stderr)
        return 130
