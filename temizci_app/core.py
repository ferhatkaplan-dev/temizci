"""
Temizci çekirdeği: tarama kuralları, boyut hesabı, güvenlik kontrolleri ve silme.

Tasarım ilkeleri
----------------
* Sadece önceden tanımlı kuralların ürettiği yollar silinebilir (istemciden yol kabul edilmez).
* Her silme işlemi öncesi yol, izin verilen kökler ve korunan yollar açısından doğrulanır.
* Sembolik bağlantılar takip edilmez; bağlantının kendisi silinir.
* Riskli öğeler varsayılan olarak seçili gelmez; geri alınabilir silme (çöp) seçeneği sunulur.
* root gerektiren işler (pacman, journald) uygulama içinde çalıştırılmaz; komut olarak sunulur.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import time
import urllib.parse
import configparser
import platform
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = "1.2.0"

HOME = Path(os.environ.get("HOME") or str(Path.home())).resolve()
TRASH_DIR = HOME / ".local" / "share" / "Trash"
STATE_DIR = HOME / ".local" / "state" / "temizci"
HISTORY_FILE = STATE_DIR / "history.jsonl"
AUTOSTART_DIR = HOME / ".config" / "autostart"
DISABLED_AUTOSTART_DIR = STATE_DIR / "autostart-disabled"

# Doğrudan silme yapılabilecek kökler. root gerektiren dizinler yalnızca
# "command" türü öğelerde kullanılır; yine de savunma amaçlı listede tutulur.
ALLOWED_ROOTS: list[Path] = [
    HOME,
    Path("/tmp"),
    Path("/var/tmp"),
    Path("/var/cache/pacman/pkg"),
    Path("/var/log"),
]

RISK_ORDER = {"safe": 0, "caution": 1, "risky": 2}
SCAN_MODES = ("fast", "balanced", "thorough")
DEFAULT_SCAN_WORKERS = 2


@dataclass(frozen=True)
class ScanOptions:
    """Kullanıcıya açık tarama kapsamı ve performans seçenekleri.

    ``categories`` boşsa tüm kategoriler taranır. ``excludes`` içindeki yollar
    ne taranır ne de temizlenebilir. ``workers`` yalnızca bağımsız
    koleksiyoncuları paralelleştirir; hiçbir silme işlemi paralel yapılmaz.
    """

    mode: str = "balanced"
    workers: int = DEFAULT_SCAN_WORKERS
    categories: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    large_file_limit: int = 0


@dataclass(frozen=True)
class Workflow:
    """Tarama sonrası ön seçim profili. Riskli öğeler hiçbir profilde seçilmez."""

    key: str
    title: str
    description: str
    risks: frozenset[str]
    categories: frozenset[str] = frozenset()
    include_running: bool = False


WORKFLOWS: dict[str, Workflow] = {
    "recommended": Workflow(
        "recommended",
        "Önerilen",
        "Yalnızca güvenli öğeleri seçer; açık uygulamaların önbelleklerini ve riskli yedekleri atlar.",
        frozenset({"safe"}),
    ),
    "deep": Workflow(
        "deep",
        "Derin inceleme",
        "Güvenli ve dikkat öğelerini seçer; açık uygulamalar ile riskli yedekler yine atlanır.",
        frozenset({"safe", "caution"}),
    ),
    "low-disk": Workflow(
        "low-disk",
        "Düşük disk alanı",
        "Daha çok alan açmak için güvenli ve dikkat önbelleklerini seçer; kişisel büyük dosya ve yedekleri dışarıda bırakır.",
        frozenset({"safe", "caution"}),
        frozenset({"system", "caches", "browsers", "dev"}),
    ),
    "developer": Workflow(
        "developer",
        "Geliştirici",
        "Geliştirici ve uygulama önbelleklerini seçer; kişisel dosyalara, yedeklere ve büyük dosyalara dokunmaz.",
        frozenset({"safe", "caution"}),
        frozenset({"caches", "browsers", "dev"}),
    ),
    "gaming": Workflow(
        "gaming",
        "Oyun ve grafik",
        "Shader, tarayıcı ve uygulama önbelleklerini seçer; oyun dosyalarına ve projelere dokunmaz.",
        frozenset({"safe", "caution"}),
        frozenset({"caches", "browsers"}),
    ),
    "privacy": Workflow(
        "privacy",
        "Gizlilik",
        "Tarayıcı ve uygulama önbelleklerini seçer; kişisel dosya ve yedekleri kapsam dışı bırakır.",
        frozenset({"safe"}),
        frozenset({"caches", "browsers"}),
    ),
    "manual": Workflow(
        "manual",
        "Manuel seçim",
        "Hiçbir öğeyi otomatik seçmez; tam kontrol sende.",
        frozenset(),
    ),
}

# Bu bağlam değerleri koleksiyoncuların imzasını değiştirmeden tarama
# seçeneklerini onlara ulaştırır. ThreadPoolExecutor görevleri kendi bağlam
# kopyalarıyla çalıştığı için eşzamanlı taramalar birbirini etkilemez.
_ACTIVE_EXCLUDES: contextvars.ContextVar[tuple[Path, ...]] = contextvars.ContextVar(
    "temizci_excludes", default=()
)
_ACTIVE_LARGE_LIMIT: contextvars.ContextVar[int] = contextvars.ContextVar(
    "temizci_large_limit", default=40
)

# Paketiciden sistemin açılışını/temel yönetimini sağlayan öğeler GUI'de
# kaldırılabilir hedef olarak sunulmaz. Pacman'ın kendi bağımlılık denetimi
# ayrıca geçerlidir; bu liste ikinci bir emniyet katmanıdır.
PROTECTED_PACKAGES = {
    "base", "filesystem", "glibc", "pacman", "systemd", "bash", "coreutils",
    "util-linux", "sudo", "dbus", "polkit", "networkmanager", "linux",
    "linux-cachyos", "linux-cachyos-lts", "linux-firmware", "grub", "efibootmgr",
    "mkinitcpio", "systemd-sysvcompat", "shadow", "zsh", "fish",
}

CATEGORIES: dict[str, dict] = {
    "system": {"title": "Sistem", "icon": "cpu", "order": 1},
    "caches": {"title": "Uygulama önbellekleri", "icon": "layers", "order": 2},
    "browsers": {"title": "Tarayıcı önbellekleri", "icon": "globe", "order": 3},
    "dev": {"title": "Geliştirici araçları", "icon": "terminal", "order": 4},
    "backups": {"title": "Eski yedekler", "icon": "archive", "order": 5},
    "files": {"title": "Büyük dosyalar", "icon": "file", "order": 6},
    "trash": {"title": "Çöp kutusu", "icon": "trash", "order": 7},
}

# ~/.cache altında bilinen ve yeniden oluşturulabilen klasörler.
CACHE_TITLES = {
    "zen": "Zen tarayıcı önbelleği",
    "google-chrome": "Chrome önbelleği",
    "mozilla": "Firefox önbelleği",
    "microsoft-edge": "Edge önbelleği",
    "custom-ai-browser": "Özel AI tarayıcı önbelleği",
    "chromium": "Chromium önbelleği",
    "brave": "Brave önbelleği",
    "thumbnails": "Küçük resim önbelleği",
    "pip": "Python paket önbelleği",
    "npm": "npm önbelleği",
    "yarn": "Yarn önbelleği",
    "paru": "paru derleme önbelleği",
    "mesa_shader_cache": "Mesa gölgelendirici önbelleği",
    "cliphist": "Pano geçmişi önbelleği",
    "tealdeer": "tldr önbelleği",
    "electron": "Electron indirme önbelleği",
    "wine": "Wine önbelleği",
    "ms-playwright": "Playwright tarayıcıları",
    "ms-playwright-mcp": "Playwright MCP tarayıcıları",
    "codex-runtimes": "Codex çalışma zamanları",
    "Codex": "Codex önbelleği",
    "opencode": "OpenCode önbelleği",
    "Shelly": "Shelly önbelleği",
    "fontconfig": "Yazı tipi önbelleği",
    "obsidian": "Obsidian önbelleği",
    "discord": "Discord önbelleği",
    "Code": "VS Code önbelleği",
    "ai.opencode.desktop": "OpenCode masaüstü önbelleği",
    "Antigravity IDE": "Antigravity IDE önbelleği",
    "FreeTube": "FreeTube önbelleği",
    "OpenChamber": "OpenChamber önbelleği",
    "openchamber": "OpenChamber önbelleği",
}

CACHE_DETAILS = {
    "codex-runtimes": "Codex'in çalışması için kullandığı yerel bileşenler. Silinirse Codex yeniden indirmek zorunda kalabilir; Codex'i kullanıyorsan bırak.",
    "ms-playwright": "Otomasyon testlerinin kullandığı Chromium/Firefox/WebKit tarayıcıları. Gerektiğinde yeniden indirilir.",
    "ms-playwright-mcp": "Playwright MCP'nin tarayıcıları. Silinirse tarayıcıları yeniden indirmesi gerekir.",
    "paru": "AUR paket kaynakları ve derleme artıkları. Silmek kurulu paketleri kaldırmaz, ancak kaynakları tekrar indirmek gerekir.",
    "wine": "Wine ile ilgili önbellek. Silinirse bazı bileşenler yeniden oluşturulur veya indirilir.",
}

# Varsayılan olarak "dikkat" sayılan, silinince yeniden indirme gerektiren önbellekler.
CAUTION_CACHES = {"ms-playwright", "ms-playwright-mcp", "codex-runtimes", "paru", "wine"}
BROWSER_CACHE_NAMES = {"zen", "google-chrome", "mozilla", "microsoft-edge", "custom-ai-browser", "chromium", "brave"}

BROWSER_CACHE_DIRS = [
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "ShaderCache",
    "GrShaderCache",
    "CachedData",
    "cache2",
    "startupCache",
    "shader-cache",
    "Service Worker/CacheStorage",
    "Service Worker/ScriptCache",
]

BACKUP_MARKERS = ("-backup", "-old-profile", "-back-ovfs", "crashrecovery")

SKIP_TMP_NAMES = {
    "opencode",
    "temizci",
    "systemd-private",
    "snap-private",
    "psd-",
    ".X11-unix",
    ".ICE-unix",
    ".font-unix",
    ".Test-unix",
    ".XIM-unix",
}


class SafetyError(Exception):
    """Yol güvenlik doğrulamasından geçmediğinde fırlatılır."""


@dataclass
class Item:
    id: str
    rule_id: str
    title: str
    detail: str
    path: str | None
    size: int
    files: int
    risk: str
    category: str
    action: str  # delete | command | empty_trash
    paths: list[str] = field(default_factory=list)
    command: str | None = None
    requires_root: bool = False
    selected: bool = False
    last_modified: float | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_order"] = RISK_ORDER.get(self.risk, 9)
        return d


def normalize_excludes(paths) -> tuple[Path, ...]:
    """Hariç tutulan yolları doğrular ve tekilleştirir.

    Göreli yollar ve dosya sisteminin kökü reddedilir; böylece yanlış bir
    ayarın tüm taramayı sessizce devre dışı bırakması engellenir.
    """
    result: list[Path] = []
    for raw in paths or ():
        text = str(raw).strip()
        if not text:
            continue
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            raise ValueError(f"Hariç tutulan yol mutlak olmalı: {text}")
        resolved = candidate.resolve(strict=False)
        if resolved == Path(resolved.anchor):
            raise ValueError(f"Kök dizin hariç tutulamaz: {text}")
        result.append(resolved)
    return tuple(dict.fromkeys(result))


def path_is_excluded(path: str | Path, excludes: tuple[Path, ...]) -> bool:
    if not excludes:
        return False
    raw = Path(path)
    try:
        resolved = raw.resolve(strict=False)
    except OSError:
        resolved = raw
    # Hem yazıldığı yol hem de çözümlenmiş hedef kontrol edilir; böylece bir
    # sembolik bağlantı üzerinden hariç tutulan yola girilemez.
    return any(
        candidate == excluded or excluded in candidate.parents
        for candidate in (raw, resolved)
        for excluded in excludes
    )


def is_excluded(path: str | Path) -> bool:
    """Etkin taramada yolun hariç tutulup tutulmadığını döndürür."""
    return path_is_excluded(path, _ACTIVE_EXCLUDES.get())


def select_items(items: list[Item], workflow: str = "recommended") -> set[str]:
    """Bir iş akışı profiline göre güvenli ön seçim kümesi üretir."""
    profile = WORKFLOWS.get(workflow, WORKFLOWS["recommended"])
    if not profile.risks:
        return set()
    return {
        item.id
        for item in items
        if item.action == "delete"
        and item.risk in profile.risks
        and (not profile.categories or item.category in profile.categories)
        and (profile.include_running or not item.meta.get("running"))
    }


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def human_size(num: float | int) -> str:
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.1f} {unit}".replace(".", ",")
        num /= 1024
    return f"{num:.1f} TB"


def _item_id(rule_id: str, path: str | Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8", "surrogateescape")).hexdigest()[:12]
    return f"{rule_id}:{digest}"


def _run(cmd: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


_SIZE_RE = re.compile(r"([\d.,]+)\s*([KMGTP])(?:i?B)?", re.IGNORECASE)
_BYTES_RE = re.compile(r"([\d.,]+)\s*B\b", re.IGNORECASE)


def parse_size(text: str) -> int:
    """'1.63 GiB', '46.4M' gibi ifadeleri bayta çevirir (son eşleşmeyi kullanır)."""
    matches = list(_SIZE_RE.finditer(text))
    if matches:
        match = matches[-1]
        unit = match.group(2).upper()
    else:
        match = _BYTES_RE.search(text)
        if not match:
            return 0
        unit = ""
    value = float(match.group(1).replace(",", "."))
    mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    return int(value * mult.get(unit, 1))


def walk_size(path: Path, cache: dict[str, tuple[int, int, float]] | None = None) -> tuple[int, int, float | None]:
    """Bir yolun disk üzerindeki boyutunu (bloklar), dosya sayısını ve son değişimini döndürür."""
    key = str(path)
    if cache is not None and key in cache:
        return cache[key]

    total = 0
    files = 0
    newest: float | None = None
    try:
        st = path.lstat()
    except OSError:
        return 0, 0, None

    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        size = getattr(st, "st_blocks", 0) * 512 or st.st_size
        result = (size, 1, st.st_mtime)
        if cache is not None:
            cache[key] = result
        return result

    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        est = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(est.st_mode):
                        stack.append(Path(entry.path))
                    else:
                        total += getattr(est, "st_blocks", 0) * 512 or est.st_size
                        files += 1
                        if newest is None or est.st_mtime > newest:
                            newest = est.st_mtime
        except OSError:
            continue
    result = (total, files, newest)
    if cache is not None:
        cache[key] = result
    return result


def _is_backup_name(name: str) -> bool:
    low = name.lower()
    return any(marker in low for marker in BACKUP_MARKERS)


def _protected_paths() -> set[Path]:
    """Tam olarak silinmemesi gereken yollar (altlarındaki öğeler serbesttir)."""
    protected = {
        HOME,
        HOME / ".config",
        HOME / ".local",
        HOME / ".local" / "share",
        HOME / ".ssh",
        HOME / ".gnupg",
        HOME / "Documents",
        HOME / "Desktop",
        HOME / "Downloads",
        HOME / "Pictures",
        HOME / "Videos",
        HOME / "Projects",
        TRASH_DIR,
    }
    zen = HOME / ".config" / "zen"
    if zen.is_dir():
        try:
            for entry in zen.iterdir():
                if entry.is_dir() and not _is_backup_name(entry.name):
                    protected.add(entry.resolve())
        except OSError:
            pass
    return {p.resolve() for p in protected if p.exists() or p == HOME}


def assert_safe_path(path: str | Path) -> Path:
    """Silinmesi istenen yolun güvenli olduğunu doğrular; değilse SafetyError fırlatır."""
    p = Path(path)
    if not p.is_absolute():
        raise SafetyError(f"Göreli yol reddedildi: {path}")
    if any(part == ".." for part in p.parts):
        raise SafetyError(f"Üst dizin içeren yol reddedildi: {path}")

    try:
        st = p.lstat()
    except FileNotFoundError as exc:
        raise SafetyError(f"Yol bulunamadı: {path}") from exc
    except OSError as exc:
        raise SafetyError(f"Yol okunamadı: {path} ({exc})") from exc

    if stat.S_ISLNK(st.st_mode):
        # Bağlantının kendisi silinecek; hedefi asla takip edilmez.
        parent = p.parent.resolve()
        roots = [r.resolve() for r in ALLOWED_ROOTS]
        if not any(parent == r or r in parent.parents for r in roots):
            raise SafetyError(f"Bağlantının bulunduğu dizin izinli değil: {path}")
        if parent in _protected_paths():
            raise SafetyError(f"Korunan dizindeki bağlantı reddedildi: {path}")
        return p

    resolved = p.resolve()
    roots = [r.resolve() for r in ALLOWED_ROOTS]
    if not any(resolved == r or r in resolved.parents for r in roots):
        raise SafetyError(f"İzin verilen köklerin dışında: {path}")

    protected = _protected_paths()
    if resolved in protected:
        raise SafetyError(f"Korunan yol silinemez: {path}")
    for prot in protected:
        if prot != resolved and resolved in prot.parents:
            raise SafetyError(f"Korunan bir yolun üst dizini silinemez: {path}")

    if os.path.ismount(p):
        raise SafetyError(f"Bağlama noktası silinemez: {path}")

    return p


# ---------------------------------------------------------------------------
# Silme / çöp kutusu
# ---------------------------------------------------------------------------


def _unique_trash_name(name: str) -> str:
    candidate = name
    counter = 1
    while (TRASH_DIR / "files" / candidate).exists() or (TRASH_DIR / "info" / f"{candidate}.trashinfo").exists():
        counter += 1
        candidate = f"{name}.{counter}"
    return candidate


def move_to_trash(path: Path) -> int:
    """XDG çöp kutusuna taşır. Taşınan boyutu döndürür."""
    assert_safe_path(path)
    size = walk_size(path)[0]
    files_dir = TRASH_DIR / "files"
    info_dir = TRASH_DIR / "info"
    files_dir.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)
    name = _unique_trash_name(path.name or "dosya")
    destination = files_dir / name
    shutil.move(str(path), str(destination))
    info = (
        "[Trash Info]\n"
        f"Path={urllib.parse.quote(str(path), safe='/')}\n"
        f"DeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
    )
    (info_dir / f"{name}.trashinfo").write_text(info, encoding="utf-8")
    return size


def delete_permanently(path: Path) -> int:
    assert_safe_path(path)
    size = walk_size(path)[0]
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return size


def empty_trash() -> tuple[int, int]:
    """Çöp kutusunu boşaltır: (silinen bayt, silinen öğe)."""
    files_dir = TRASH_DIR / "files"
    info_dir = TRASH_DIR / "info"
    freed = 0
    count = 0
    if files_dir.is_dir():
        for entry in list(files_dir.iterdir()):
            try:
                freed += walk_size(entry)[0]
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                count += 1
            except OSError:
                continue
    if info_dir.is_dir():
        for entry in list(info_dir.glob("*.trashinfo")):
            try:
                entry.unlink()
            except OSError:
                pass
    return freed, count


# ---------------------------------------------------------------------------
# Tarama koleksiyoncuları
# ---------------------------------------------------------------------------


def _make_item(
    rule_id: str,
    title: str,
    detail: str,
    path: Path | None,
    size: int,
    files: int,
    risk: str,
    category: str,
    action: str = "delete",
    *,
    paths: list[Path] | None = None,
    command: str | None = None,
    requires_root: bool = False,
    last_modified: float | None = None,
    meta: dict | None = None,
) -> Item:
    real_paths = [str(p) for p in (paths or ([path] if path else []))]
    ident = _item_id(rule_id, real_paths[0] if real_paths else command or title)
    return Item(
        id=ident,
        rule_id=rule_id,
        title=title,
        detail=detail,
        path=str(path) if path else None,
        size=size,
        files=files,
        risk=risk,
        category=category,
        action=action,
        paths=real_paths,
        command=command,
        requires_root=requires_root,
        selected=(risk == "safe" and action == "delete" and not requires_root),
        last_modified=last_modified,
        meta=meta or {},
    )


def collect_pacman(cache: dict) -> list[Item]:
    items: list[Item] = []
    pkg_dir = Path("/var/cache/pacman/pkg")
    if not pkg_dir.is_dir() or is_excluded(pkg_dir):
        return items
    size, files, newest = walk_size(pkg_dir, cache)
    if size < 1:
        return items

    savings = 0
    if shutil.which("paccache"):
        code, out, err = _run(["paccache", "-d", "-k1"], timeout=30)
        savings = parse_size(out + err)

    items.append(
        _make_item(
            "pacman-keep1",
            "Pacman önbelleği — son sürümü sakla",
            "Eski paket sürümleri silinir; son sürümler geri dönüş için kalır. sudo gerekir.",
            pkg_dir,
            savings or int(size * 0.3),
            files,
            "safe",
            "system",
            "command",
            command="sudo paccache -rk1",
            requires_root=True,
            last_modified=newest,
            meta={"raw_size": size, "keep": 1},
        )
    )
    items.append(
        _make_item(
            "pacman-all",
            "Pacman önbelleğinin tamamı",
            "Tüm paket arşivleri silinir. Eski sürümlere geri dönüş mümkün olmaz. sudo gerekir.",
            pkg_dir,
            size,
            files,
            "risky",
            "system",
            "command",
            command="sudo paccache -rk0",
            requires_root=True,
            last_modified=newest,
            meta={"raw_size": size, "keep": 0},
        )
    )
    return items


def collect_journal(cache: dict) -> list[Item]:
    items: list[Item] = []
    if not shutil.which("journalctl"):
        return items
    code, out, err = _run(["journalctl", "--disk-usage"], timeout=15)
    if code != 0:
        return items
    size = parse_size(out + err)
    if size < 1:
        return items
    target = 200 * 1024**2
    reclaim = max(0, size - target)
    if reclaim < 5 * 1024**2:
        return items
    items.append(
        _make_item(
            "journal-vacuum",
            "systemd günlükleri",
            "Günlükler 200 MB'a küçültülür. sudo gerekir.",
            Path("/var/log/journal"),
            reclaim,
            0,
            "safe",
            "system",
            "command",
            command="sudo journalctl --vacuum-size=200M",
            requires_root=True,
            meta={"raw_size": size, "target": target},
        )
    )
    return items


def collect_orphans(cache: dict) -> list[Item]:
    if not shutil.which("pacman"):
        return []
    code, out, err = _run(["pacman", "-Qdtq"], timeout=20)
    if code != 0:
        return []
    packages = [line.strip() for line in out.splitlines() if line.strip()]
    if not packages:
        return []

    installed = 0
    for pkg in packages[:80]:
        code, info, _ = _run(["pacman", "-Qi", pkg], timeout=10)
        if code == 0:
            match = re.search(r"Installed Size\s*:\s*(.+)", info)
            if match:
                installed += parse_size(match.group(1))

    quoted = " ".join(shlex.quote(p) for p in packages)
    return [
        _make_item(
            "orphan-packages",
            f"Artık paketler ({len(packages)} adet)",
            "Hiçbir paketin bağımlılığı olmayan paketler: " + ", ".join(packages[:6]) + ("…" if len(packages) > 6 else ""),
            None,
            installed,
            0,
            "caution",
            "system",
            "command",
            command=f"sudo pacman -Rns -- {quoted}",
            requires_root=True,
            meta={"packages": packages, "count": len(packages)},
        )
    ]


def parse_pacman_info(text: str) -> list[dict]:
    """Parse pacman -Qi output without relying on localized field positions."""
    blocks = re.split(r"(?m)(?=^Name\s+:)", text)
    result: list[dict] = []
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            match = re.match(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$", line)
            if match:
                fields[match.group(1).strip()] = match.group(2).strip()
        name = fields.get("Name")
        if not name:
            continue
        result.append(
            {
                "name": name,
                "version": fields.get("Version", ""),
                "description": fields.get("Description", "Açıklama yok"),
                "size": parse_size(fields.get("Installed Size", "")),
                "reason": fields.get("Install Reason", "Bilinmiyor"),
                "required_by": fields.get("Required By", "None"),
                "install_date": fields.get("Install Date", ""),
                "source": fields.get("Installed From", ""),
                "groups": fields.get("Groups", "None"),
            }
        )
    return result


def is_protected_package(name: str) -> bool:
    lower = name.casefold()
    return lower in PROTECTED_PACKAGES or lower.startswith(("linux-cachyos-", "linux-headers"))


def collect_installed_packages() -> list[dict]:
    """List explicit user packages and orphan dependencies; does not mutate pacman."""
    if not shutil.which("pacman"):
        return []
    code, explicit_out, _ = _run(["pacman", "-Qqe"], timeout=30)
    if code != 0:
        return []
    explicit = {line.strip() for line in explicit_out.splitlines() if line.strip()}
    code, orphan_out, _ = _run(["pacman", "-Qdtq"], timeout=30)
    orphans = {line.strip() for line in orphan_out.splitlines() if line.strip()} if code == 0 else set()
    names = sorted(explicit | orphans)
    if not names:
        return []

    # A single query is far faster and more consistent than one pacman process per package.
    code, info, _ = _run(["pacman", "-Qi", *names], timeout=45)
    if code != 0:
        return []
    packages = parse_pacman_info(info)
    for package in packages:
        name = package["name"]
        package["explicit"] = name in explicit
        package["orphan"] = name in orphans
        package["protected"] = is_protected_package(name)
        package["selected"] = False
        package["size_label"] = human_size(package["size"])
    packages.sort(key=lambda p: (not p["orphan"], -p["size"], p["name"].casefold()))
    return packages


_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9@._+:-]+$")


def preview_package_removal(names: list[str]) -> dict:
    """Use pacman's read-only remove/recursive/print mode to list transaction targets."""
    unique = list(dict.fromkeys(names))
    if not unique:
        raise ValueError("Önizleme için paket seçilmedi")
    if len(unique) > 120:
        raise ValueError("Tek işlemde en fazla 120 paket seçebilirsin")
    invalid = [name for name in unique if not _PACKAGE_NAME_RE.fullmatch(name)]
    protected = [name for name in unique if is_protected_package(name)]
    if invalid:
        raise ValueError("Geçersiz paket adı: " + ", ".join(invalid))
    if protected:
        raise ValueError("Temel sistem paketleri kaldırma listesinden korunuyor: " + ", ".join(protected))
    code, out, err = _run(
        ["pacman", "-Rsp", "--print-format", "%n", "--", *unique],
        timeout=45,
    )
    if code != 0:
        raise ValueError((err or out or "Pacman işlem önizlemesi başarısız").strip())
    targets = list(dict.fromkeys(line.strip() for line in out.splitlines() if line.strip()))
    if not targets:
        raise ValueError("Pacman işlem önizlemesinde kaldırılacak hedef bulunamadı")
    protected_targets = [name for name in targets if is_protected_package(name)]
    if protected_targets:
        raise ValueError("İşlem planı temel sistem paketlerini etkiliyor; güvenlik için engellendi: " + ", ".join(protected_targets))
    code, info, _ = _run(["pacman", "-Qi", *targets], timeout=45)
    target_info = parse_pacman_info(info) if code == 0 else []
    return {
        "selected": unique,
        "targets": targets,
        "size": sum(package["size"] for package in target_info),
        "packages": target_info,
        "command": package_removal_command(unique),
    }


