# Temizci

CachyOS ve Arch tabanlı dağıtımlar için **güvenli**, **yerel** bakım yardımcısı.
Önbellekleri, eski tarayıcı yedeklerini, geliştirici artıklarını ve büyük dosyaları
bulur; neyin silineceğini önce gösterir, sonra onayınızla temizler.

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
* **Manuel:** otomatik seçim yapmaz. Risk filtresi, arama ve boyuta göre sıralama kullanılabilir.
* **Ayarlar:** varsayılan çöp kutusu/kalıcı sil tercihi, büyük dosya eşiği, başlangıç taraması ve aralıkla tarama.
* **Dil:** Ayarlar → Dil bölümünden Türkçe veya English seç; değişiklik uygulamaya anında yansır ve kaydedilir.
* **Geçmiş / Çöp kutusu:** önceki işlemleri gösterir veya XDG çöp klasörünü açar.
* **Uygulamalar ve paketler:** Pacman envanterini, kurulu boyutları ve bağımlılık ilişkilerini gösterir. Kaldırma öncesi Pacman'ın `-Rsp --print-format` salt okunur planı incelenir; sonrasında komut terminalde açılır ve Pacman'ın kendi onayı da gerekir.
* **Hız ve başlangıç:** RAM/swap, yük, açılışta en uzun süren systemd birimleri, TRIM ve güç profilini ölçer. Kullanıcı autostart girdileri silinmeden devre dışı bırakılıp geri yüklenebilir.
* **Tanı raporu:** Topluluk desteği için dağıtım, disk/RAM ölçümleri ve araç durumlarını dışa aktarır. Kullanıcı adı, bilgisayar adı, ev dizini, disk kimliği, dosya yolu, paket adı, servis adı ve başlangıç komutları dahil edilmez; paylaşmadan önce raporu yine de inceleyin.

Aralıklı tarama yalnızca GUI açıkken çalışır ve **dosyaları otomatik silmez**.
Temizleme için her zaman ayrı onay gerekir; riskli öğeler otomatik seçilmez.
Paket listesi hiçbir paketin “kullanılmıyor” olduğunu varsaymaz; 5 artık bağımlılık
gibi Pacman'ın işaretlediği adaylar da otomatik kaldırılmaz. Sistem servisleri
yalnızca raporlanır; ağ, Bluetooth ve masaüstü servisleri kendiliğinden kapatılmaz.

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

temizci clean              # yalnızca önizleme (hiçbir şey silmez)
temizci clean --yes        # güvenli öğeleri kalıcı sil
temizci clean --trash --yes        # güvenlileri çöpe taşı
temizci clean --include-risky      # risklileri de önizlemeye kat
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
├── assets/temizci.svg
├── .github/workflows/test.yml
└── install.sh
```

Yeni bir temizlik kuralı eklemek için `core.py` içinde bir `collect_*` fonksiyonu
yazıp `COLLECTORS` listesine ekleyin. Kural, `_make_item(...)` ile öğe üretmeli;
risk seviyesini ve varsayılan seçimi açıkça belirtmelidir.

Katkı ilkeleri için [CONTRIBUTING.md](CONTRIBUTING.md), güvenlik bildirimi için
[SECURITY.md](SECURITY.md), İngilizce dokümantasyon için [README.en.md](README.en.md)
dosyasına bakın. Pull request'lerde CI birim testlerini, Python derlemesini ve
web JavaScript sözdizimini denetler.

## Kaldırma

```bash
rm -f ~/.local/bin/temizci \
      ~/.local/share/applications/temizci.desktop \
      ~/.local/share/icons/hicolor/scalable/apps/temizci.svg
rm -rf ~/.local/state/temizci
```
