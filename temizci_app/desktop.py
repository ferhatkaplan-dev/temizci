"""PySide6 ile yerel masaüstü arayüzü."""

from __future__ import annotations

import os
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# The package and diagnostics views are intentionally built from native Qt
# widgets; no privileged operation is performed in a worker thread.
from PySide6.QtWidgets import QAbstractItemView, QPlainTextEdit

from . import i18n


def _message_box(kind: str, parent: QWidget | None, title: str, text: str, *args):
    """Show a translated standard dialog while preserving its Qt button choices."""
    return getattr(QMessageBox, kind)(parent, i18n.tr(title), i18n.tr(text), *args)

from . import core

ACCENT = "#48e5c2"
RISK_LABELS = {"safe": "GÜVENLİ", "caution": "DİKKAT", "risky": "RİSKLİ"}

STYLES = f"""
QMainWindow, QWidget {{ background: #091015; color: #e8f1f3; font-family: 'Inter', 'Noto Sans', sans-serif; font-size: 13px; }}
QFrame#panel {{ background: #111b22; border: 1px solid #26353d; border-radius: 14px; }}
QFrame#item {{ background: #111b22; border: 1px solid #26353d; border-radius: 10px; }}
QFrame#item[selected="true"] {{ border: 1px solid #348e7c; background: #10211f; }}
QLabel#brand {{ color: #f2fbfa; font-size: 25px; font-weight: 700; }}
QLabel#subtitle {{ color: #92a6ae; font-size: 12px; }}
QLabel#metric {{ color: #f2fbfa; font-size: 23px; font-weight: 700; }}
QLabel#metricAccent {{ color: {ACCENT}; font-size: 23px; font-weight: 700; }}
QLabel#muted {{ color: #93a7b0; }}
QLabel#dim {{ color: #637781; font-size: 11px; }}
QLabel#section {{ color: #e8f1f3; font-size: 13px; font-weight: 700; letter-spacing: 1px; padding: 8px 2px; }}
QLabel#safe {{ color: #50e0bd; background: #15332f; border: 1px solid #255c52; border-radius: 5px; padding: 2px 6px; font-size: 9px; font-weight: 700; }}
QLabel#caution {{ color: #ffd178; background: #342b19; border: 1px solid #665128; border-radius: 5px; padding: 2px 6px; font-size: 9px; font-weight: 700; }}
QLabel#risky {{ color: #ff8585; background: #351f22; border: 1px solid #67383c; border-radius: 5px; padding: 2px 6px; font-size: 9px; font-weight: 700; }}
QLabel#blueTag {{ color: #9acbff; background: #14283b; border: 1px solid #294865; border-radius: 5px; padding: 2px 6px; font-size: 9px; font-weight: 700; }}
QPushButton {{ background: #18252d; color: #e8f1f3; border: 1px solid #33434c; border-radius: 9px; padding: 9px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #21323b; border-color: #50636d; }}
QPushButton:disabled {{ color: #52626a; background: #131c21; }}
QPushButton#primary {{ color: #061310; background: {ACCENT}; border: 0; font-weight: 700; }}
QPushButton#primary:hover {{ background: #6bf2d1; }}
QPushButton#danger {{ color: #2a0909; background: #ff7777; border: 0; font-weight: 700; }}
QPushButton#danger:hover {{ background: #ff9292; }}
QPushButton#filter[active="true"] {{ color: {ACCENT}; background: #14312d; border-color: #27685a; }}
QLineEdit, QComboBox {{ background: #0b1318; color: #e8f1f3; border: 1px solid #2b3b43; border-radius: 9px; padding: 9px 11px; selection-background-color: #247862; }}
QComboBox QAbstractItemView {{ background: #142029; color: #e8f1f3; selection-background-color: #247862; }}
QCheckBox, QRadioButton {{ spacing: 8px; color: #c5d2d6; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 17px; height: 17px; }}
QCheckBox::indicator {{ border-radius: 5px; border: 1px solid #52636b; background: #0c1419; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator {{ border-radius: 9px; border: 1px solid #52636b; background: #0c1419; }}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 4px solid #0c1419; }}
QProgressBar {{ background: #1b2a32; border: 0; border-radius: 5px; height: 9px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #31434c; border-radius: 5px; min-height: 28px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QTabWidget::pane {{ border: 1px solid #26353d; border-radius: 12px; background: #0b1318; top: -1px; }}
QTabBar::tab {{ background: #101920; color: #92a6ae; border: 1px solid #26353d; padding: 10px 18px; margin-right: 4px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ color: {ACCENT}; background: #14231f; border-bottom-color: #14231f; }}
QTreeWidget {{ background: #0c1419; alternate-background-color: #111b22; border: 1px solid #26353d; border-radius: 8px; outline: 0; }}
QTreeWidget::item {{ min-height: 28px; padding: 4px 3px; }}
QTreeWidget::item:selected {{ background: #17362f; color: #f2fbfa; }}
QHeaderView::section {{ color: #a5b7bd; background: #142029; border: 0; border-bottom: 1px solid #26353d; padding: 7px; font-weight: 600; }}
QPlainTextEdit {{ background: #0c1419; color: #c9d6da; border: 1px solid #26353d; border-radius: 8px; padding: 8px; selection-background-color: #247862; }}
QDialog {{ background: #111b22; }}
QStatusBar {{ background: #0c1419; color: #92a6ae; border-top: 1px solid #26353d; }}
"""


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    finished_items = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            items = core.scan_all(progress=lambda done, total, label: self.progress.emit(done, total, label))
            self.finished_items.emit(items)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CleanWorker(QThread):
    finished_results = Signal(object)

    def __init__(self, items: dict[str, core.Item], ids: list[str], mode: str):
        super().__init__()
        self.items = items
        self.ids = ids
        self.mode = mode

    def run(self) -> None:
        results = core.clean_items(self.items, self.ids, mode=self.mode)
        core.append_history(
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "mode": self.mode,
                "freed": sum(result.get("freed", 0) for result in results),
                "items": [
                    {"title": result["title"], "status": result["status"], "freed": result.get("freed", 0)}
                    for result in results
                ],
            }
        )
        self.finished_results.emit(results)