def package_removal_command(names: list[str]) -> str:
    unique = list(dict.fromkeys(names))
    if not unique or any(not _PACKAGE_NAME_RE.fullmatch(name) for name in unique):
        raise ValueError("Paket listesi geçersiz")
    if any(is_protected_package(name) for name in unique):
        raise ValueError("Temel sistem paketleri kaldırma listesinden korunuyor")
    return "sudo pacman -Rns -- " + " ".join(shlex.quote(name) for name in unique)


def list_user_autostart() -> list[dict]:
    """List user-owned autostart entries (system-wide entries are read-only)."""
    result: list[dict] = []
    if not AUTOSTART_DIR.is_dir():
        return result
    try:
        entries = sorted(AUTOSTART_DIR.glob("*.desktop"), key=lambda p: p.name.casefold())
    except OSError:
        return result
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            resolved = entry.resolve()
            if resolved.parent != AUTOSTART_DIR.resolve():
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            parser.read(entry, encoding="utf-8")
            section = parser["Desktop Entry"] if parser.has_section("Desktop Entry") else {}
            if section.get("Type", "Application") != "Application":
                continue
            if section.get("Hidden", "false").casefold() == "true":
                continue
            if section.get("X-GNOME-Autostart-enabled", "true").casefold() == "false":
                continue
            result.append(
                {
                    "filename": entry.name,
                    "name": section.get("Name", entry.stem),
                    "comment": section.get("Comment", "Kullanıcı oturumunda otomatik başlatılır"),
                    "exec": section.get("Exec", ""),
                    "path": str(entry),
                }
            )
        except (OSError, configparser.Error, UnicodeError):
            continue
    return result


