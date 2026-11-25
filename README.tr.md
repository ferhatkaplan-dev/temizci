# Temizci — Arch Linux Disk Temizleyici ve Sistem Bakımı

**[English documentation](README.md)**

Arch Linux, CachyOS ve Arch tabanlı dağıtımlar için ücretsiz, açık kaynaklı bir
**disk temizleyici ve sistem bakım uygulaması**. Uygulama/tarayıcı önbelleklerini,
eski yedekleri, geliştirici artıklarını, büyük dosyaları ve Pacman paket
adaylarını bulur. Gizlilik odaklı ve yerel çalışır: temizlenecek öğeleri önce
gösterir, yalnızca açık onayınızdan sonra işlem yapar; dosyaları, paketleri veya
sistem servislerini sessizce silmez/kapatmaz.

[![Tests](https://github.com/ferhatkaplan-dev/temizci/actions/workflows/test.yml/badge.svg)](https://github.com/ferhatkaplan-dev/temizci/actions/workflows/test.yml)
[![MIT License](https://img.shields.io/github/license/ferhatkaplan-dev/temizci)](LICENSE)

**Arch Linux · CachyOS · Pacman · Linux disk temizliği · Python · PySide6**

```
┌──────────────────────────────────────────────────────────────┐
│  Temizci            CachyOS · çekirdek 7.3.3 · 29,4 GB boş  │
│                                                              │
│  ● %74 dolu       Seçili temizlik    Güvenli kazanç         │
│                   ███ 12,8 GB        ███ 5,4 GB             │
└──────────────────────────────────────────────────────────────┘
```

## Neleri temizler?

| Kategori | Örnekler | Varsayılan |
|---|---|---|
| Sistem | Pacman paket önbelleği, systemd günlükleri, artık paketler | Seçili değil (sudo) |
| Uygulama önbellekleri | `~/.cache/*`, pip, npm, paru, Mesa, küçük resimler | Güvenliler seçili |
| Tarayıcılar | Zen, Chrome, Edge, Firefox, OpenChamber / Electron önbellekleri | Güvenli |
| Geliştirici | npm `_cacache`, Cargo registry, `node_modules` | Kısmen |
| Eski yedekler | Zen `*-backup*`, `*-old-profile-*`, çökme kurtarma arşivleri | Seçili değil (riskli) |
| Büyük dosyalar | 150 MB üzeri dosyalar (İndirilenler, Masaüstü, Videolar…) | Seçili değil |
| Çöp kutusu | XDG çöp kutusu | Seçili değil |
| Yazılım paketleri | Kullanıcı tarafından kurulmuş paketler ve Pacman artık bağımlılıkları | Hiçbiri seçili değil |
| Hız / başlangıç | RAM, swap, açılış süresi, etkin servisler ve kullanıcı autostart'ı | Ölçüm salt okunur |

Her öğe **güvenli / dikkat / riskli** olarak işaretlenir. Riskli öğeler asla
kendiliğinden seçilmez.

## Kurulum

Python 3.11+ ve yerel pencere arayüzü için PySide6 gerekir. PySide6 bu sistemde
kurulu. Başka bir Arch tabanlı kurulumda `sudo pacman -S pyside6` ile kurabilirsin.

```bash
cd ~/Projects/temizci
./install.sh          # komutu ve uygulama menüsü kısayolunu kur
temizci gui           # yerel masaüstü penceresini aç
```

Kurulum yapmadan da çalışır:

```bash
./temizci gui
python3 -m temizci_app gui
```

## Kullanım

### Yerel masaüstü GUI

Uygulama menüsünden **Temizci**'yi aç veya `temizci gui` çalıştır. Bu PySide6/Qt
penceresidir; tarayıcı açmaz ve yerel HTTP sunucusu başlatmaz.

GUI'deki iş akışları:

* **Önerilen:** yalnızca güvenli ve kapalı uygulamaların öğelerini seçer.
* **Derin inceleme:** güvenli ve dikkat öğelerini seçer; açık uygulamaları ve riskli yedekleri atlar.
* **Düşük disk alanı:** güvenli/dikkat önbelleklerini seçer; kişisel büyük dosya ve yedekleri dışarıda bırakır.
* **Geliştirici:** uygulama, tarayıcı ve geliştirici önbelleklerini seçer; kişisel dosya, yedek ve büyük dosyalara dokunmaz.
* **Oyun ve grafik:** shader, tarayıcı ve uygulama önbelleklerini seçer; oyun dosyalarına ve projelere dokunmaz.
* **Gizlilik:** tarayıcı ve uygulama önbelleklerini seçer; kişisel dosya ve yedekleri kapsam dışı bırakır.
* **Manuel:** otomatik seçim yapmaz. Risk filtresi, arama ve boyuta göre sıralama kullanılabilir.
* **Ayarlar:** varsayılan çöp kutusu/kalıcı sil tercihi, tarama modu, paralel işçi sayısı, büyük dosya eşiği, kategori kapsamı, hariç tutulan yollar, başlangıç taraması ve aralıkla tarama.
* **Dil:** Ayarlar → Dil bölümünden Türkçe veya English seç; değişiklik uygulamaya anında yansır ve kaydedilir.
* **Geçmiş / Çöp kutusu:** önceki işlemleri gösterir veya XDG çöp klasörünü açar.
* **Uygulamalar ve paketler:** Pacman envanterini, kurulu boyutları ve bağımlılık ilişkilerini gösterir. Kaldırma öncesi Pacman'ın `-Rsp --print-format` salt okunur planı incelenir; sonrasında komut terminalde açılır ve Pacman'ın kendi onayı da gerekir.
* **Hız ve başlangıç:** RAM/swap, yük, açılışta en uzun süren systemd birimleri, TRIM ve güç profilini ölçer. Dengeli / Performans / Pil tasarrufu güç iş akışını açık onayla uygular ve önceki profile dönmeyi sunar. Kullanıcı autostart girdileri silinmeden devre dışı bırakılıp geri yüklenebilir.
* **Tanı raporu:** Topluluk desteği için dağıtım, disk/RAM ölçümleri ve araç durumlarını dışa aktarır. Kullanıcı adı, bilgisayar adı, ev dizini, disk kimliği, dosya yolu, paket adı, servis adı ve başlangıç komutları dahil edilmez; paylaşmadan önce raporu yine de inceleyin.

### Performans ve gelişmiş tarama

Temizci taramayı hızlandırmak için üç mod ve isteğe bağlı kapsam ayarları sunar:

| Ayar | Ne yapar |
|---|---|
| **Dengeli** | Tüm kategorileri tarar; günlük kullanım için varsayılan. |
| **Hızlı** | Büyük dosya keşfini atlar; ilk sonuçlar daha hızlı gelir. |
| **Kapsamlı** | Varsayılan 40 yerine en fazla 100 büyük dosya sonucunu listeler. |
| **Paralel işçi** | Bağımsız tarama adımlarını eşzamanlı çalıştırır. 2 önerilir; bazı disklerde daha yüksek değerler yavaşlatabilir. |
| **Kategoriler** | Yalnızca seçilen kategorileri tarar (ör. sadece tarayıcı önbellekleri). |
| **Hariç tutulan yollar** | Belirtilen dizinler ne taranır ne de temizlenir; ayar temizlik anında da doğrulanır. |

Tarama sırasında ilk bulunan öğeler beklemeden listelenir, ilerleme çubuğu ve
tamamlanma süresi gösterilir. Tarama hâlâ tek tek dosya silmez; hız ayarları
yalnızca keşif kapsamını değiştirir.

```bash
temizci presets                              # iş akışı profillerini listele
temizci scan --mode fast --workers 2         # hızlı tarama
temizci scan --category browsers --stats     # yalnızca tarayıcılar + süre dağılımı
temizci scan --exclude ~/Projects --json     # projeleri hariç tut
temizci clean --preset developer             # yalnızca önizleme
temizci clean --preset gaming --trash --yes  # seçili profili çöpe taşı
```

`--stats` süreleri ve en yavaş koleksiyoncuları `stderr`'e yazar; JSON çıktısını
bozmaz. Hariç tutulan bir yol tarama sonrasında ayarlara eklense bile temizlik
sırasında ikinci kez kontrol edilir ve silinmez.

Aralıklı tarama yalnızca GUI açıkken çalışır ve **dosyaları otomatik silmez**.
Temizleme için her zaman ayrı onay gerekir; riskli öğeler otomatik seçilmez.
Paket listesi hiçbir paketin “kullanılmıyor” olduğunu varsaymaz; 5 artık bağımlılık
gibi Pacman'ın işaretlediği adaylar da otomatik kaldırılmaz. Sistem servisleri
yalnızca raporlanır; ağ, Bluetooth ve masaüstü servisleri kendiliğinden kapatılmaz.

### Bilgisayar performansı için güvenli iş akışları

**Hız ve başlangıç** sekmesi ölçümlere göre üç güç profilini sunar:

* **Dengeli:** günlük kullanım için önerilen tepki ve enerji dengesi.
* **Performans:** ağır işlerde işlemci tepkisini artırabilir; daha çok güç, ısı ve fan sesi oluşturabilir. Pilde varsayılan olarak önerilmez.
* **Pil tasarrufu:** tüketimi, ısıyı ve fan sesini azaltabilir; yoğun işlerde daha yavaş olabilir.

Profil değişimi sistemin desteklediği seçeneklerle sınırlıdır, açık onay ister
ve önceki profil için **geri dön** seçeneği saklar. `powerprofilesctl` kullanıcı
oturumunda çalışır; Temizci sudo çalıştırmaz. Masaüstü yetkilendirme ilkesi ayrıca
izin sorabilir. Güç profilleri işlemciyi her koşulda hızlandırma garantisi vermez;
gerçek etki donanıma ve iş yüküne bağlıdır.

Başlangıç uygulamaları kullanıcı tarafından tek tek seçilir ve geri alınabilir
şekilde devre dışı bırakılır. Sistem servisleri otomatik kapatılmaz. SSD TRIM
zamanlayıcısı yalnızca destekli disklerde sunulur; bu depolama bakımıdır, işlemci
hızlandırma ayarı değildir. Depolama doluluğunu azaltmak güncelleme ve uygulama
alanı sağlayabilir ancak RAM/CPU darboğazını çözmez.

### İsteğe bağlı web arayüzü

```bash
temizci ui                 # http://127.0.0.1:8765 adresinde açar
temizci ui --port 9000     # farklı port
temizci ui --no-browser    # tarayıcıyı otomatik açma
```

Arayüz yalnızca `127.0.0.1` üzerinde dinler, dışarıya açılmaz. Her oturum için
rastgele bir CSRF anahtarı üretir.

### Komut satırı

```bash
temizci doctor             # sistem + disk + btrfs özeti
temizci support-report     # gizliliği azaltılmış destek raporu (JSON)
temizci support-report -o rapor.json
temizci scan               # neler silinebilir, boyutlarıyla listele
temizci scan --json        # makine okunabilir çıktı
temizci scan --mode fast --workers 2 --stats
temizci scan --category caches --exclude ~/Projects
temizci presets            # iş akışı profilleri ve kapsamları

temizci clean              # yalnızca önizleme (hiçbir şey silmez)
temizci clean --yes        # güvenli öğeleri kalıcı sil
temizci clean --trash --yes        # güvenlileri çöpe taşı
temizci clean --include-risky      # risklileri de önizlemeye kat
temizci clean --preset developer   # profil tabanlı önizleme
temizci clean --ids "id1,id2" --yes
```

`clean` varsayılan olarak **kuru çalışmadır**; `--yes` olmadan hiçbir dosya
silinmez. `sudo` gerektiren işler komut olarak yazdırılır, çalıştırılmaz.

## Güvenlik modeli

1. **Rastgele yol silinemez.** Yalnızca tarama kurallarının bulduğu öğeler GUI veya
   API üzerinden seçilebilir.
2. **İzinli kökler.** Silme yalnızca ev dizini, `/tmp`, `/var/tmp`,
   `/var/cache/pacman/pkg` ve `/var/log` altında yapılır.
3. **Korunan yollar.** Ev dizini, `~/.config`, `~/.local`, `~/.ssh`, `~/.gnupg`,
   Belgeler/Masaüstü/İndirilenler/Videolar/Projeler kökleri, **aktif Zen profili**
   ve çöp kutusunun kendisi silinemez. Bir korunan yolun üst dizini de silinemez.
4. **Sembolik bağlantı takibi yok.** Bağlantı silinirse yalnızca bağlantı dosyası
   kaldırılır; hedefi korunur.
5. **Bağlama noktaları** reddedilir.
6. **İki aşamalı onay.** Önizleme + onay kutusu olmadan temizlik başlamaz.
7. **Geri alınabilir mod.** Kalıcı silme yerine XDG çöp kutusuna taşıma seçilebilir.
8. **sudo yok.** Pacman/journald/artık paket işleri uygulama içinde çalıştırılmaz;
   `foot` (veya alacritty/ghostty/konsole/xterm) terminalinde açılır. Parolayı siz
   girersiniz, komutu görürsünüz.

> **Btrfs notu:** Snapshot varsa silinen dosyaların alanı hemen açılmayabilir.
> Temizci snapshotları kendiliğinden silmez; yalnızca uyarır.

## Nerede durum tutar?

* İşlem geçmişi: `~/.local/state/temizci/history.jsonl`
* Çöpe taşıma: standart XDG çöp kutusu (`~/.local/share/Trash`)

## Geliştirme

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile temizci_app/*.py
```

Proje yapısı:

```
temizci
├── temizci                  # başlatıcı
├── temizci_app/
│   ├── core.py              # kurallar, boyut, güvenlik, silme
│   ├── desktop.py           # PySide6 yerel masaüstü GUI
│   ├── server.py            # 127.0.0.1 HTTP API
│   ├── cli.py               # gui / scan / clean / doctor / ui
│   └── web/                 # bağımlılıksız arayüz (HTML/CSS/JS)
├── tests/test_safety.py
├── docs/PERFORMANCE.md       # tarama performansı ve ayarları
├── assets/temizci.svg
├── .github/workflows/test.yml
└── install.sh
```

Yeni bir temizlik kuralı eklemek için `core.py` içinde bir `collect_*` fonksiyonu
yazıp `COLLECTORS` listesine ekleyin. Kural, `_make_item(...)` ile öğe üretmeli;
risk seviyesini ve varsayılan seçimi açıkça belirtmelidir.

Katkı ilkeleri için [CONTRIBUTING.md](CONTRIBUTING.md), güvenlik bildirimi için
[SECURITY.md](SECURITY.md), İngilizce dokümantasyon için [README.md](README.md)
dosyasına bakın. Pull request'lerde CI birim testlerini, Python derlemesini ve
web JavaScript sözdizimini denetler.

## Kaldırma

```bash
rm -f ~/.local/bin/temizci \
      ~/.local/share/applications/temizci.desktop \
      ~/.local/share/icons/hicolor/scalable/apps/temizci.svg
rm -rf ~/.local/state/temizci
```