class PackageWorker(QThread):
    finished_packages = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            packages = core.collect_installed_packages()
            if not packages:
                self.failed.emit("Kurulu paket listesi alınamadı. pacman kurulu mu?")
                return
            self.finished_packages.emit(packages)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class PackagePreviewWorker(QThread):
    finished_plan = Signal(object)
    failed = Signal(str)

    def __init__(self, names: list[str]):
        super().__init__()
        self.names = names

    def run(self) -> None:
        try:
            self.finished_plan.emit(core.preview_package_removal(self.names))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class PerformanceWorker(QThread):
    finished_report = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.finished_report.emit(core.performance_report())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class PackagePreviewDialog(QDialog):
    def __init__(self, plan: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Paket kaldırma işlem planı")
        self.setMinimumSize(640, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        title = QLabel("Pacman işlem planı")
        title.setObjectName("brand")
        title.setStyleSheet("font-size:19px")
        layout.addWidget(title)
        source = ", ".join(plan["selected"])
        summary = QLabel(
            (
                f"Selected: {source}\n"
                f"Packages Pacman will remove (including dependencies): {len(plan['targets'])}\n"
                f"Estimated installed size: {core.human_size(plan['size'])}"
            )
            if i18n.get_language() == "en"
            else (
                f"Seçtiklerin: {source}\n"
                f"Pacman'ın kaldıracağı paketler (bağımlılıkları dahil): {len(plan['targets'])}\n"
                f"Kurulu boyut tahmini: {core.human_size(plan['size'])}"
            )
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        listing = QPlainTextEdit()
        listing.setReadOnly(True)
        listing.setPlainText(
            "\n".join(
                f"{package['name']}  {package['version']}  ·  {core.human_size(package['size'])}"
                for package in plan["packages"]
            )
            or "\n".join(plan["targets"])
        )
        layout.addWidget(listing, 1)
        command = QPlainTextEdit()
        command.setReadOnly(True)
        command.setMaximumHeight(54)
        command.setPlainText(plan["command"])
        layout.addWidget(command)
        note = QLabel(
            "Uygulama paketi kaldırmaz. Devam edersen komut terminalde açılır; "
            "sudo parolanı ve Pacman'ın son işlem onayını terminalde kendin verirsin."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#ffd178; background:#342b19; padding:9px; border-radius:8px")
        layout.addWidget(note)
        self.ack = QCheckBox("Kaldırılacak paket listesini ve bağımlılıkları inceledim.")
        layout.addWidget(self.ack)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.proceed = buttons.addButton("Terminalde incelemeye devam et", QDialogButtonBox.ButtonRole.AcceptRole)
        self.proceed.setObjectName("danger")
        self.proceed.setEnabled(False)
        self.ack.toggled.connect(self.proceed.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate_widget_tree(self)


class ConfirmDialog(QDialog):
    def __init__(self, items: list[core.Item], default_mode: str = "trash", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Temizliği onayla")
        self.setMinimumWidth(520)
        self.mode = "delete"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Seçilen öğeleri temizle")
        title.setObjectName("brand")
        title.setStyleSheet("font-size: 19px")
        layout.addWidget(title)
        layout.addWidget(QLabel("Aşağıdaki öğeleri kontrol et. İşlem, onay vermeden başlamaz."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(210)
        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 8, 0)
        rows_layout.setSpacing(5)
        for item in items:
            row_widget = QWidget()
            row = QVBoxLayout(row_widget)
            row.setContentsMargins(0, 4, 0, 4)
            title_line = QHBoxLayout()
            name = QLabel(item.title)
            name.setWordWrap(True)
            amount = QLabel(core.human_size(item.size))
            amount.setObjectName("muted")
            title_line.addWidget(name, 1)
            title_line.addWidget(amount)
            row.addLayout(title_line)
            if item.path:
                path = QLabel(item.path.replace(str(core.HOME), "~", 1))
                path.setObjectName("dim")
                path.setWordWrap(True)
                row.addWidget(path)
            description = QLabel(item.detail)
            description.setObjectName("muted")
            description.setWordWrap(True)
            row.addWidget(description)
            rows_layout.addWidget(row_widget)
        scroll.setWidget(rows)
        layout.addWidget(scroll)

        self.permanent = QRadioButton("Kalıcı sil — alan hemen açılır, geri alınamaz")
        self.permanent.setChecked(default_mode == "delete")
        self.trash = QRadioButton("Çöp kutusuna taşı — geri alınabilir, alan sonra açılır")
        self.trash.setChecked(default_mode != "delete")
        self.mode = default_mode
        self.permanent.toggled.connect(lambda checked: setattr(self, "mode", "delete" if checked else "trash"))
        layout.addWidget(self.permanent)
        layout.addWidget(self.trash)

        if any(item.risk == "risky" for item in items):
            warning = QLabel("⚠ Riskli yedek veya büyük dosyalar seçili. Silmeden önce adlarını ve boyutlarını kontrol et.")
            warning.setWordWrap(True)
            warning.setStyleSheet("color:#ff9292; background:#351f22; padding:9px; border-radius:8px")
            layout.addWidget(warning)
        if any(item.action == "empty_trash" for item in items):
            note = QLabel("Çöp kutusunu boşaltmak kalıcıdır; çöp kutusu seçiliyse 'Çöpe taşı' modu uygulanmaz.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#ffd178; background:#342b19; padding:9px; border-radius:8px")
            layout.addWidget(note)

        self.ack = QCheckBox("Listeyi ve silme modunu kontrol ettim; işlemi onaylıyorum.")
        layout.addWidget(self.ack)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.confirm = buttons.addButton("Onayla ve temizle", QDialogButtonBox.ButtonRole.AcceptRole)
        self.confirm.setObjectName("danger")
        self.confirm.setEnabled(False)
        self.ack.toggled.connect(self.confirm.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate_widget_tree(self)


class SettingsDialog(QDialog):
    """Kullanıcı tercihleri; hiçbir ayar otomatik silme izni vermez."""

    def __init__(self, settings: QSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Temizci ayarları")
        self.setMinimumWidth(480)
        self.settings = settings
        self.language = QComboBox()
        self.language.addItem("Türkçe", "tr")
        self.language.addItem("English", "en")
        current_language = str(settings.value("ui/language", "tr"))
        self.language.setCurrentIndex(max(0, self.language.findData(current_language)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        heading = QLabel("İş akışı ve tercihler")
        heading.setObjectName("brand")
        heading.setStyleSheet("font-size:19px")
        layout.addWidget(heading)
        intro = QLabel("Bu ayarlar tarama ve ön seçimleri düzenler. Hiçbir ayar otomatik dosya silmez.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Dil", self.language)
        self.profile = QComboBox()
        self.profile.addItem("Önerilen — yalnızca güvenli öğeler", "recommended")
        self.profile.addItem("Derin inceleme — güvenli + dikkat", "deep")
        self.profile.addItem("Manuel — otomatik seçim yok", "manual")
        current_profile = str(settings.value("workflow/profile", "recommended"))
        self.profile.setCurrentIndex(max(0, self.profile.findData(current_profile)))
        form.addRow("Varsayılan tarama profili", self.profile)

        self.mode = QComboBox()
        self.mode.addItem("Çöp kutusuna taşı (önerilen)", "trash")
        self.mode.addItem("Kalıcı sil", "delete")
        current_mode = str(settings.value("cleanup/default_mode", "trash"))
        self.mode.setCurrentIndex(max(0, self.mode.findData(current_mode)))
        form.addRow("Varsayılan temizlik yöntemi", self.mode)

        self.threshold = QSpinBox()
        self.threshold.setRange(50, 4096)
        self.threshold.setSuffix(" MB")
        self.threshold.setSingleStep(50)
        self.threshold.setValue(int(settings.value("scan/large_file_mb", 150)))
        form.addRow("Büyük dosya eşiği", self.threshold)

        self.auto_scan = QCheckBox("Uygulama açıldığında otomatik tara")
        self.auto_scan.setChecked(settings.value("scan/auto", True, type=bool))
        form.addRow("Başlangıç", self.auto_scan)

        self.scheduled_scan = QCheckBox("Uygulama açıkken düzenli tarama yap")
        self.scheduled_scan.setChecked(settings.value("scan/scheduled", False, type=bool))
        form.addRow("Planlı tarama", self.scheduled_scan)
        self.schedule_interval = QComboBox()
        for label, minutes in (("Her 30 dakikada", 30), ("Saatte bir", 60), ("6 saatte bir", 360), ("Günde bir", 1440)):
            self.schedule_interval.addItem(label, minutes)
        current_interval = int(settings.value("scan/interval_minutes", 360))
        self.schedule_interval.setCurrentIndex(max(0, self.schedule_interval.findData(current_interval)))
        self.schedule_interval.setEnabled(self.scheduled_scan.isChecked())
        self.scheduled_scan.toggled.connect(self.schedule_interval.setEnabled)
        form.addRow("Tarama aralığı", self.schedule_interval)
        layout.addLayout(form)

        safety_note = QLabel("Güvenlik: riskli yedekler otomatik seçilmez. Temizlik öncesi onay her zaman zorunludur.")
        safety_note.setWordWrap(True)
        safety_note.setStyleSheet("color:#50e0bd; background:#15332f; border:1px solid #255c52; border-radius:8px; padding:10px")
        layout.addWidget(safety_note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        save = buttons.addButton("Kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate_widget_tree(self)

    def save_preferences(self) -> None:
        self.settings.setValue("workflow/profile", self.profile.currentData())
        self.settings.setValue("cleanup/default_mode", self.mode.currentData())
        self.settings.setValue("scan/large_file_mb", self.threshold.value())
        self.settings.setValue("scan/auto", self.auto_scan.isChecked())
        self.settings.setValue("scan/scheduled", self.scheduled_scan.isChecked())
        self.settings.setValue("scan/interval_minutes", self.schedule_interval.currentData())
        self.settings.setValue("ui/language", self.language.currentData())
        self.settings.sync()


class HistoryDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Temizlik geçmişi")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        heading = QLabel("Son temizlik işlemleri")
        heading.setObjectName("brand")
        heading.setStyleSheet("font-size:19px")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel(
                f"History file: {core.HISTORY_FILE}"
                if i18n.get_language() == "en"
                else f"Geçmiş dosyası: {core.HISTORY_FILE}"
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(2, 8, 8, 8)
        rows.setSpacing(8)
        history = core.load_history(50)
        if not history:
            empty = QLabel("Henüz bir temizlik işlemi kaydedilmedi. Tarama yapmak geçmişe kayıt eklemez.")
            empty.setWordWrap(True)
            empty.setObjectName("muted")
            rows.addWidget(empty)
        for entry in history:
            card = QFrame()
            card.setObjectName("panel")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            mode = entry.get("mode", "delete")
            mode_label = ("Move to Trash" if mode == "trash" else "Permanent delete") if i18n.get_language() == "en" else ("Çöpe taşı" if mode == "trash" else "Kalıcı sil")
            when = QLabel(f"{entry.get('time', 'Unknown date' if i18n.get_language() == 'en' else 'Tarih bilinmiyor')} · {mode_label}")
            when.setStyleSheet("font-weight:700")
            card_layout.addWidget(when)
            total = QLabel(
                f"Total: {core.human_size(entry.get('freed', 0))}"
                if i18n.get_language() == "en"
                else f"Toplam: {core.human_size(entry.get('freed', 0))}"
            )
            total.setObjectName("muted")
            card_layout.addWidget(total)
            for item in entry.get("items", [])[:12]:
                row = QLabel(f"• {item.get('title', 'Öğe')} — {item.get('status', '')} · {core.human_size(item.get('freed', 0))}")
                row.setWordWrap(True)
                row.setObjectName("dim")
                card_layout.addWidget(row)
            more = len(entry.get("items", [])) - 12
            if more > 0:
                card_layout.addWidget(QLabel(f"… ve {more} öğe daha"))
            rows.addWidget(card)
        rows.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        close = QPushButton("Kapat")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        i18n.translate_widget_tree(self)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Temizci — Disk Temizleyici")
        self.setMinimumSize(960, 680)
        self.resize(1240, 850)
        self.settings = QSettings("Temizci", "Temizci")
        i18n.set_language(str(self.settings.value("ui/language", "tr")))
        core.LARGE_FILE_MIN = int(self.settings.value("scan/large_file_mb", 150)) * 1024**2
        self.items: list[core.Item] = []
        self.by_id: dict[str, core.Item] = {}
        self.selected: set[str] = set()
        self.filter_risk = "all"
        self.worker: ScanWorker | CleanWorker | None = None
        self.package_worker: PackageWorker | PackagePreviewWorker | None = None
        self.performance_worker: PerformanceWorker | None = None
        self.package_items: list[dict] = []
        self.packages_loaded = False
        self.performance_loaded = False
        self.has_snapshots = False
        self.scan_after_clean = False
        self._updating_profile = False
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self._scheduled_scan)
        self._make_ui()
        self._apply_schedule()
        self._update_disk()
        if self.settings.value("scan/auto", True, type=bool):
            self._show_status("Sistem taranıyor…")
            self.scan()
        else:
            self._show_status("Taramaya hazır · 'Yeniden tara' ile başlayabilirsin")

    def _make_ui(self) -> None:
        outer = QWidget()
        self.setCentralWidget(outer)
        root = QVBoxLayout(outer)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        brand_col = QVBoxLayout()
        brand = QLabel("Temizci")
        brand.setObjectName("brand")
        self.subtitle = QLabel("Arch tabanlı Linux için güvenli bakım")
        self.subtitle.setObjectName("subtitle")
        brand_col.addWidget(brand)
        brand_col.addWidget(self.subtitle)
        header.addLayout(brand_col)
        header.addStretch()
        history_button = QPushButton("Geçmiş")
        history_button.clicked.connect(self.show_history)
        header.addWidget(history_button)
        support_button = QPushButton("Tanı raporu")
        support_button.setToolTip("Kullanıcı adı, ev dizini, disk kimliği ve özel dosya yollarını içermeyen rapor oluştur")
        support_button.clicked.connect(self.export_support_report)
        header.addWidget(support_button)
        trash_button = QPushButton("Çöp kutusu")
        trash_button.clicked.connect(self.open_trash)
        header.addWidget(trash_button)
        settings_button = QPushButton("Ayarlar")
        settings_button.clicked.connect(self.show_settings)
        header.addWidget(settings_button)
        self.scan_button = QPushButton("⟳  Yeniden tara")
        self.scan_button.clicked.connect(self.scan)
        header.addWidget(self.scan_button)
        root.addLayout(header)

        top = QHBoxLayout()
        top.setSpacing(12)
        disk_panel = QFrame()
        disk_panel.setObjectName("panel")
        disk_layout = QVBoxLayout(disk_panel)
        disk_layout.setContentsMargins(18, 15, 18, 15)
        disk_layout.setSpacing(8)
        disk_title = QLabel("Disk kullanımı")
        disk_title.setObjectName("muted")
        self.disk_line = QLabel("Disk bilgisi okunuyor…")
        self.disk_line.setObjectName("metric")
        self.disk_progress = QProgressBar()
        self.disk_progress.setTextVisible(False)
        self.disk_detail = QLabel("")
        self.disk_detail.setObjectName("subtitle")
        disk_layout.addWidget(disk_title)
        disk_layout.addWidget(self.disk_line)
        disk_layout.addWidget(self.disk_progress)
        disk_layout.addWidget(self.disk_detail)
        top.addWidget(disk_panel, 1)

        self.metrics: dict[str, QLabel] = {}
        metric_layout = QHBoxLayout()
        metric_layout.setSpacing(10)
        for key, title in (
            ("selected", "SEÇİLİ TEMİZLİK"),
            ("safe", "GÜVENLİ KAZANÇ"),
            ("found", "TOPLAM BULUNAN"),
            ("trash", "ÇÖP KUTUSU"),
        ):
            panel = QFrame()
            panel.setObjectName("panel")
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(14, 13, 14, 13)
            label = QLabel(title)
            label.setObjectName("dim")
            value = QLabel("0 B")
            value.setObjectName("metricAccent" if key == "selected" else "metric")
            note = QLabel(" ")
            note.setObjectName("dim")
            self.metrics[key] = value
            self.metrics[key + "_note"] = note
            layout.addWidget(label)
            layout.addWidget(value)
            layout.addWidget(note)
            metric_layout.addWidget(panel, 1)
        top.addLayout(metric_layout, 2)
        root.addLayout(top)

        self.pages = QTabWidget()
        self.clean_page = QWidget()
        clean_layout = QVBoxLayout(self.clean_page)
        clean_layout.setContentsMargins(12, 10, 12, 10)
        clean_layout.setSpacing(9)
        self.pages.addTab(self.clean_page, "Temizlik")
        self.packages_page = QWidget()
        self._build_packages_page()
        self.pages.addTab(self.packages_page, "Uygulamalar ve paketler")
        self.performance_page = QWidget()
        self._build_performance_page()
        self.pages.addTab(self.performance_page, "Hız ve başlangıç")
        self.pages.currentChanged.connect(self._page_changed)
        root.addWidget(self.pages, 1)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara: Zen, önbellek, büyük dosya…")
        self.search.textChanged.connect(self.render_items)
        toolbar.addWidget(self.search, 1)
        self.risk_combo = QComboBox()
        self.risk_combo.addItem("Tüm riskler", "all")
        self.risk_combo.addItem("Güvenli", "safe")
        self.risk_combo.addItem("Dikkat", "caution")
        self.risk_combo.addItem("Riskli", "risky")
        self.risk_combo.currentIndexChanged.connect(self._filter_changed)
        toolbar.addWidget(self.risk_combo)
        self.workflow_combo = QComboBox()
        self.workflow_combo.addItem("Önerilen", "recommended")
        self.workflow_combo.addItem("Derin inceleme", "deep")
        self.workflow_combo.addItem("Manuel seçim", "manual")
        profile = str(self.settings.value("workflow/profile", "recommended"))
        self.workflow_combo.setCurrentIndex(max(0, self.workflow_combo.findData(profile)))
        self.workflow_combo.setToolTip("Önerilen: güvenli öğeler. Derin: güvenli ve dikkat öğeleri. Riskliler otomatik seçilmez.")
        self.workflow_combo.currentIndexChanged.connect(self._workflow_changed)
        toolbar.addWidget(self.workflow_combo)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("En büyük önce", "size")
        self.sort_combo.addItem("Ada göre", "name")
        self.sort_combo.currentIndexChanged.connect(self.render_items)
        toolbar.addWidget(self.sort_combo)
        self.only_selected = QCheckBox("Sadece seçili")
        self.only_selected.toggled.connect(self.render_items)
        toolbar.addWidget(self.only_selected)
        self.select_safe_button = QPushButton("Önerilenleri seç")
        self.select_safe_button.clicked.connect(self.select_safe)
        toolbar.addWidget(self.select_safe_button)
        clean_layout.addLayout(toolbar)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color:#ffd178; background:#342b19; border:1px solid #665128; border-radius:8px; padding:9px")
        self.warning.hide()
        clean_layout.addWidget(self.warning)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(1, 2, 8, 2)
        self.list_layout.setSpacing(7)
        self.list_layout.addStretch()
        self.list_scroll.setWidget(self.list_widget)
        clean_layout.addWidget(self.list_scroll, 1)

        footer = QHBoxLayout()
        self.selection_label = QLabel("0 öğe seçildi · 0 B")
        self.selection_label.setObjectName("muted")
        footer.addWidget(self.selection_label)
        footer.addStretch()
        self.clear_button = QPushButton("Seçimi temizle")
        self.clear_button.clicked.connect(self.clear_selection)
        footer.addWidget(self.clear_button)
        self.clean_button = QPushButton("Seçilenleri temizle")
        self.clean_button.setObjectName("danger")
        self.clean_button.setEnabled(False)
        self.clean_button.clicked.connect(self.confirm_clean)
        footer.addWidget(self.clean_button)
        clean_layout.addLayout(footer)
        i18n.translate_widget_tree(self)

    def _build_packages_page(self) -> None:
        layout = QVBoxLayout(self.packages_page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(9)

        intro = QLabel(
            "Açıkça kurduğun uygulamalar ve artık bağımlılıklar listelenir. "
            "'Kurulu ama kullanılmıyor' tahmin etmiyoruz; hiçbir paket varsayılan seçili değildir."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        controls = QHBoxLayout()
        self.package_search = QLineEdit()
        self.package_search.setPlaceholderText("Paket adı veya açıklama ara…")
        self.package_search.textChanged.connect(self._filter_packages)
        controls.addWidget(self.package_search, 1)
        self.package_filter = QComboBox()
        self.package_filter.addItem("Tüm paketler", "all")
        self.package_filter.addItem("Artık bağımlılıklar", "orphans")
        self.package_filter.addItem("Açıkça kurduklarım", "explicit")
        self.package_filter.currentIndexChanged.connect(self._filter_packages)
        controls.addWidget(self.package_filter)
        self.package_refresh_button = QPushButton("Paketleri tara")
        self.package_refresh_button.clicked.connect(self.load_packages)
        controls.addWidget(self.package_refresh_button)
        layout.addLayout(controls)

        self.package_tree = QTreeWidget()
        self.package_tree.setColumnCount(5)
        self.package_tree.setHeaderLabels(["Seç", "Paket", "Durum", "Kurulu boyut", "Sürüm"])
        self.package_tree.setRootIsDecorated(False)
        self.package_tree.setAlternatingRowColors(True)
        self.package_tree.setUniformRowHeights(True)
        self.package_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.package_tree.setColumnWidth(0, 40)
        self.package_tree.setColumnWidth(1, 300)
        self.package_tree.setColumnWidth(2, 175)
        self.package_tree.setColumnWidth(3, 115)
        self.package_tree.currentItemChanged.connect(self._package_details_changed)
        self.package_tree.itemChanged.connect(self._package_checked)
        layout.addWidget(self.package_tree, 1)

        self.package_detail = QPlainTextEdit()
        self.package_detail.setReadOnly(True)
        self.package_detail.setMaximumHeight(86)
        self.package_detail.setPlaceholderText("Pakete tıklayarak açıklama ve kurulum bilgisini gör.")
        layout.addWidget(self.package_detail)

        actions = QHBoxLayout()
        self.package_count_label = QLabel("Paket listesi henüz yüklenmedi")
        self.package_count_label.setObjectName("muted")
        actions.addWidget(self.package_count_label)
        actions.addStretch()
        self.select_orphans_button = QPushButton("Artık bağımlılıkları işaretle")
        self.select_orphans_button.clicked.connect(self.select_orphans)
        actions.addWidget(self.select_orphans_button)
        clear = QPushButton("Seçimi temizle")
        clear.clicked.connect(self.clear_package_selection)
        actions.addWidget(clear)
        self.package_preview_button = QPushButton("Kaldırma planını önizle…")
        self.package_preview_button.setObjectName("danger")
        self.package_preview_button.clicked.connect(self.preview_package_removal)
        self.package_preview_button.setEnabled(False)
        actions.addWidget(self.package_preview_button)
        layout.addLayout(actions)

    def _build_performance_page(self) -> None:
        layout = QVBoxLayout(self.performance_page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        intro = QHBoxLayout()
        explanation = QLabel(
            "Ölçümler salt okunurdur. Başlangıç uygulamalarını geçici olarak devre dışı bırakabilirsin; "
            "sistem servisleri yalnızca raporlanır, kendiliğimizden kapatmayız."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        intro.addWidget(explanation, 1)
        self.performance_refresh_button = QPushButton("Ölçümleri yenile")
        self.performance_refresh_button.clicked.connect(self.refresh_performance)
        intro.addWidget(self.performance_refresh_button)
        layout.addLayout(intro)

        self.performance_summary = QLabel("Performans ölçümü için 'Yenile'ye bas.")
        self.performance_summary.setObjectName("muted")
        self.performance_summary.setWordWrap(True)
        self.performance_summary.setStyleSheet("background:#111b22; border:1px solid #26353d; border-radius:9px; padding:10px")
        layout.addWidget(self.performance_summary)

        self.performance_recommendations = QPlainTextEdit()
        self.performance_recommendations.setReadOnly(True)
        self.performance_recommendations.setMaximumHeight(115)
        self.performance_recommendations.setPlaceholderText("Ölçüm tamamlanınca kişiye özel, salt okunur öneriler burada görünür.")
        layout.addWidget(self.performance_recommendations)

        self.performance_actions = QHBoxLayout()
        self.power_profile_button = QPushButton("Performans güç profiline geç…")
        self.power_profile_button.clicked.connect(self.set_performance_profile)
        self.trim_button = QPushButton("SSD TRIM zamanlayıcısını etkinleştir…")
        self.trim_button.clicked.connect(self.enable_trim)
        self.performance_actions.addWidget(self.power_profile_button)
        self.performance_actions.addWidget(self.trim_button)
        self.performance_actions.addStretch()
        layout.addLayout(self.performance_actions)

        lower = QHBoxLayout()
        boot_frame = QFrame()
        boot_frame.setObjectName("panel")
        boot_layout = QVBoxLayout(boot_frame)
        boot_layout.setContentsMargins(12, 10, 12, 10)
        boot_title = QLabel("Açılışta en uzun süren birimler")
        boot_title.setStyleSheet("font-weight:700")
        boot_layout.addWidget(boot_title)
        self.boot_tree = QTreeWidget()
        self.boot_tree.setColumnCount(2)
        self.boot_tree.setHeaderLabels(["Süre", "Systemd birimi"])
        self.boot_tree.setRootIsDecorated(False)
        self.boot_tree.setAlternatingRowColors(True)
        boot_layout.addWidget(self.boot_tree, 1)
        lower.addWidget(boot_frame, 1)

        units_frame = QFrame()
        units_frame.setObjectName("panel")
        units_layout = QVBoxLayout(units_frame)
        units_layout.setContentsMargins(12, 10, 12, 10)
        unit_title = QLabel("Etkin systemd servisleri · bilgi amaçlı")
        unit_title.setStyleSheet("font-weight:700")
        units_layout.addWidget(unit_title)
        self.units_tree = QTreeWidget()
        self.units_tree.setColumnCount(1)
        self.units_tree.setHeaderLabels(["Açılışta etkin servis"])
        self.units_tree.setRootIsDecorated(False)
        self.units_tree.setAlternatingRowColors(True)
        units_layout.addWidget(self.units_tree, 1)
        lower.addWidget(units_frame, 1)
        layout.addLayout(lower, 1)

        startup_frame = QFrame()
        startup_frame.setObjectName("panel")
        startup_layout = QVBoxLayout(startup_frame)
        startup_layout.setContentsMargins(12, 10, 12, 10)
        startup_heading = QHBoxLayout()
        startup_title = QLabel("Kullanıcı başlangıç uygulamaları")
        startup_title.setStyleSheet("font-weight:700")
        startup_heading.addWidget(startup_title)
        startup_heading.addStretch()
        self.autostart_hint = QLabel("Kapatmak yalnızca sonraki oturum açılışını etkiler; geri alınabilir.")
        self.autostart_hint.setObjectName("dim")
        startup_heading.addWidget(self.autostart_hint)
        startup_layout.addLayout(startup_heading)

        lists = QHBoxLayout()
        active_col = QVBoxLayout()
        active_col.addWidget(QLabel("Etkin · seçip devre dışı bırak"))
        self.autostart_tree = QTreeWidget()
        self.autostart_tree.setColumnCount(2)
        self.autostart_tree.setHeaderLabels(["Uygulama", "Başlatma komutu"])
        self.autostart_tree.setRootIsDecorated(False)
        self.autostart_tree.setMaximumHeight(150)
        active_col.addWidget(self.autostart_tree)
        lists.addLayout(active_col, 1)

        disabled_col = QVBoxLayout()
        disabled_col.addWidget(QLabel("Devre dışı · geri yüklenebilir"))
        self.disabled_autostart_tree = QTreeWidget()
        self.disabled_autostart_tree.setColumnCount(1)
        self.disabled_autostart_tree.setHeaderLabels(["Uygulama"])
        self.disabled_autostart_tree.setRootIsDecorated(False)
        self.disabled_autostart_tree.setMaximumHeight(150)
        disabled_col.addWidget(self.disabled_autostart_tree)
        lists.addLayout(disabled_col, 1)
        startup_layout.addLayout(lists)

        startup_buttons = QHBoxLayout()
        startup_buttons.addStretch()
        self.disable_autostart_button = QPushButton("Seçileni devre dışı bırak")
        self.disable_autostart_button.clicked.connect(self.disable_autostart)
        startup_buttons.addWidget(self.disable_autostart_button)
        self.restore_autostart_button = QPushButton("Seçileni geri yükle")
        self.restore_autostart_button.clicked.connect(self.restore_autostart)
        startup_buttons.addWidget(self.restore_autostart_button)
        startup_layout.addLayout(startup_buttons)
        layout.addWidget(startup_frame)
        i18n.translate_widget_tree(self)

    def _page_changed(self, index: int) -> None:
        if index == 1 and not self.packages_loaded:
            self.load_packages()
        elif index == 2 and not self.performance_loaded:
            self.refresh_performance()

    def load_packages(self) -> None:
        if self.package_worker and self.package_worker.isRunning():
            return
        self.package_refresh_button.setEnabled(False)
        self.package_count_label.setText("Pacman paket bilgileri salt okunur şekilde alınıyor…")
        worker = PackageWorker(self)
        worker.finished_packages.connect(self._packages_loaded)
        worker.failed.connect(self._packages_failed)
        worker.finished.connect(self._package_worker_done)
        self.package_worker = worker
        worker.start()

    def _package_worker_done(self) -> None:
        self.package_refresh_button.setEnabled(True)
        if self.package_worker:
            self.package_worker.deleteLater()
            self.package_worker = None

    def _packages_loaded(self, packages: list[dict]) -> None:
        self.package_items = packages
        self.packages_loaded = True
        self._render_packages()
        self._show_status(f"Paket envanteri hazır · {len(packages)} paket", 7000)

    def _packages_failed(self, message: str) -> None:
        self.package_count_label.setText("Paket envanteri alınamadı")
        _message_box("warning", self, "Pacman sorgulanamadı", message)

    def _render_packages(self) -> None:
        self.package_tree.blockSignals(True)
        self.package_tree.clear()
        for package in self.package_items:
            item = QTreeWidgetItem()
            item.setText(1, package["name"])
            item.setText(2, "Korumalı" if package["protected"] else "Artık bağımlılık" if package["orphan"] else "Açıkça kurulmuş")
            item.setText(3, core.human_size(package["size"]))
            item.setText(4, package["version"])
            item.setToolTip(1, package["description"])
            item.setData(0, Qt.ItemDataRole.UserRole, package)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if package["protected"]:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsUserCheckable)
                item.setToolTip(1, "Temel işletim sistemi paketi; Temizci kaldırma listesinde kilitler.")
            self.package_tree.addTopLevelItem(item)
        self.package_tree.blockSignals(False)
        self._filter_packages()
        i18n.translate_widget_tree(self)

    def _filter_packages(self, *_args) -> None:
        if not hasattr(self, "package_tree"):
            return
        query = self.package_search.text().strip().casefold()
        mode = self.package_filter.currentData()
        for index in range(self.package_tree.topLevelItemCount()):
            row = self.package_tree.topLevelItem(index)
            package = row.data(0, Qt.ItemDataRole.UserRole)
            is_visible = (
                (mode == "all" or mode == "orphans" and package["orphan"] or mode == "explicit" and package["explicit"])
                and (not query or query in f"{package['name']} {package['description']} {package['version']}".casefold())
            )
            row.setHidden(not is_visible)
        checked = len(self._selected_package_names())
        visible = sum(not self.package_tree.topLevelItem(i).isHidden() for i in range(self.package_tree.topLevelItemCount()))
        self.package_count_label.setText(
            i18n.tr(f"{checked} seçili · {visible} / {len(self.package_items)} paket gösteriliyor")
        )
        self.package_preview_button.setEnabled(checked > 0 and not (self.package_worker and self.package_worker.isRunning()))

    def _package_checked(self, _item: QTreeWidgetItem, _column: int) -> None:
        self._filter_packages()

    def _package_details_changed(self, item: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if not item:
            self.package_detail.clear()
            return
        package = item.data(0, Qt.ItemDataRole.UserRole)
        if not package:
            return
        reason = (
            "Explicitly installed by the user" if package["explicit"] else "Installed as a dependency"
        ) if i18n.get_language() == "en" else (
            "Kullanıcı tarafından açıkça kurulmuş" if package["explicit"] else "Bağımlılık olarak kurulmuş"
        )
        if package["orphan"]:
            reason = (
                "Orphan dependency — no installed package currently requires it"
                if i18n.get_language() == "en"
                else "Artık bağımlılık — şu anda başka bir paketin gereksinimi değil"
            )
        required_by = package["required_by"]
        self.package_detail.setPlainText(
            (
                f"{package['description']}\n"
                f"Install reason: {reason} · Repository: {package['source'] or 'unknown'} · "
                f"Required by: {required_by} · Install date: {package['install_date'] or 'unknown'}"
            )
            if i18n.get_language() == "en"
            else (
                f"{package['description']}\n"
                f"Kurulum: {reason} · Kaynak: {package['source'] or 'bilinmiyor'} · "
                f"Gerekli olduğu paketler: {required_by} · Kurulum tarihi: {package['install_date'] or 'bilinmiyor'}"
            )
        )

    def _selected_package_names(self) -> list[str]:
        names = []
        for index in range(self.package_tree.topLevelItemCount()):
            row = self.package_tree.topLevelItem(index)
            if row.checkState(0) == Qt.CheckState.Checked:
                package = row.data(0, Qt.ItemDataRole.UserRole)
                if package and not package["protected"]:
                    names.append(package["name"])
        return names

    def select_orphans(self) -> None:
        self.package_tree.blockSignals(True)
        for index in range(self.package_tree.topLevelItemCount()):
            row = self.package_tree.topLevelItem(index)
            package = row.data(0, Qt.ItemDataRole.UserRole)
            if package and package["orphan"] and not package["protected"]:
                row.setCheckState(0, Qt.CheckState.Checked)
        self.package_tree.blockSignals(False)
        self._filter_packages()

    def clear_package_selection(self) -> None:
        self.package_tree.blockSignals(True)
        for index in range(self.package_tree.topLevelItemCount()):
            self.package_tree.topLevelItem(index).setCheckState(0, Qt.CheckState.Unchecked)
        self.package_tree.blockSignals(False)
        self._filter_packages()

    def preview_package_removal(self) -> None:
        names = self._selected_package_names()
        if not names:
            return
        if len(names) > 120:
            _message_box("warning", self, "Çok fazla paket", "Önizleme başına en fazla 120 paket seçebilirsin.")
            return
        worker = PackagePreviewWorker(names)
        worker.finished_plan.connect(self._package_plan_ready)
        worker.failed.connect(self._package_plan_failed)
        worker.finished.connect(self._package_worker_done)
        self.package_worker = worker
        self.package_preview_button.setEnabled(False)
        self.package_count_label.setText("Pacman'ın salt okunur işlem planı hazırlanıyor…")
        self._show_status("Paket kaldırma planı hesaplanıyor; sistem değiştirilmiyor")
        worker.start()

    def _package_plan_ready(self, plan: dict) -> None:
        dialog = PackagePreviewDialog(plan, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._open_command_terminal(plan["command"])
            self._show_status("Pacman terminalde açıldı; son işlem onayı ve sudo parolası terminalde.", 9000)
        self._filter_packages()

    def _package_plan_failed(self, message: str) -> None:
        self._filter_packages()
        _message_box("warning", self, "İşlem planı oluşturulamadı", message)

    def refresh_performance(self) -> None:
        if self.performance_worker and self.performance_worker.isRunning():
            return
        self.performance_refresh_button.setEnabled(False)
        self.performance_summary.setText("RAM, açılış, disk bakımı ve kullanıcı başlangıç uygulamaları ölçülüyor…")
        worker = PerformanceWorker(self)
        worker.finished_report.connect(self._performance_ready)
        worker.failed.connect(self._performance_failed)
        worker.finished.connect(self._performance_worker_done)
        self.performance_worker = worker
        worker.start()

    def _performance_worker_done(self) -> None:
        self.performance_refresh_button.setEnabled(True)
        if self.performance_worker:
            self.performance_worker.deleteLater()
            self.performance_worker = None

    def _performance_failed(self, message: str) -> None:
        self.performance_summary.setText("Performans ölçümü başarısız")
        _message_box("warning", self, "Ölçüm yapılamadı", message)

    def _performance_ready(self, report: dict) -> None:
        self.performance_loaded = True
        memory_pct = report["memory_percent"]
        disk = core.disk_info()
        swap_pct = round(report["swap_used"] * 100 / report["swap_total"]) if report["swap_total"] else 0
        load = " · ".join(f"{value:.2f}" for value in report["load"]) or "bilinmiyor"
        if i18n.get_language() == "en":
            summary = (
                f"Memory: {core.human_size(report['memory_used'])} / {core.human_size(report['memory_total'])} ({memory_pct:g}%)   ·   "
                f"Swap: {core.human_size(report['swap_used'])} / {core.human_size(report['swap_total'])} ({swap_pct}%)   ·   "
                f"Load average: {load}   ·   Disk: {disk['percent']}% used\n"
                f"Boot: {report['boot_time'] or 'not available'}   ·   "
                f"Power profile: {report['power_profile']}   ·   CPU governor: {report['cpu_governor']}   ·   "
                f"fstrim.timer: {report['trim_enabled']} ({report['trim_active']})"
            )
        else:
            summary = (
                f"RAM: {core.human_size(report['memory_used'])} / {core.human_size(report['memory_total'])} (%{memory_pct:g})   ·   "
                f"Swap: {core.human_size(report['swap_used'])} / {core.human_size(report['swap_total'])} (%{swap_pct})   ·   "
                f"Yük ortalaması: {load}   ·   Disk: %{disk['percent']} dolu\n"
                f"Açılış: {report['boot_time'] or 'ölçülemedi'}   ·   "
                f"Güç profili: {report['power_profile']}   ·   CPU governor: {report['cpu_governor']}   ·   "
                f"fstrim.timer: {report['trim_enabled']} ({report['trim_active']})"
            )
        self.performance_summary.setText(summary)

        recommendations = []
        english = i18n.get_language() == "en"
        if disk["percent"] >= 90:
            recommendations.append("• Disk usage is above 90%; reviewing large files and caches is a good first step." if english else "• Disk kullanımı %90 üzerinde; büyük dosyalar ve önbelleklerde yer açmak ilk adımdır.")
        elif disk["percent"] >= 80:
            recommendations.append("• Disk usage is high; removing unneeded files can leave room for updates." if english else "• Disk kullanımı yüksek; gereksiz dosyaları temizlemek güncelleme alanı bırakır.")
        if memory_pct >= 90:
            recommendations.append("• Memory pressure is high. Review startup apps and close applications you do not need." if english else "• RAM baskısı yüksek. Başlangıçta açılan uygulamaları azaltmayı ve büyük uygulamaları kapatmayı incele.")
        elif report["swap_total"] and swap_pct >= 60:
            recommendations.append("• Swap usage is high. This is not automatically a problem; consider it alongside memory pressure and active workloads." if english else "• Swap kullanımı yüksek. Bu tek başına sorun değildir; RAM doluluğu ve ağır uygulamalarla birlikte değerlendir.")
        if report["root_is_ssd"] and report["trim_supported"] and report["trim_enabled"] != "enabled":
            recommendations.append("• The system disk supports SSD/NVMe discard, but the fstrim timer is disabled. You can enable it below." if english else "• Sistem SSD/NVMe üzerinde ve discard destekli; fstrim zamanlayıcısı etkin değil. İstersen aşağıdaki düğmeden etkinleştir.")
        if report["power_profile"] != "performance" and shutil.which("powerprofilesctl"):
            recommendations.append("• The current power profile is not performance. Switching may improve responsiveness but can increase heat, fan noise, and battery use." if english else "• Güç profili performans değil. İstersen daha yüksek tepki için performans profiline geç; pil tüketimi ve fan sesi artabilir.")
        if not recommendations:
            recommendations.append("• No critical memory/disk pressure or missing SSD TRIM setting was detected. Review boot and service diagnostics below." if english else "• Kritik RAM/disk baskısı veya eksik SSD TRIM ayarı görünmüyor. Açılış ve servis ölçümlerini aşağıdan incele.")
        recommendations.append("• System services are never disabled automatically; doing so could affect networking, Bluetooth, power management, or desktop features." if english else "• Sistem servislerini otomatik kapatmıyoruz: ağ, Bluetooth, güç yönetimi veya masaüstü işlevleri etkilenebilir.")
        self.performance_recommendations.setPlainText("\n".join(recommendations))

        self.power_profile_button.setEnabled(report["power_profile"] != "performance" and bool(shutil.which("powerprofilesctl")))
        self.trim_button.setEnabled(
            report["root_is_ssd"]
            and report["trim_supported"]
            and report["trim_enabled"] != "enabled"
            and bool(shutil.which("fstrim"))
        )

        self.boot_tree.clear()
        for line in report["boot_blame"]:
            parts = line.split(None, 1)
            row = QTreeWidgetItem([parts[0] if parts else "", parts[1] if len(parts) > 1 else line])
            self.boot_tree.addTopLevelItem(row)
        if not report["boot_blame"]:
            self.boot_tree.addTopLevelItem(QTreeWidgetItem(["—", "systemd-analyze verisi yok"]))
        self.units_tree.clear()
        for unit in report["enabled_units"]:
            self.units_tree.addTopLevelItem(QTreeWidgetItem([unit]))
        self._render_autostart(report.get("autostart", []), core.list_disabled_autostart())
        self._show_status("Performans ölçümü tamamlandı · hiçbir ayar değiştirilmedi", 7000)

    def _render_autostart(self, entries: list[dict], disabled: list[dict]) -> None:
        self.autostart_tree.clear()
        for entry in entries:
            item = QTreeWidgetItem([entry["name"], entry["exec"]])
            item.setData(0, Qt.ItemDataRole.UserRole, entry["filename"])
            item.setToolTip(0, entry["comment"])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            self.autostart_tree.addTopLevelItem(item)
        self.disabled_autostart_tree.clear()
        for entry in disabled:
            item = QTreeWidgetItem([entry["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, entry["filename"])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            self.disabled_autostart_tree.addTopLevelItem(item)
        self.disable_autostart_button.setEnabled(bool(entries))
        self.restore_autostart_button.setEnabled(bool(disabled))
        i18n.translate_widget_tree(self)

    def _checked_startup_files(self, tree: QTreeWidget) -> list[str]:
        return [
            str(tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole))
            for index in range(tree.topLevelItemCount())
            if tree.topLevelItem(index).checkState(0) == Qt.CheckState.Checked
        ]

    def disable_autostart(self) -> None:
        filenames = self._checked_startup_files(self.autostart_tree)
        if not filenames:
            _message_box("information", self, "Öğe seçilmedi", "Devre dışı bırakmak istediğin kullanıcı başlangıç uygulamalarını işaretle.")
            return
        names = [
            self.autostart_tree.topLevelItem(index).text(0)
            for index in range(self.autostart_tree.topLevelItemCount())
            if self.autostart_tree.topLevelItem(index).checkState(0) == Qt.CheckState.Checked
        ]
        answer = _message_box(
            "question",
            self,
            "Başlangıç uygulamalarını devre dışı bırak",
            (
                "These apps will not start automatically at your next login. Their files will not be deleted; "
                "you can restore them in Temizci.\n\n"
                + "\n".join(f"• {name}" for name in names)
            ) if i18n.get_language() == "en" else (
                "Bu uygulamalar sonraki oturum açılışında otomatik başlamayacak. Dosyalar silinmez; Temizci'den geri yüklenebilir.\n\n"
                + "\n".join(f"• {name}" for name in names)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        results = core.disable_user_autostart(filenames)
        errors = [item["error"] for item in results if not item["ok"]]
        changed = len(results) - len(errors)
        self._show_status(
            f"{changed} startup app{'s' if changed != 1 else ''} disabled until your next login"
            if i18n.get_language() == "en"
            else f"{changed} başlangıç uygulaması sonraki oturum için devre dışı",
            8000,
        )
        if errors:
            _message_box("warning", self, "Bazı öğeler değiştirilemedi", "\n".join(errors))
        self.refresh_performance()

    def restore_autostart(self) -> None:
        filenames = self._checked_startup_files(self.disabled_autostart_tree)
        if not filenames:
            _message_box("information", self, "Öğe seçilmedi", "Geri yüklemek istediğin başlangıç uygulamalarını işaretle.")
            return
        answer = _message_box(
            "question",
            self,
            "Başlangıç uygulamalarını geri yükle",
            "Selected apps will start automatically again at your next login. Continue?" if i18n.get_language() == "en" else "Seçilen uygulamalar sonraki oturum açılışında tekrar otomatik başlayacak. Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        results = core.restore_user_autostart(filenames)
        errors = [item["error"] for item in results if not item["ok"]]
        restored = len(results) - len(errors)
        self._show_status(
            f"{restored} startup app{'s' if restored != 1 else ''} restored"
            if i18n.get_language() == "en"
            else f"{restored} başlangıç uygulaması geri yüklendi",
            8000,
        )
        if errors:
            _message_box("warning", self, "Bazı öğeler geri yüklenemedi", "\n".join(errors))
        self.refresh_performance()

    def set_performance_profile(self) -> None:
        answer = _message_box(
            "question",
            self,
            "Performans profili",
            "This profile may improve CPU responsiveness but can increase fan noise, temperature, and battery use. "
            "The command will only be opened in a terminal. Continue?" if i18n.get_language() == "en" else "Bu profil işlemci tepkisini artırabilir; fan sesi, sıcaklık ve pil tüketimi de artabilir. "
            "Sadece terminalde komut açılacak; devam etmek istiyor musun?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._open_command_terminal("powerprofilesctl set performance")

    def enable_trim(self) -> None:
        answer = _message_box(
            "question",
            self,
            "SSD TRIM zamanlayıcısı",
            "This enables the systemd fstrim timer for supported SSD/NVMe drives. The command will request your sudo password in a terminal. Continue?" if i18n.get_language() == "en" else "Bu, destekleyen SSD/NVMe diskler için systemd fstrim zamanlayıcısını etkinleştirir. "
            "Komut sudo parolanı terminalde ister. Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._open_command_terminal("sudo systemctl enable --now fstrim.timer")


    def scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        core.LARGE_FILE_MIN = int(self.settings.value("scan/large_file_mb", 150)) * 1024**2
        self.scan_button.setEnabled(False)
        self.clean_button.setEnabled(False)
        self._show_status("Sistem taranıyor…")
        worker = ScanWorker(self)
        worker.progress.connect(self._scan_progress)
        worker.finished_items.connect(self._scan_finished)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(self._worker_done)
        self.worker = worker
        worker.start()

    def _scan_progress(self, done: int, total: int, label: str) -> None:
        self._show_status(f"Taranıyor: {i18n.tr(label)} ({done}/{total})")

    def _scan_finished(self, items: list[core.Item]) -> None:
        self.items = items
        self.by_id = {item.id: item for item in items}
        self._apply_profile()
        self._update_disk()
        self.render_items()
        self._show_status(f"Tarama tamamlandı · {len(items)} öğe bulundu", 7000)

    def _scan_failed(self, message: str) -> None:
        self._show_status(f"Tarama hatası: {message}", 10000)
        _message_box("critical", self, "Tarama başarısız", message)

    def _worker_done(self) -> None:
        self.scan_button.setEnabled(True)
        self._update_metrics()
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.scan_after_clean:
            self.scan_after_clean = False
            self.scan()

    def export_support_report(self) -> None:
        privacy_tr = (
            "Rapor toplulukla paylaşılmaya uygun olacak şekilde hazırlanır. İçerdiği bilgiler:\n"
            "• Dağıtım/sürüm, çekirdek sürümü, mimari ve masaüstü ailesi\n"
            "• Disk ve bellek kapasitesi/kullanım oranı, açılış özeti, güç/TRIM durumu\n"
            "• İlgili sistem araçlarının kurulu olup olmadığı\n\n"
            "Kullanıcı adı, bilgisayar adı, ev dizini, disk kimliği, dosya yolları, paket adları, "
            "systemd servis adları ve başlangıç komutları rapora alınmaz. Raporu kaydetmeden önce "
            "oluşturulan JSON'u inceleyebilirsin. Devam edilsin mi?"
        )
        privacy_en = (
            "This report is prepared for community troubleshooting and includes:\n"
            "• Distribution/version, kernel version, architecture, and desktop family\n"
            "• Disk and memory capacity/usage, boot summary, power/TRIM status\n"
            "• Whether relevant system tools are available\n\n"
            "Usernames, computer names, home directories, disk IDs, file paths, package names, "
            "systemd service names, and startup commands are excluded. Review the generated JSON "
            "before saving. Continue?"
        )
        answer = _message_box(
            "question",
            self,
            "Gizliliği koruyan tanı raporu",
            privacy_en if i18n.get_language() == "en" else privacy_tr,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        report = core.community_support_report()
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle(i18n.tr("Paylaşılabilir tanı raporu · önizleme"))
        preview_dialog.resize(760, 620)
        preview_layout = QVBoxLayout(preview_dialog)
        preview_text = QLabel(
            "Review the report before saving. It contains read-only diagnostics and does not change system settings."
            if i18n.get_language() == "en"
            else "Kaydetmeden önce içeriği incele. Rapor salt okunur ölçümler içerir; hiçbir sistem ayarını değiştirmez."
        )
        preview_text.setWordWrap(True)
        preview_layout.addWidget(preview_text)
        preview_json = QPlainTextEdit()
        preview_json.setReadOnly(True)
        preview_json.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        preview_layout.addWidget(preview_json, 1)
        preview_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        save_preview = preview_buttons.addButton(
            "Reviewed · save report…" if i18n.get_language() == "en" else "İnceledim · dosyaya kaydet…",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        save_preview.setObjectName("primary")
        preview_buttons.accepted.connect(preview_dialog.accept)
        preview_buttons.rejected.connect(preview_dialog.reject)
        preview_layout.addWidget(preview_buttons)
        if preview_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save support report" if i18n.get_language() == "en" else "Tanı raporunu kaydet",
            str(Path.home() / "temizci-tani-raporu.json"),
            "JSON report (*.json)" if i18n.get_language() == "en" else "JSON raporu (*.json)",
        )
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"
        try:
            destination = core.write_community_support_report(filename, report)
        except (OSError, ValueError) as exc:
            _message_box("warning", self, "Rapor kaydedilemedi", str(exc))
            return
        _message_box(
            "information",
            self,
            "Rapor hazır",
            (
                f"Privacy-conscious support report saved to:\n{destination}\n\n"
                "Open and review the report before sharing it with the community."
            )
            if i18n.get_language() == "en"
            else f"Gizliliği koruyan tanı raporu kaydedildi:\n{destination}\n\n"
            "Toplulukla paylaşmadan önce dosyayı açıp içeriğini yine de gözden geçir.",
        )

    def _update_disk(self) -> None:
        disk = core.disk_info()
        percent = int(disk.get("percent", 0))
        self.disk_line.setText(i18n.tr(f"{percent}% dolu"))
        self.disk_progress.setValue(percent)
        self.disk_detail.setText(
            f"{core.human_size(disk['used'])} / {core.human_size(disk['total'])} "
            + ("used · " if i18n.get_language() == "en" else "kullanılıyor · ")
            + f"{core.human_size(disk['free'])} "
            + ("free" if i18n.get_language() == "en" else "boş")
        )
        report = core.system_report()
        self.has_snapshots = bool(report.get("snapshots"))
        self.subtitle.setText(
            f"{report['os']} · "
            + (f"kernel {report['kernel']} · local app only" if i18n.get_language() == "en" else f"çekirdek {report['kernel']} · yalnızca yerel uygulama")
        )

    def _update_metrics(self) -> None:
        chosen = [self.by_id[item_id] for item_id in self.selected if item_id in self.by_id]
        selected_size = sum(item.size for item in chosen)
        safe_size = sum(item.size for item in self.items if item.risk == "safe" and item.action == "delete")
        found_size = core.reclaimable_total(self.items)
        trash_item = next((item for item in self.items if item.rule_id == "trash"), None)
        self.metrics["selected"].setText(core.human_size(selected_size))
        if chosen:
            selection_note = i18n.tr(f"{len(chosen)} öğe seçildi")
        elif self.items:
            selection_note = i18n.tr("Güvenli seçim yok · Dikkat öğelerini incele")
        else:
            selection_note = i18n.tr("Tarama bekleniyor")
        self.metrics["selected_note"].setText(selection_note)
        self.metrics["safe"].setText(core.human_size(safe_size))
        self.metrics["safe_note"].setText(i18n.tr("güvenli temizlenebilir"))
        self.metrics["found"].setText(core.human_size(found_size))
        self.metrics["found_note"].setText(i18n.tr(f"{len(self.items)} öğe bulundu"))
        self.metrics["trash"].setText(core.human_size(trash_item.size if trash_item else 0))
        self.metrics["trash_note"].setText(i18n.tr("çöp kutusundaki alan"))
        self.selection_label.setText(i18n.tr(f"{len(chosen)} öğe seçildi · {core.human_size(selected_size)}"))
        self.clean_button.setEnabled(bool(chosen) and not (self.worker and self.worker.isRunning()))
        self.clear_button.setEnabled(bool(chosen))
        recommended_count = sum(
            item.risk == "safe" and item.action == "delete" and not item.meta.get("running")
            for item in self.items
        )
        self.select_safe_button.setEnabled(recommended_count > 0)

        running = [
            item.meta.get("app") or item.meta.get("cache_name") or item.title
            for item in self.items
            if item.meta.get("running")
        ]
        notes = []
        if self.has_snapshots:
            notes.append("Btrfs snapshot algılandı; silinen dosyaların alanı hemen boşalmayabilir.")
        if running:
            notes.append("Açık uygulamalar: " + ", ".join(running) + ". Önbelleklerini temizlemeden önce kapat.")
        self.warning.setText("  •  ".join(i18n.tr(note) for note in notes))
        self.warning.setVisible(bool(notes))

    def _filter_changed(self, index: int) -> None:
        self.filter_risk = str(self.risk_combo.itemData(index))
        self.render_items()

    def _workflow_changed(self, index: int) -> None:
        if self._updating_profile:
            return
        profile = str(self.workflow_combo.itemData(index))
        self.settings.setValue("workflow/profile", profile)
        self.settings.sync()
        if self.items:
            self._apply_profile()
            self.render_items()

    def _apply_profile(self) -> None:
        profile = str(self.settings.value("workflow/profile", "recommended"))
        if profile == "manual":
            self.selected.clear()
            return
        allowed_risks = {"safe"} if profile == "recommended" else {"safe", "caution"}
        self.selected = {
            item.id
            for item in self.items
            if item.risk in allowed_risks
            and item.action == "delete"
            and not item.meta.get("running")
        }

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_language = i18n.get_language()
        old_threshold = int(self.settings.value("scan/large_file_mb", 150))
        dialog.save_preferences()
        new_language = str(self.settings.value("ui/language", "tr"))
        if new_language != old_language:
            i18n.set_language(new_language)
            i18n.translate_widget_tree(self)
            current_package = self.package_tree.currentItem()
            if current_package:
                self._package_details_changed(current_package, None)
        new_threshold = int(self.settings.value("scan/large_file_mb", 150))
        profile = str(self.settings.value("workflow/profile", "recommended"))
        self._updating_profile = True
        self.workflow_combo.setCurrentIndex(max(0, self.workflow_combo.findData(profile)))
        self._updating_profile = False
        self._apply_profile()
        self._apply_schedule()
        self.render_items()
        if new_language != old_language and self.performance_loaded:
            self.performance_loaded = False
            self.refresh_performance()
        if old_threshold != new_threshold and self.items:
            self._show_status("Büyük dosya eşiği değişti; sonuçlar yenileniyor…")
            self.scan()
        else:
            self._show_status("Tercihler kaydedildi", 5000)

    def _show_status(self, message: str, timeout: int = 0) -> None:
        self.statusBar().showMessage(i18n.tr(message), timeout)

    def show_history(self) -> None:
        HistoryDialog(self).exec()

    def open_trash(self) -> None:
        path = core.TRASH_DIR / "files"
        path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            _message_box("warning", self, "Çöp kutusu açılamadı", f"Folder location: {path}" if i18n.get_language() == "en" else f"Klasör şu konumda: {path}")

    def _apply_schedule(self) -> None:
        self.schedule_timer.stop()
        if not self.settings.value("scan/scheduled", False, type=bool):
            return
        minutes = max(1, int(self.settings.value("scan/interval_minutes", 360)))
        self.schedule_timer.start(minutes * 60 * 1000)
        self._show_status(f"Planlı tarama açık · her {minutes} dakikada bir · otomatik silme kapalı", 8000)

    def _scheduled_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._show_status("Planlı tarama başladı · dosyalar silinmeyecek", 5000)
        self.scan()

    def render_items(self, *_args) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        query = self.search.text().strip().casefold()
        visible = [
            item
            for item in self.items
            if (self.filter_risk == "all" or item.risk == self.filter_risk)
            and (not self.only_selected.isChecked() or item.id in self.selected)
            and (not query or query in f"{i18n.tr(item.title)} {i18n.tr(item.detail)} {item.path or ''}".casefold())
        ]
        for category, metadata in sorted(core.CATEGORIES.items(), key=lambda pair: pair[1]["order"]):
            group = [item for item in visible if item.category == category]
            if not group:
                continue
            if self.sort_combo.currentData() == "name":
                group.sort(key=lambda item: item.title.casefold())
            else:
                group.sort(key=lambda item: item.size, reverse=True)
            size = core.reclaimable_total(group)
            section = QLabel(
                f"{i18n.tr(metadata['title']).upper()}     ·     {len(group)} "
                f"{'items' if i18n.get_language() == 'en' else 'öğe'}     ·     {core.human_size(size)}"
            )
            section.setObjectName("section")
            self.list_layout.insertWidget(self.list_layout.count() - 1, section)
            for candidate in group:
                self.list_layout.insertWidget(self.list_layout.count() - 1, self._item_card(candidate))
        if not visible:
            empty = QLabel("Bu filtrede öğe yok. Yeniden tarayabilir veya filtreyi değiştirebilirsin.")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(120)
            self.list_layout.insertWidget(self.list_layout.count() - 1, empty)
        self._update_metrics()
        i18n.translate_widget_tree(self)

    def _item_card(self, item: core.Item) -> QFrame:
        card = QFrame()
        card.setObjectName("item")
        card.setProperty("selected", "true" if item.id in self.selected else "false")
        card.setProperty("itemId", item.id)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 13, 10)
        row.setSpacing(11)
        checkbox = QCheckBox()
        checkbox.setChecked(item.id in self.selected)
        checkbox.setAccessibleName(
            f"Select {i18n.tr(item.title)}" if i18n.get_language() == "en" else f"{item.title} seç"
        )
        checkbox.toggled.connect(lambda checked, ident=item.id: self._toggle(ident, checked))
        row.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)

        detail_col = QVBoxLayout()
        title_row = QHBoxLayout()
        name = QLabel(i18n.tr(item.title))
        name.setStyleSheet("font-weight:600; font-size:13px")
        name.setWordWrap(True)
        title_row.addWidget(name)
        risk = QLabel(i18n.tr(RISK_LABELS.get(item.risk, item.risk.upper())))
        risk.setObjectName(item.risk)
        title_row.addWidget(risk, 0, Qt.AlignmentFlag.AlignTop)
        if item.requires_root:
            sudo = QLabel("SUDO")
            sudo.setObjectName("blueTag")
            title_row.addWidget(sudo, 0, Qt.AlignmentFlag.AlignTop)
        if item.meta.get("running"):
            active = QLabel("AÇIK")
            active.setObjectName("caution")
            title_row.addWidget(active, 0, Qt.AlignmentFlag.AlignTop)
        title_row.addStretch()
        detail_col.addLayout(title_row)
        description = QLabel(i18n.tr(item.detail))
        description.setObjectName("muted")
        description.setWordWrap(True)
        detail_col.addWidget(description)
        if item.path:
            path = QLabel(item.path.replace(str(core.HOME), "~", 1))
            path.setObjectName("dim")
            path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_col.addWidget(path)
        row.addLayout(detail_col, 1)

        right = QVBoxLayout()
        size = QLabel(core.human_size(item.size))
        size.setAlignment(Qt.AlignmentFlag.AlignRight)
        size.setStyleSheet("font-size:14px; font-weight:700")
        right.addWidget(size)
        count = QLabel(i18n.tr("tahmini" if item.action == "command" else f"{item.files} dosya"))
        count.setObjectName("dim")
        count.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(count)
        if item.action == "command":
            terminal = QPushButton("Open in terminal" if i18n.get_language() == "en" else "Terminalde aç")
            terminal.setToolTip(item.command or "")
            terminal.clicked.connect(lambda _checked=False, candidate=item: self.open_terminal(candidate))
            right.addWidget(terminal)
        row.addLayout(right)
        card.setProperty("selected", "true" if item.id in self.selected else "false")
        return card

    def _toggle(self, ident: str, checked: bool) -> None:
        if checked:
            self.selected.add(ident)
        else:
            self.selected.discard(ident)
        # Yeniden çizim sırasında checkbox odağını kaybetme; metrikleri güncelle.
        self._update_metrics()
        for index in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(index).widget()
            if widget and widget.objectName() == "item":
                checkbox = widget.findChild(QCheckBox)
                if checkbox and widget.property("itemId") == ident:
                    widget.setProperty("selected", "true" if checked else "false")
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)

    def select_safe(self) -> None:
        self.selected = {
            item.id
            for item in self.items
            if item.risk == "safe" and item.action == "delete" and not item.meta.get("running")
        }
        self.render_items()

    def clear_selection(self) -> None:
        self.selected.clear()
        self.render_items()

    def confirm_clean(self) -> None:
        chosen = [self.by_id[ident] for ident in self.selected if ident in self.by_id]
        if not chosen:
            return
        default_mode = str(self.settings.value("cleanup/default_mode", "trash"))
        dialog = ConfirmDialog(chosen, default_mode=default_mode, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ids = [item.id for item in chosen]
        snapshot = {item.id: item for item in chosen}
        self.clean_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self._show_status("Seçilen öğeler temizleniyor…")
        worker = CleanWorker(snapshot, ids, dialog.mode)
        worker.finished_results.connect(lambda results, mode=dialog.mode: self._clean_finished(results, mode))
        worker.finished.connect(self._worker_done)
        self.worker = worker
        worker.start()

    def _clean_finished(self, results: list[dict], mode: str) -> None:
        freed = sum(result.get("freed", 0) for result in results)
        self.selected.clear()
        self._show_status(f"Temizlik tamamlandı · {core.human_size(freed)}", 7000)
        lines = []
        for result in results:
            if result["status"] == "needs_terminal":
                lines.append(f"• {i18n.tr(result['title'])}: " + ("must be opened in a terminal" if i18n.get_language() == "en" else "terminalde açılması gerekiyor") + f"\n  {result['command']}")
            elif result.get("error"):
                lines.append(f"• {i18n.tr(result['title'])}: {i18n.tr(result['error'])}")
            else:
                lines.append(f"• {i18n.tr(result['title'])}: {core.human_size(result.get('freed', 0))}")
        heading = "Temizlik tamamlandı"
        if mode == "trash":
            heading += " (öğeler çöp kutusuna taşındı)"
        if i18n.get_language() == "en":
            heading = "Cleanup complete" + (" (items moved to Trash)" if mode == "trash" else "")
            result_text = f"Reclaimed: {core.human_size(freed)}\n\n" + "\n".join(lines)
        else:
            heading = "Temizlik tamamlandı" + (" (öğeler çöp kutusuna taşındı)" if mode == "trash" else "")
            result_text = f"Boşaltılan: {core.human_size(freed)}\n\n" + "\n".join(lines)
        _message_box("information", self, heading, result_text)
        # Temizlik sonrası kalan alanı ve çöp kutusunu güncel verilerle yeniden tara.
        self.scan_after_clean = True

    def open_terminal(self, item: core.Item) -> None:
        if item.command:
            self._open_command_terminal(item.command)

    def _open_command_terminal(self, command: str) -> None:
        if not command:
            return
        allowed = {item.command for item in self.items if item.action == "command" and item.command}
        allowed.update({"powerprofilesctl set performance", "sudo systemctl enable --now fstrim.timer"})
        if command not in allowed:
            try:
                tokens = shlex.split(command)
                if tokens[:4] != ["sudo", "pacman", "-Rns", "--"] or len(tokens) < 5:
                    raise ValueError("Bu komut Temizci tarafından oluşturulmadı")
                if core.package_removal_command(tokens[4:]) != command:
                    raise ValueError("Paket komutu doğrulanamadı")
            except ValueError as exc:
                _message_box("warning", self, "Güvenlik nedeniyle engellendi", str(exc))
                return
        candidates = [
            ("foot", ["foot", "--title=Temizci", "-e"]),
            ("alacritty", ["alacritty", "-t", "Temizci", "-e"]),
            ("ghostty", ["ghostty", "-e"]),
            ("konsole", ["konsole", "-e"]),
            ("xterm", ["xterm", "-T", "Temizci", "-e"]),
        ]
        wait_message = "Operation finished. Press Enter to close" if i18n.get_language() == "en" else "İşlem tamamlandı. Kapatmak için Enter"
        script = f"{command}; printf '\\n\\n{wait_message}\\n'; read -r"
        for binary, args in candidates:
            if shutil.which(binary):
                try:
                    subprocess.Popen(args + ["bash", "-lc", script], start_new_session=True)
                    self._show_status("Terminal açıldı; sudo parolanı terminalde gir.", 6000)
                except OSError as exc:
                    _message_box("warning", self, "Terminal açılamadı", str(exc))
                return
        _message_box("warning", self, "Terminal bulunamadı", "Install foot, alacritty, ghostty, konsole, or xterm." if i18n.get_language() == "en" else "foot, alacritty, ghostty, konsole veya xterm kurulu olmalı.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt event API
        if self.worker and self.worker.isRunning():
            _message_box(
                "information",
                self,
                "İşlem devam ediyor",
                "Wait for the scan or cleanup to finish before closing this window." if i18n.get_language() == "en" else "Tarama veya temizlik bitince pencereyi kapatabilirsin.",
            )
            event.ignore()
            return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Temizci")
    app.setOrganizationName("Temizci")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLES)
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "temizci.svg"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