def disable_user_autostart(filenames: list[str]) -> list[dict]:
    """Reversibly move user autostart entries out of XDG autostart."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    DISABLED_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    allowed = {item["filename"] for item in list_user_autostart()}
    results = []
    for filename in dict.fromkeys(filenames):
        if filename not in allowed or Path(filename).name != filename or not filename.endswith(".desktop"):
            results.append({"filename": filename, "ok": False, "error": "Bu başlangıç öğesi listede yok"})
            continue
        source = AUTOSTART_DIR / filename
        destination = DISABLED_AUTOSTART_DIR / filename
        if destination.exists():
            results.append({"filename": filename, "ok": False, "error": "Devre dışı öğe zaten mevcut"})
            continue
        try:
            if source.is_symlink() or source.resolve().parent != AUTOSTART_DIR.resolve():
                raise SafetyError("Güvenli kullanıcı başlangıç yolu doğrulanamadı")
            shutil.move(str(source), str(destination))
            results.append({"filename": filename, "ok": True})
        except (OSError, SafetyError) as exc:
            results.append({"filename": filename, "ok": False, "error": str(exc)})
    return results


def list_disabled_autostart() -> list[dict]:
    result = []
    try:
        entries = sorted(DISABLED_AUTOSTART_DIR.glob("*.desktop"), key=lambda p: p.name.casefold())
    except OSError:
        return result
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            continue
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        try:
            parser.read(entry, encoding="utf-8")
            section = parser["Desktop Entry"] if parser.has_section("Desktop Entry") else {}
            result.append({"filename": entry.name, "name": section.get("Name", entry.stem)})
        except (OSError, configparser.Error, UnicodeError):
            result.append({"filename": entry.name, "name": entry.stem})
    return result


def restore_user_autostart(filenames: list[str]) -> list[dict]:
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    allowed = {item["filename"] for item in list_disabled_autostart()}
    results = []
    for filename in dict.fromkeys(filenames):
        if filename not in allowed or Path(filename).name != filename or not filename.endswith(".desktop"):
            results.append({"filename": filename, "ok": False, "error": "Devre dışı başlangıç öğesi listede yok"})
            continue
        source = DISABLED_AUTOSTART_DIR / filename
        destination = AUTOSTART_DIR / filename
        if destination.exists() or destination.is_symlink():
            results.append({"filename": filename, "ok": False, "error": "Aynı adlı başlangıç dosyası zaten var; üzerine yazılmadı"})
            continue
        try:
            if source.is_symlink() or source.resolve().parent != DISABLED_AUTOSTART_DIR.resolve():
                raise SafetyError("Güvenli devre dışı başlangıç yolu doğrulanamadı")
            shutil.move(str(source), str(destination))
            results.append({"filename": filename, "ok": True})
        except (OSError, SafetyError) as exc:
            results.append({"filename": filename, "ok": False, "error": str(exc)})
    return results


def collect_user_caches(cache: dict) -> list[Item]:
    items: list[Item] = []
    cache_root = HOME / ".cache"
    if not cache_root.is_dir():
        return items

    try:
        entries = sorted(cache_root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return items

    for entry in entries:
        if entry.name in {"temizci"} or entry.is_symlink() or is_excluded(entry):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        size, files, newest = walk_size(entry, cache)
        if size < 5 * 1024**2:
            continue
        running = entry.name in BROWSER_CACHE_NAMES and _app_running(entry.name)
        risk = "caution" if entry.name in CAUTION_CACHES or running else "safe"
        title = CACHE_TITLES.get(entry.name, f"Önbellek: {entry.name}")
        detail = CACHE_DETAILS.get(entry.name, "Yeniden oluşturulabilir önbellek.")
        if running:
            detail = "Uygulama açık; önbelleği temizlemeden önce kapatmanız önerilir."
        items.append(
            _make_item(
                "user-cache",
                title,
                detail,
                entry,
                size,
                files,
                risk,
                "browsers" if entry.name in BROWSER_CACHE_NAMES else "caches",
                "delete",
                last_modified=newest,
                meta={"cache_name": entry.name, "running": running},
            )
        )
    return items


def collect_browser_caches(cache: dict) -> list[Item]:
    items: list[Item] = []
    config = HOME / ".config"
    if not config.is_dir() or is_excluded(config):
        return items

    def cache_dir(candidate: Path) -> bool:
        return candidate.is_dir() and not candidate.is_symlink() and not is_excluded(candidate)

    try:
        app_dirs = [
            p
            for p in config.iterdir()
            if p.is_dir() and not p.name.startswith(".") and not is_excluded(p)
        ]
    except OSError:
        return items

    for app in app_dirs:
        if _is_backup_name(app.name):
            continue
        found: list[Path] = []
        # Uygulama kökündeki doğrudan önbellekler
        for name in BROWSER_CACHE_DIRS:
            candidate = app / name
            if cache_dir(candidate):
                found.append(candidate)

        # Profil alt dizinleri (Default, Profile 1, Zen profilleri...)
        try:
            profiles = [p for p in app.iterdir() if p.is_dir() and not p.is_symlink()]
        except OSError:
            profiles = []
        for profile in profiles:
            if _is_backup_name(profile.name) or profile.name in {"Cache", "Code Cache", "GPUCache"}:
                continue
            for name in BROWSER_CACHE_DIRS:
                candidate = profile / name
                if cache_dir(candidate):
                    found.append(candidate)
            # OpenChamber gibi gömülü tarayıcı bölümleri
            if profile.name in {"Partitions", "partitions"}:
                try:
                    partitions = [p for p in profile.iterdir() if p.is_dir() and not p.is_symlink()]
                except OSError:
                    partitions = []
                for part in partitions:
                    for name in BROWSER_CACHE_DIRS:
                        candidate = part / name
                        if cache_dir(candidate):
                            found.append(candidate)

        # Aynı yolu iki kez sayma
        seen: set[str] = set()
        unique: list[Path] = []
        for path in found:
            key = str(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        if not unique:
            continue

        size = 0
        files = 0
        newest = None
        for path in unique:
            s, f, m = walk_size(path, cache)
            size += s
            files += f
            if m and (newest is None or m > newest):
                newest = m
        if size < 10 * 1024**2:
            continue

        label = CACHE_TITLES.get(app.name)
        title = label if label else f"Önbellek: {app.name}"
        running = _app_running(app.name)
        risk = "caution" if running else "safe"
        detail = f"{len(unique)} önbellek klasörü."
        if running:
            detail += " Uygulama açık; kapatmanız önerilir."
        items.append(
            _make_item(
                "app-cache",
                title,
                detail,
                unique[0],
                size,
                files,
                risk,
                "browsers",
                "delete",
                paths=unique,
                last_modified=newest,
                meta={"app": app.name, "running": running, "path_count": len(unique)},
            )
        )
    return items


_RUNNING_PROCESS_CACHE: dict[str, bool] = {}


def _app_running(name: str) -> bool:
    if name in _RUNNING_PROCESS_CACHE:
        return _RUNNING_PROCESS_CACHE[name]
    needles = {
        "zen": ["zen"],
        "google-chrome": ["chrome"],
        "microsoft-edge": ["msedge"],
        "mozilla": ["firefox"],
        "OpenChamber": ["openchamber"],
        "Code": ["code"],
        "ai.opencode.desktop": ["opencode"],
        "discord": ["discord"],
    }.get(name, [name.lower()])
    running = False
    try:
        proc = subprocess.run(["ps", "-eo", "comm="], capture_output=True, text=True, timeout=5)
        names = [line.strip().lower() for line in proc.stdout.splitlines()]
        running = any(any(n in procname for n in needles) for procname in names)
    except (OSError, subprocess.TimeoutExpired):
        pass
    _RUNNING_PROCESS_CACHE[name] = running
    return running


def collect_dev(cache: dict) -> list[Item]:
    items: list[Item] = []
    candidates: list[tuple[Path, str, str, str]] = [
        (HOME / ".npm" / "_cacache", "npm paket önbelleği", "safe", "Yeniden indirilebilir npm arşivi."),
        (HOME / ".cargo" / "registry", "Cargo kayıt defteri önbelleği", "caution", "Silinirse derlemelerde yeniden indirme gerekir."),
        (HOME / ".cache" / "paru" / "clone", "paru AUR derleme önbelleği", "caution", "AUR depoları yeniden klonlanır."),
    ]
    for path, title, risk, detail in candidates:
        if not path.is_dir() or path.is_symlink() or is_excluded(path):
            continue
        size, files, newest = walk_size(path, cache)
        if size < 10 * 1024**2:
            continue
        items.append(
            _make_item(
                "dev-cache",
                title,
                detail,
                path,
                size,
                files,
                risk,
                "dev",
                "delete",
                last_modified=newest,
            )
        )

    # Projelerdeki node_modules klasörleri (yalnızca belirgin biçimde büyükse)
    projects = HOME / "Projects"
    if projects.is_dir() and not is_excluded(projects):
        try:
            for project in projects.iterdir():
                if not project.is_dir() or project.is_symlink():
                    continue
                nm = project / "node_modules"
                if not nm.is_dir() or nm.is_symlink() or is_excluded(nm):
                    continue
                size, files, newest = walk_size(nm, cache)
                if size < 100 * 1024**2:
                    continue
                items.append(
                    _make_item(
                        "node-modules",
                        f"node_modules: {project.name}",
                        "Proje bağımlılıkları; npm/pnpm install ile yeniden kurulur.",
                        nm,
                        size,
                        files,
                        "caution",
                        "dev",
                        "delete",
                        last_modified=newest,
                    )
                )
        except OSError:
            pass
    return items


def collect_backups(cache: dict) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()

    def add(entry: Path, rule_id: str, title: str, detail: str, kind: str) -> None:
        key = str(entry)
        if key in seen or is_excluded(entry):
            return
        size, files, newest = walk_size(entry, cache)
        if size < 10 * 1024**2:
            return
        seen.add(key)
        items.append(
            _make_item(
                rule_id,
                title,
                detail,
                entry,
                size,
                files,
                "risky",
                "backups",
                "trash",
                last_modified=newest,
                meta={"kind": kind},
            )
        )

    zen = HOME / ".config" / "zen"
    if zen.is_dir() and not is_excluded(zen):
        try:
            entries = list(zen.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            if not _is_backup_name(entry.name):
                continue
            add(
                entry,
                "zen-backup",
                f"Zen yedeği: {_backup_label(entry.name)}",
                "Eski tarayıcı profili yedeği. Çöpe taşımak geri alınabilir; kalıcı silmek alanı hemen açar.",
                "zen-backup",
            )

    brain = HOME / ".brain-forest-backup_asd"
    if brain.is_dir() and not is_excluded(brain):
        try:
            entries = [p for p in brain.iterdir() if p.is_file() and not p.is_symlink()]
        except OSError:
            entries = []
        for entry in entries:
            if not _is_backup_name(entry.name):
                continue
            add(
                entry,
                "brain-backup",
                f"Çökme kurtarma arşivi: {_backup_label(entry.name)}",
                "Brain Forest çökme kurtarma arşivi. İçeriğinden emin değilseniz önce çöpe taşıyın.",
                "brain-backup",
            )

    # Ev dizini kökünde duran çökme kurtarma arşivleri
    try:
        home_archives = [
            p
            for p in HOME.iterdir()
            if p.is_file()
            and not p.is_symlink()
            and p.name.startswith(".brain-forest-backup")
            and _is_backup_name(p.name)
        ]
    except OSError:
        home_archives = []
    for entry in home_archives:
        add(
            entry,
            "brain-backup",
            f"Çökme kurtarma arşivi: {_backup_label(entry.name)}",
            "Ev dizininde duran Brain Forest çökme kurtarma arşivi. İçeriğinden emin değilseniz önce çöpe taşıyın.",
            "brain-backup",
        )
    return items


def _backup_label(name: str) -> str:
    match = re.search(r"(\d{8})[_-](\d{4,6})", name)
    if match:
        raw = match.group(1)
        label = f"{raw[6:8]}.{raw[4:6]}.{raw[0:4]} · {match.group(2)[:2]}:{match.group(2)[2:4]}"
        if "unused" in name.lower():
            label += " · kullanılmayan"
        return label
    low = name.lower()
    if "back-ovfs" in low:
        return "overlay yedeği"
    if low.endswith("-backup"):
        return "ana profil yedeği"
    if "old-profile" in low:
        return "eski profil"
    return name[:60]


def collect_tmp(cache: dict) -> list[Item]:
    items: list[Item] = []
    tmp = Path("/tmp")
    if not tmp.is_dir() or is_excluded(tmp):
        return items
    now = time.time()
    cutoff = now - 7 * 24 * 3600
    try:
        entries = list(tmp.iterdir())
    except OSError:
        return items

    for entry in entries:
        name = entry.name
        if any(name.startswith(skip) for skip in SKIP_TMP_NAMES):
            continue
        if is_excluded(entry):
            continue
        try:
            st = entry.lstat()
        except OSError:
            continue
        if st.st_uid != os.getuid():
            continue
        if stat.S_ISLNK(st.st_mode):
            continue
        if st.st_mtime > cutoff:
            continue
        size, files, newest = walk_size(entry, cache)
        if size < 10 * 1024**2:
            continue
        items.append(
            _make_item(
                "tmp-stale",
                f"Eski geçici dosya: {name}",
                "7 günden uzun süredir değiştirilmemiş /tmp içeriği.",
                entry,
                size,
                files,
                "caution",
                "system",
                "delete",
                last_modified=newest or st.st_mtime,
            )
        )
    return items


LARGE_FILE_ROOTS = ["Downloads", "Desktop", "Videos", "Documents", "Pictures", "Projects"]
LARGE_FILE_MIN = 150 * 1024**2
LARGE_FILE_LIMIT = 40
PRUNE_DIRS = {"node_modules", ".git", ".cache", ".venv", "venv", "__pycache__", ".npm", ".cargo", "Trash"}


def collect_large_files(cache: dict) -> list[Item]:
    found: list[tuple[int, Path, float]] = []
    limit = max(1, int(_ACTIVE_LARGE_LIMIT.get()))

    def visit(root: Path) -> None:
        # os.scandir tabanlı yineleme: her dosya için ayrı Path/lstat yerine
        # DirEntry önbelleğini kullanır ve gizli/üretim dizinlerini budar.
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if (
                                    entry.name in PRUNE_DIRS
                                    or entry.name.startswith(".")
                                    or _is_backup_name(entry.name)
                                    or is_excluded(entry.path)
                                ):
                                    continue
                                stack.append(Path(entry.path))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            est = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if est.st_size >= LARGE_FILE_MIN:
                            found.append((est.st_size, Path(entry.path), est.st_mtime))
            except OSError:
                continue

    for name in LARGE_FILE_ROOTS:
        root = HOME / name
        if root.is_dir() and not is_excluded(root):
            visit(root)
    if not is_excluded(HOME):
        try:
            with os.scandir(HOME) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                            continue
                        est = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if est.st_size >= LARGE_FILE_MIN:
                        found.append((est.st_size, Path(entry.path), est.st_mtime))
        except OSError:
            pass

    found.sort(key=lambda x: x[0], reverse=True)
    items: list[Item] = []
    for size, path, mtime in found[:limit]:
        items.append(
            _make_item(
                "large-file",
                f"Büyük dosya: {path.name}",
                str(path.parent).replace(str(HOME), "~", 1),
                path,
                size,
                1,
                "caution",
                "files",
                "trash",
                last_modified=mtime,
                meta={"kind": "large-file"},
            )
        )
    return items


def collect_trash(cache: dict) -> list[Item]:
    files_dir = TRASH_DIR / "files"
    if not files_dir.is_dir() or is_excluded(files_dir):
        return []
    size, files, newest = walk_size(files_dir, cache)
    if size < 1024**2:
        return []
    return [
        _make_item(
            "trash",
            "Çöp kutusu",
            f"{files} öğe. Boşaltmak kalıcıdır; çöp kutusundaki dosyalar geri getirilemez.",
            files_dir,
            size,
            files,
            "caution",
            "trash",
            "empty_trash",
            last_modified=newest,
        )
    ]


COLLECTORS = [
    ("system", "Sistem paketleri", collect_pacman),
    ("system", "Sistem günlükleri", collect_journal),
    ("system", "Artık paketler", collect_orphans),
    ("caches", "Uygulama önbellekleri", collect_user_caches),
    ("browsers", "Tarayıcı önbellekleri", collect_browser_caches),
    ("dev", "Geliştirici araçları", collect_dev),
    ("backups", "Eski yedekler", collect_backups),
    ("system", "Geçici dosyalar", collect_tmp),
    ("files", "Büyük dosyalar", collect_large_files),
    ("trash", "Çöp kutusu", collect_trash),
]


def reclaimable_total(items: list[Item]) -> int:
    """Aynı yolu paylaşan alternatif komutları iki kez saymadan toplam kazancı hesaplar."""
    physical = sum(item.size for item in items if item.action != "command")
    commands: dict[str, int] = {}
    for item in items:
        if item.action != "command":
            continue
        key = item.path or item.id
        commands[key] = max(commands.get(key, 0), item.size)
    return physical + sum(commands.values())


def disk_info() -> dict:
    try:
        usage = shutil.disk_usage(str(HOME))
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
            "mount": str(HOME),
        }
    except OSError:
        return {"total": 0, "used": 0, "free": 0, "percent": 0, "mount": str(HOME)}


def scan_all(
    progress=None,
    options: ScanOptions | None = None,
    stats: dict | None = None,
    on_partial=None,
) -> list[Item]:
    """Tüm kuralları çalıştırır.

    Bağımsız koleksiyoncular ``options.workers`` kadar iş parçacığında paralel
    çalışır; ilerleme ve kısmi sonuç geri çağrıları ana iş parçacığından
    yapılır. ``on_partial`` ilk sonuçların erken gösterilmesini sağlar.
    ``stats`` verilirse süre ve koleksiyoncu dağılımı bu sözlüğe yazılır.
    """
    options = options or ScanOptions()
    mode = options.mode if options.mode in SCAN_MODES else "balanced"
    excludes = normalize_excludes(options.excludes)
    categories = tuple(dict.fromkeys(c for c in options.categories if c))
    workers = max(1, min(int(options.workers or DEFAULT_SCAN_WORKERS), 8))
    large_limit = max(
        1,
        int(options.large_file_limit or (100 if mode == "thorough" else LARGE_FILE_LIMIT)),
    )

    selected = [
        (category, label, collector)
        for category, label, collector in COLLECTORS
        if (not categories or category in categories)
        and not (mode == "fast" and category == "files")
    ]

    cache: dict[str, tuple[int, int, float]] = {}
    collected: list[tuple[str, list[Item], float]] = []
    total = len(selected)
    started = time.monotonic()

    def emit_partial() -> None:
        if on_partial is None or not collected:
            return
        partial = [item for _label, group, _duration in collected for item in group]
        if excludes:
            partial = [
                item
                for item in partial
                if not any(path_is_excluded(path, excludes) for path in item.paths)
            ]
        partial.sort(
            key=lambda i: (
                CATEGORIES.get(i.category, {}).get("order", 99),
                RISK_ORDER.get(i.risk, 9),
                -i.size,
            )
        )
        on_partial(partial)

    def execute_collector(collector):
        collector_started = time.monotonic()
        try:
            items = collector(cache)
        except Exception:  # tek kural patlarsa tarama devam etsin
            items = []
        return items, time.monotonic() - collector_started

    if progress and selected:
        progress(0, total, selected[0][1])

    excludes_token = _ACTIVE_EXCLUDES.set(excludes)
    limit_token = _ACTIVE_LARGE_LIMIT.set(large_limit)
    try:
        if total == 0:
            pass
        elif workers == 1:
            for index, (_category, label, collector) in enumerate(selected):
                if progress:
                    progress(index, total, label)
                collector_started = time.monotonic()
                try:
                    items = collector(cache)
                except Exception:  # tek kural patlarsa tarama devam etsin
                    items = []
                collected.append((label, items, time.monotonic() - collector_started))
                emit_partial()
                if progress:
                    progress(index + 1, total, label)
        else:
            completed = 0
            with ThreadPoolExecutor(max_workers=min(workers, total)) as executor:
                futures = {}
                for _category, label, collector in selected:
                    # Bağlam kopyası, hariç tutma ve büyük dosya limitini
                    # çalışan iş parçacığına taşır.
                    context = contextvars.copy_context()
                    futures[executor.submit(context.run, execute_collector, collector)] = label
                for future in as_completed(futures):
                    label = futures[future]
                    try:
                        items, duration = future.result()
                    except Exception:  # tek kural patlarsa tarama devam etsin
                        items = []
                        duration = 0.0
                    collected.append((label, items, duration))
                    emit_partial()
                    completed += 1
                    if progress:
                        progress(completed, total, label)
    finally:
        _ACTIVE_LARGE_LIMIT.reset(limit_token)
        _ACTIVE_EXCLUDES.reset(excludes_token)

    items = [item for _label, group, _duration in collected for item in group]

    # Hariç tutulan bir yol, bir koleksiyoncu tarafından üretilmiş olsa bile
    # sonuç listesine giremez.
    if excludes:
        items = [
            item
            for item in items
            if not any(path_is_excluded(path, excludes) for path in item.paths)
        ]

    # Aynı yolu kapsayan öğeleri ayıkla (ör. üst klasör + alt klasör).
    # Komut/çöp öğeleri fiziksel yol tüketmediği için bu elemeden muaftır.
    dedup_order = sorted(items, key=lambda i: (i.rule_id == "large-file", -i.size))
    kept: list[Item] = []
    covered: list[str] = []
    for item in dedup_order:
        if item.action in {"command", "empty_trash"}:
            kept.append(item)
            continue
        paths = item.paths
        if paths and all(any(p == c or p.startswith(c.rstrip("/") + "/") for c in covered) for p in paths):
            continue
        kept.append(item)
        covered.extend(paths)

    kept.sort(key=lambda i: (CATEGORIES.get(i.category, {}).get("order", 99), RISK_ORDER.get(i.risk, 9), -i.size))

    if stats is not None:
        stats.clear()
        stats.update(
            {
                "mode": mode,
                "workers": workers,
                "categories": list(categories) or ["all"],
                "items": len(kept),
                "elapsed": round(time.monotonic() - started, 3),
                "collectors": {
                    label: round(duration, 3)
                    for label, _items, duration in sorted(collected, key=lambda row: row[2], reverse=True)
                },
            }
        )
    return kept


# ---------------------------------------------------------------------------
# Temizlik
# ---------------------------------------------------------------------------


def clean_items(
    items_by_id: dict[str, Item],
    ids: list[str],
    mode: str = "delete",
    excludes=None,
) -> list[dict]:
    """Seçilen öğeleri temizler. Sonuç listesi döndürür.

    ``excludes`` verilirse bu yolların altındaki hiçbir öğe, tarama
    sonrasında ayarlar değişmiş olsa bile silinmez.
    """
    if mode not in {"delete", "trash"}:
        raise ValueError("Geçersiz mod")
    blocked = normalize_excludes(excludes or ())
    results: list[dict] = []
    for ident in ids:
        item = items_by_id.get(ident)
        if item is None:
            results.append({"id": ident, "title": ident, "status": "error", "error": "Öğe bulunamadı", "freed": 0})
            continue

        if blocked and any(path_is_excluded(path, blocked) for path in item.paths):
            results.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "status": "error",
                    "freed": 0,
                    "error": "Hariç tutulan yol: bu öğe silinmedi.",
                }
            )
            continue

        if item.action == "command":
            results.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "status": "needs_terminal",
                    "freed": 0,
                    "command": item.command,
                    "error": None,
                }
            )
            continue

        if item.action == "empty_trash":
            if blocked and path_is_excluded(TRASH_DIR / "files", blocked):
                results.append(
                    {
                        "id": item.id,
                        "title": item.title,
                        "status": "error",
                        "freed": 0,
                        "error": "Hariç tutulan yol: bu öğe silinmedi.",
                    }
                )
                continue
            if mode == "trash":
                results.append(
                    {
                        "id": item.id,
                        "title": item.title,
                        "status": "error",
                        "freed": 0,
                        "error": "Çöp kutusunu boşaltmak kalıcıdır; bu işlem için 'Kalıcı sil' modunu seçin.",
                    }
                )
                continue
            freed, count = empty_trash()
            results.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "status": "deleted",
                    "freed": freed,
                    "error": None,
                    "meta": {"items": count},
                }
            )
            continue

        freed = 0
        errors: list[str] = []
        deleted_paths = 0
        for raw in item.paths:
            path = Path(raw)
            try:
                if mode == "trash":
                    freed += move_to_trash(path)
                else:
                    freed += delete_permanently(path)
                deleted_paths += 1
            except SafetyError as exc:
                errors.append(str(exc))
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        status = "deleted" if not errors else ("partial" if deleted_paths else "error")
        if mode == "trash" and status == "deleted":
            status = "trashed"
        results.append(
            {
                "id": item.id,
                "title": item.title,
                "status": status,
                "freed": freed,
                "error": "; ".join(errors) if errors else None,
            }
        )
    return results


def append_history(entry: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_history(limit: int = 20) -> list[dict]:
    if not HISTORY_FILE.is_file():
        return []
    entries: list[dict] = []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries[-limit:][::-1]


def system_report() -> dict:
    code, out, _ = _run(["btrfs", "filesystem", "usage", "/"], timeout=15)
    btrfs = out if code == 0 else ""
    snapshots: list[str] = []
    code, out, _ = _run(["btrfs", "subvolume", "list", "/"], timeout=15)
    if code == 0:
        snapshots = [line for line in out.splitlines() if line.strip()][:20]
    return {
        "version": VERSION,
        "home": str(HOME),
        "user": os.environ.get("USER", ""),
        "euid": os.geteuid(),
        "disk": disk_info(),
        "btrfs_usage": btrfs,
        "snapshots": snapshots,
        "os": _os_name(),
        "kernel": os.uname().release,
        "has_paccache": bool(shutil.which("paccache")),
        "has_journalctl": bool(shutil.which("journalctl")),
        "has_pacman": bool(shutil.which("pacman")),
    }


def performance_report() -> dict:
    """Read-only health/boot diagnostics; this function never changes system settings."""
    mem: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            match = re.match(r"^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+)", line)
            if match:
                mem[match.group(1)] = int(match.group(2)) * 1024
    except OSError:
        pass
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    try:
        load = list(os.getloadavg())
    except OSError:
        load = []
    uptime_seconds = 0
    try:
        uptime_seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        pass

    _, boot_time, boot_err = _run(["systemd-analyze", "time"], timeout=15)
    if not boot_time:
        boot_time = boot_err
    _, blame_out, _ = _run(["systemd-analyze", "blame"], timeout=20)
    _, unit_out, _ = _run(
        ["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-pager", "--no-legend"],
        timeout=20,
    )
    enabled_units = []
    for line in unit_out.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".service"):
            enabled_units.append(parts[0])

    _, profile, _ = _run(["powerprofilesctl", "get"], timeout=8)
    _, governor_out, _ = _run(["cpupower", "frequency-info", "-p"], timeout=8)
    gov_match = re.search(r"The governor \"([^\"]+)\"", governor_out)
    _, trim_enabled, _ = _run(["systemctl", "is-enabled", "fstrim.timer"], timeout=8)
    _, trim_active, _ = _run(["systemctl", "is-active", "fstrim.timer"], timeout=8)
    _, discard_out, _ = _run(["lsblk", "-D", "-o", "NAME,ROTA,DISC-MAX", "--noheadings"], timeout=10)
    discard_lines = [line.strip() for line in discard_out.splitlines() if line.strip()]

    try:
        root_source = os.path.realpath(subprocess.check_output(["findmnt", "-nro", "SOURCE", "/"], text=True, timeout=5).strip())
    except (OSError, subprocess.SubprocessError):
        root_source = ""
    root_device = Path(root_source.split("[", 1)[0]).name
    root_path = root_source.split("[", 1)[0]
    _, root_disc_out, _ = _run(["lsblk", "-ndo", "ROTA,DISC-MAX", root_path], timeout=8) if root_path.startswith("/dev/") else (127, "", "")
    root_disc = root_disc_out.strip().split()
    root_is_ssd = bool(root_disc and root_disc[0] == "0")
    trim_supported = bool(root_disc and len(root_disc) > 1 and root_disc[1] not in {"0B", "0"})

    return {
        "memory_total": total,
        "memory_available": available,
        "memory_used": max(0, total - available),
        "memory_percent": round((total - available) * 100 / total, 1) if total else 0,
        "swap_total": swap_total,
        "swap_used": max(0, swap_total - swap_free),
        "load": load,
        "uptime_seconds": uptime_seconds,
        "boot_time": boot_time.strip(),
        "boot_blame": [line.strip() for line in blame_out.splitlines() if line.strip()][:12],
        "enabled_units": enabled_units,
        "power_profile": profile.strip() or "bilinmiyor",
        "cpu_governor": gov_match.group(1) if gov_match else "bilinmiyor",
        "trim_enabled": trim_enabled.strip(),
        "trim_active": trim_active.strip(),
        "root_is_ssd": root_is_ssd,
        "trim_supported": trim_supported,
        "root_device": root_source,
        "discard_devices": discard_lines[:12],
        "autostart": list_user_autostart(),
    }


def community_support_report() -> dict:
    """Build an explicitly shareable diagnostics report with identifying data omitted.

    Never includes usernames, hostnames, home paths, disk identifiers, file paths,
    package names, autostart commands, or service names.
    """
    distro: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"ID", "VERSION_ID", "ID_LIKE"}:
                distro[key.lower()] = value.strip().strip('"').replace('\\"', '"')
    except OSError:
        pass
    disk = disk_info()
    performance = performance_report()
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "privacy": {
            "redacted": True,
            "omitted": ["username", "hostname", "home paths", "disk identifiers", "file paths", "package names", "service names", "autostart commands"],
        },
        "software": {
            "temizci": VERSION,
            "distro": distro,
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "desktop": _desktop_family(),
        },
        "storage": {
            "total_bytes": disk.get("total", 0),
            "free_bytes": disk.get("free", 0),
            "used_percent": disk.get("percent", 0),
            "filesystem_type": _root_filesystem_type(),
        },
        "performance": {
            "memory_total_bytes": performance["memory_total"],
            "memory_available_bytes": performance["memory_available"],
            "memory_used_percent": performance["memory_percent"],
            "swap_total_bytes": performance["swap_total"],
            "swap_used_bytes": performance["swap_used"],
            "load_average": performance["load"],
            "boot_summary": _redact_boot_summary(performance["boot_time"]),
            "power_profile": performance["power_profile"],
            "cpu_governor": performance["cpu_governor"],
            "root_is_ssd": performance["root_is_ssd"],
            "trim_supported": performance["trim_supported"],
            "trim_enabled": performance["trim_enabled"],
            "enabled_service_count": len(performance["enabled_units"]),
        },
        "available_tools": {
            name: bool(shutil.which(name))
            for name in ("pacman", "paccache", "journalctl", "systemd-analyze", "powerprofilesctl", "fstrim")
        },
    }


def _desktop_family() -> str:
    candidates = " ".join(
        os.environ.get(key, "") for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
    ).casefold()
    for key, label in (("kde", "KDE Plasma"), ("gnome", "GNOME"), ("xfce", "Xfce"), ("cinnamon", "Cinnamon"), ("lxqt", "LXQt"), ("mate", "MATE"), ("sway", "Sway"), ("hyprland", "Hyprland"), ("wayfire", "Wayfire")):
        if key in candidates:
            return label
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland (bilinmeyen masaüstü)"
    if os.environ.get("DISPLAY"):
        return "X11 (bilinmeyen masaüstü)"
    return "Bilinmiyor"


def _root_filesystem_type() -> str:
    code, output, _ = _run(["findmnt", "-nro", "FSTYPE", "/"], timeout=5)
    value = output.strip().splitlines()[0] if code == 0 and output.strip() else "bilinmiyor"
    return value if re.fullmatch(r"[A-Za-z0-9_.+-]{1,40}", value) else "bilinmiyor"


def _redact_boot_summary(value: str) -> str:
    """Keep timing measurements only; systemd output can include host-specific data."""
    component = r"([0-9]+(?:\.[0-9]+)?\s*(?:ms|s|min)\s*\((?:kernel|initrd|userspace|firmware|loader)\))"
    match = re.search(
        rf"Startup finished in\s+{component}\s*\+\s*{component}\s*\+\s*"
        rf"{component}\s*=\s*([0-9]+(?:\.[0-9]+)?\s*(?:ms|s|min))",
        value,
        flags=re.IGNORECASE,
    )
    return f"{match.group(1)} + {match.group(2)} + {match.group(3)} = {match.group(4)}" if match else "ölçülemedi"


def write_community_support_report(path: str | Path, report: dict | None = None) -> Path:
    """Write a redacted diagnostics JSON report to a user-selected destination."""
    destination = Path(path).expanduser()
    if destination.exists() and destination.is_dir():
        raise ValueError("Rapor hedefi bir klasör olamaz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report if report is not None else community_support_report(), ensure_ascii=False, indent=2) + "\n"
    destination.write_text(payload, encoding="utf-8")
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return destination


def _os_name() -> str:
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return os.uname().sysname
