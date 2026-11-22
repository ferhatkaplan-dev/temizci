/* Temizci — yerel web arayüzü (bağımlılıksız) */
"use strict";

const TOKEN = document.querySelector('meta[name="temizci-token"]').content;
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  data: null,
  selected: new Set(),
  filter: "all",
  query: "",
  onlySelected: false,
  mode: "delete",
  modalIds: [],
  selectionKey: null,
  pollTimer: null,
  polling: false,
  lastCleanMode: "delete",
  booted: false,
};

const RISK_LABELS = { safe: "güvenli", caution: "dikkat", risky: "riskli" };
const STATUS_LABELS = {
  deleted: "Silindi",
  trashed: "Çöpe taşındı",
  needs_terminal: "Terminal bekliyor",
  partial: "Kısmen silindi",
  error: "Hata",
};

const CATEGORY_ICONS = {
  cpu: '<rect x="4" y="4" width="16" height="16" rx="3"></rect><rect x="9" y="9" width="6" height="6"></rect><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"></path>',
  layers: '<path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 12l10 5 10-5"></path><path d="M2 17l10 5 10-5"></path>',
  globe: '<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18"></path><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"></path>',
  terminal: '<rect x="2" y="4" width="20" height="16" rx="3"></rect><path d="M7 9l3 3-3 3M13 15h4"></path>',
  archive: '<rect x="3" y="4" width="18" height="4" rx="1"></rect><path d="M5 8v12h14V8"></path><path d="M10 12h4"></path>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path><path d="M9 13h6M9 17h6"></path>',
  trash: '<path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M19 6l-1 14H6L5 6"></path><path d="M10 11v5M14 11v5"></path>',
};

const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });
const ni = new Intl.NumberFormat("tr-TR");

function fmtBytes(value) {
  let num = Number(value) || 0;
  if (num < 1024) return `${Math.round(num)} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let index = -1;
  do {
    num /= 1024;
    index += 1;
  } while (num >= 1024 && index < units.length - 1);
  return `${nf.format(num)} ${units[index]}`;
}

function fmtCount(value) {
  return ni.format(Number(value) || 0);
}

function fmtDate(seconds) {
  if (!seconds) return "—";
  try {
    return new Date(seconds * 1000).toLocaleDateString("tr-TR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function reclaimableTotal(items) {
  let physical = 0;
  const commands = new Map();
  for (const item of items) {
    if (item.action === "command") {
      const key = item.path || item.id;
      commands.set(key, Math.max(commands.get(key) || 0, item.size));
    } else {
      physical += item.size;
    }
  }
  return physical + Array.from(commands.values()).reduce((sum, value) => sum + value, 0);
}

function icon(name, size = 16) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${CATEGORY_ICONS[name] || CATEGORY_ICONS.file}</svg>`;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Temizci-Token": TOKEN,
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `İstek başarısız (HTTP ${response.status})`);
  }
  return payload;
}

function toast(message, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  $("#toasts").appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(6px)";
    node.style.transition = "opacity .25s, transform .25s";
    setTimeout(() => node.remove(), 260);
  }, 4200);
}

/* ------------------------------------------------------------------ veri */

async function refresh() {
  const data = await api("/api/state");
  applyState(data);
  return data;
}

function applyState(data) {
  const previous = state.data;
  state.data = data;

  if (data.phase === "ready" && data.scanned_at && data.scanned_at !== state.selectionKey) {
    state.selectionKey = data.scanned_at;
    state.selected = new Set(data.items.filter((item) => item.selected).map((item) => item.id));
  }

  if (previous && previous.phase === "scanning" && data.phase === "ready") {
    const count = data.items.length;
    toast(count ? `${count} temizlik öğesi bulundu.` : "Temizlenecek yeni bir şey bulunamadı.", "success");
  }

  if (previous && previous.phase === "cleaning" && data.phase === "ready") {
    state.selected.clear();
    showResults();
  }

  const existing = new Set(data.items.map((item) => item.id));
  for (const id of Array.from(state.selected)) {
    if (!existing.has(id)) state.selected.delete(id);
  }

  render();
  updateOverlay();
}

function schedulePoll(delay = 1200) {
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(poll, delay);
}

async function poll() {
  if (state.polling) return;
  state.polling = true;
  try {
    const data = await refresh();
    schedulePoll(["scanning", "cleaning"].includes(data.phase) ? 550 : 4000);
  } catch {
    schedulePoll(2500);
  } finally {
    state.polling = false;
  }
}

async function startScan() {
  try {
    state.selected.clear();
    await api("/api/scan", { method: "POST", body: JSON.stringify({}) });
    const data = await refresh();
    updateOverlay();
    schedulePoll(500);
    if (data.phase !== "scanning") toast("Tarama başlatılamadı.", "error");
  } catch (error) {
    toast(error.message, "error");
  }
}

/* --------------------------------------------------------------- görünüm */

function selectedItems() {
  if (!state.data) return [];
  return state.data.items.filter((item) => state.selected.has(item.id));
}

function render() {
  if (!state.data) return;
  renderHeader();
  renderStats();
  renderNotice();
  renderContent();
  renderFooter();
}

function renderHeader() {
  const { report, disk } = state.data;
  const os = report?.os || "Linux";
  const kernel = report?.kernel ? `çekirdek ${report.kernel}` : "";
  $("#sysline").textContent = `${os}${kernel ? " · " + kernel : ""} · ${fmtBytes(disk.free)} boş`;

  const percent = Math.max(0, Math.min(100, disk.percent || 0));
  $("#disk-percent").textContent = `${Math.round(percent)}%`;
  const circumference = 2 * Math.PI * 54;
  $("#ring-value").style.strokeDashoffset = String(circumference * (1 - percent / 100));
  $("#disk-bar").style.width = `${percent}%`;
  $("#disk-used").textContent = fmtBytes(disk.used);
  $("#disk-free").textContent = fmtBytes(disk.free);
  $("#disk-sub").textContent = `${fmtBytes(disk.used)} / ${fmtBytes(disk.total)} kullanılıyor`;
}

function renderStats() {
  const items = state.data.items;
  const selected = selectedItems();
  const total = state.data.total_reclaimable ?? reclaimableTotal(items);
  const safe = items
    .filter((item) => item.risk === "safe" && item.action === "delete")
    .reduce((sum, item) => sum + item.size, 0);
  const trash = items.find((item) => item.rule_id === "trash");
  const selectedSize = selected.reduce((sum, item) => sum + item.size, 0);
  const commandCount = selected.filter((item) => item.action === "command").length;

  $("#stat-selected").textContent = fmtBytes(selectedSize);
  $("#stat-selected-note").textContent = selected.length
    ? `${fmtCount(selected.length)} öğe${commandCount ? ` · ${commandCount} terminal komutu` : ""}`
    : "Henüz seçim yok";
  $("#stat-safe").textContent = fmtBytes(safe);
  $("#stat-total").textContent = fmtBytes(total);
  $("#stat-items").textContent = items.length
    ? `${fmtCount(items.length)} öğe · ${new Set(items.map((item) => item.category)).size} kategori`
    : "Tarama bekleniyor";
  $("#stat-trash").textContent = fmtBytes(trash ? trash.size : 0);
}

function renderNotice() {
  const { report, items } = state.data;
  const messages = [];
  if (report?.euid === 0) {
    messages.push("<b>root</b> olarak çalışıyorsunuz. Temizci'yi normal kullanıcı olarak çalıştırmanız önerilir.");
  }
  if (report?.snapshots?.length) {
    messages.push(
      `<b>${report.snapshots.length} btrfs snapshot</b> algılandı. Silinen dosyaların alanı hemen açılmayabilir.`
    );
  }
  const running = items
    .filter((item) => item.meta && item.meta.running)
    .map((item) => item.meta.app || item.meta.cache_name || item.title);
  if (running.length) {
    messages.push(`<b>${escapeHtml(running.join(", "))}</b> açık. Önbelleğini temizlemeden önce kapatmanız önerilir.`);
  }
  const selectedCommands = selectedItems().filter((item) => item.action === "command");
  if (selectedCommands.length) {
    messages.push(
      `${selectedCommands.length} seçili iş <b>terminalde</b> çalıştırılacak; uygulama sudo komutlarını kendisi çalıştırmaz.`
    );
  }
  const node = $("#notice");
  if (!messages.length) {
    node.classList.add("hidden");
    return;
  }
  node.classList.remove("hidden");
  $("#notice-text").innerHTML = messages.join("<br>");
}

function matchesFilters(item) {
  if (state.onlySelected && !state.selected.has(item.id)) return false;
  if (state.filter !== "all" && item.risk !== state.filter) return false;
  if (state.query) {
    const haystack = `${item.title} ${item.detail} ${item.path || ""} ${item.command || ""}`.toLocaleLowerCase("tr-TR");
    if (!haystack.includes(state.query)) return false;
  }
  return true;
}

function renderContent() {
  const content = $("#content");
  const empty = $("#empty");
  const data = state.data;
  const categories = Object.entries(data.categories).sort((a, b) => a[1].order - b[1].order);
  const selectedSet = state.selected;

  if (data.phase === "scanning" && !data.items.length) {
    content.innerHTML = "";
    empty.classList.add("hidden");
    return;
  }

  let html = "";
  let visibleCount = 0;

  for (const [key, meta] of categories) {
    const items = data.items.filter((item) => item.category === key && matchesFilters(item));
    if (!items.length) continue;
    visibleCount += items.length;
    const total = reclaimableTotal(items);
    const maxSize = Math.max(...items.map((item) => item.size), 1);

    html += `<section class="category">
      <div class="category-head">
        <div class="cat-icon">${icon(meta.icon)}</div>
        <h2>${escapeHtml(meta.title)}</h2>
        <div class="cat-line"></div>
        <div class="cat-total">${items.length} öğe · ${fmtBytes(total)}</div>
      </div>
      <div class="items">${items.map((item) => renderItem(item, maxSize, selectedSet)).join("")}</div>
    </section>`;
  }

  content.innerHTML = html;

  const ready = data.phase === "ready";
  if (!visibleCount) {
    empty.classList.toggle("hidden", !ready);
    if (ready) {
      const filtered = Boolean(state.query || state.filter !== "all" || state.onlySelected);
      $("#empty-title").textContent = filtered ? "Bu filtreye uygun öğe yok" : "Sistem tertemiz görünüyor";
      $("#empty-text").textContent = filtered
        ? "Arama veya risk filtresini değiştirip yeniden deneyin."
        : "Silinecek önbellek, eski yedek veya büyük dosya bulunamadı. Disk alanınız olduğu gibi kalıyor.";
    }
  } else {
    empty.classList.add("hidden");
  }
}

function renderItem(item, maxSize, selectedSet) {
  const checked = selectedSet.has(item.id);
  const risk = RISK_LABELS[item.risk] || item.risk;
  const isCommand = item.action === "command";
  const date = item.last_modified ? fmtDate(item.last_modified) : isCommand ? "sudo" : "—";
  const sizeLabel = isCommand ? "tahmini" : `${fmtCount(item.files)} dosya`;
  const barWidth = Math.max(2, Math.min(100, (item.size / maxSize) * 100));

  const chips = [`<span class="chip-risk ${item.risk}">${risk}</span>`];
  if (item.requires_root) chips.push('<span class="chip-meta blue">sudo</span>');
  if (item.meta?.running) chips.push('<span class="chip-meta">açık</span>');
  if (item.meta?.count) chips.push(`<span class="chip-meta">${item.meta.count} paket</span>`);
  if (item.meta?.kind === "large-file") chips.push('<span class="chip-meta">dosya</span>');

  const commandBlock = isCommand
    ? `<div class="command-block">
        <code title="${escapeHtml(item.command || "")}">${escapeHtml(item.command || "")}</code>
        <button class="btn tiny" type="button" data-terminal="${escapeHtml(item.command || "")}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9l3 3-3 3M13 15h4"></path></svg>
          Terminalde aç
        </button>
      </div>`
    : "";

  return `<article class="item ${checked ? "selected" : ""} ${isCommand ? "is-command" : ""}" data-id="${item.id}">
    <input class="cb" type="checkbox" ${checked ? "checked" : ""} aria-label="${escapeHtml(item.title)} seç">
    <div class="item-main">
      <div class="item-title">${escapeHtml(item.title)} ${chips.join(" ")}</div>
      <div class="item-detail">${escapeHtml(item.detail)}</div>
      ${item.path ? `<div class="item-path" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</div>` : ""}
    </div>
    <div class="item-meta-col">
      <span class="item-date">${date}</span>
    </div>
    <div class="item-side">
      <strong>${fmtBytes(item.size)}</strong>
      <span>${sizeLabel}</span>
      <div class="size-bar"><i style="width:${barWidth}%"></i></div>
    </div>
    ${commandBlock}
  </article>`;
}

function renderFooter() {
  const selected = selectedItems();
  const size = selected.reduce((sum, item) => sum + item.size, 0);
  $("#foot-count").textContent = `${fmtCount(selected.length)} öğe seçildi`;
  $("#foot-size").textContent = fmtBytes(size);
  const ready = state.data?.phase === "ready";
  $("#btn-clean").disabled = !ready || selected.length === 0;
  $("#btn-clear").disabled = selected.length === 0;
}

function updateOverlay() {
  const data = state.data;
  const overlay = $("#scan-overlay");
  if (!data) return;
  if (data.phase === "scanning" || data.phase === "cleaning") {
    overlay.classList.remove("hidden");
    const cleaning = data.phase === "cleaning";
    $("#scan-title").textContent = cleaning ? "Temizleniyor" : "Sistem taranıyor";
    $("#scan-label").textContent = data.progress.label || (cleaning ? "Dosyalar kaldırılıyor…" : "Önbellekler inceleniyor…");
    const total = Math.max(1, data.progress.total || 1);
    const done = Math.min(total, data.progress.done || 0);
    const percent = Math.max(4, Math.round((done / total) * 100));
    $("#scan-progress").style.width = `${percent}%`;
    $("#scan-meta").textContent = `${done} / ${total}`;
  } else {
    overlay.classList.add("hidden");
  }
}

/* ---------------------------------------------------------------- seçim */

function toggleItem(id, force) {
  if (force === undefined) {
    if (state.selected.has(id)) state.selected.delete(id);
    else state.selected.add(id);
  } else if (force) {
    state.selected.add(id);
  } else {
    state.selected.delete(id);
  }
  render();
}

function setFilter(filter) {
  state.filter = filter;
  $$("#filters .chip").forEach((chip) => chip.classList.toggle("active", chip.dataset.filter === filter));
  renderContent();
}

/* --------------------------------------------------------------- modal */

function openCleanModal() {
  const items = selectedItems();
  if (!items.length) return;
  state.modalIds = items.map((item) => item.id);
  state.mode = "delete";

  const total = items.reduce((sum, item) => sum + item.size, 0);
  const risky = items.filter((item) => item.risk === "risky");
  const commands = items.filter((item) => item.action === "command");
  const shown = items.slice(0, 80);

  $("#confirm-list").innerHTML =
    shown
      .map(
        (item) => `<div class="confirm-row">
          <span>${escapeHtml(item.title)}</span>
          <b>${fmtBytes(item.size)}</b>
        </div>`
      )
      .join("") +
    (items.length > shown.length
      ? `<div class="confirm-row"><span>… ve ${items.length - shown.length} öğe daha</span><b></b></div>`
      : "");

  $("#modal-total").textContent = fmtBytes(total);

  const warning = $("#modal-warning");
  if (risky.length) {
    warning.classList.remove("hidden");
    warning.innerHTML = `<b>${risky.length} riskli öğe</b> seçildi. Bunlar eski yedekler veya büyük kullanıcı dosyaları olabilir. Kalıcı silmeden önce çöpe taşımayı düşünün.`;
  } else {
    warning.classList.add("hidden");
    warning.innerHTML = "";
  }

  const info = $("#modal-info");
  if (commands.length) {
    info.classList.remove("hidden");
    info.innerHTML = `${commands.length} öğe <b>sudo</b> gerektiriyor. Bunlar otomatik çalıştırılmaz; işlem sonunda terminalde açmanız için komut gösterilir.`;
  } else {
    info.classList.add("hidden");
    info.innerHTML = "";
  }

  $$(".mode").forEach((mode) => mode.classList.toggle("active", mode.dataset.mode === "delete"));
  const radio = document.querySelector('input[name="mode"][value="delete"]');
  if (radio) radio.checked = true;
  $("#confirm-check").checked = false;
  $("#modal-confirm").disabled = true;
  $("#modal").classList.remove("hidden");
  $("#confirm-check").focus();
}

function closeModal() {
  $("#modal").classList.add("hidden");
}

function updateConfirmButton() {
  $("#modal-confirm").disabled = !$("#confirm-check").checked;
}

async function runClean() {
  if (!$("#confirm-check").checked) return;
  const ids = state.modalIds.slice();
  if (!ids.length) return;
  state.lastCleanMode = state.mode;
  closeModal();
  try {
    await api("/api/clean", {
      method: "POST",
      body: JSON.stringify({ ids, mode: state.mode, confirm: true }),
    });
    const data = await refresh();
    updateOverlay();
    schedulePoll(450);
    if (data.phase !== "cleaning" && data.phase !== "ready") toast("Temizlik başlatılamadı.", "error");
  } catch (error) {
    toast(error.message, "error");
  }
}

function showResults() {
  const data = state.data;
  const results = data.results || [];
  if (!results.length) return;
  const freed = results.reduce((sum, result) => sum + (result.freed || 0), 0);
  const pending = results.filter((result) => result.status === "needs_terminal");
  const failed = results.filter((result) => ["error", "partial"].includes(result.status));

  $("#result-freed").textContent = fmtBytes(freed);
  $("#result-note").textContent =
    state.lastCleanMode === "trash"
      ? "çöpe taşındı — alan çöp boşaltılınca açılır"
      : "disk alanı boşaltıldı";

  $("#result-list").innerHTML = results
    .map((result) => {
      const status = STATUS_LABELS[result.status] || result.status;
      const command =
        result.status === "needs_terminal" && result.command
          ? `<div class="cmd-row">
              <code>${escapeHtml(result.command)}</code>
              <button class="btn tiny" type="button" data-terminal="${escapeHtml(result.command)}">Terminalde aç</button>
            </div>`
          : "";
      const error = result.error ? `<div class="r-error">${escapeHtml(result.error)}</div>` : "";
      return `<div class="result-row ${result.status}">
        <span class="dot"></span>
        <span class="r-title">${escapeHtml(result.title)}<br><span class="r-size">${status}</span>${error}${command}</span>
        <span class="r-size">${result.freed ? fmtBytes(result.freed) : ""}</span>
      </div>`;
    })
    .join("");

  const trashItem = data.items.find((item) => item.rule_id === "trash");
  let footer = "";
  if (pending.length) footer += `${pending.length} komut terminalde çalıştırılmayı bekliyor. `;
  if (failed.length) footer += `${failed.length} öğede sorun oluştu. `;
  if (state.lastCleanMode === "trash" && freed > 0 && trashItem) {
    footer += `Çöp kutusunda ${fmtBytes(trashItem.size)} var.`;
  }
  $("#result-footer").innerHTML =
    escapeHtml(footer) +
    (state.lastCleanMode === "trash" && freed > 0 && trashItem
      ? ' <button class="btn tiny" type="button" id="result-empty-trash">Çöpü boşalt</button>'
      : "");

  $("#result-modal").classList.remove("hidden");
}

async function emptyTrashFromResults() {
  const trash = state.data?.items.find((item) => item.rule_id === "trash");
  if (!trash) {
    toast("Çöp kutusu zaten boş.", "success");
    return;
  }
  $("#result-modal").classList.add("hidden");
  state.selected = new Set([trash.id]);
  render();
  openCleanModal();
}

/* -------------------------------------------------------------- eylemler */

async function openTerminal(command) {
  try {
    await api("/api/terminal", { method: "POST", body: JSON.stringify({ command }) });
    toast("Terminal açıldı. Parolanızı orada girebilirsiniz.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

function bindEvents() {
  $("#btn-scan").addEventListener("click", startScan);
  $("#btn-empty-scan").addEventListener("click", startScan);
  $("#result-rescan").addEventListener("click", () => {
    $("#result-modal").classList.add("hidden");
    startScan();
  });
  $("#btn-select-safe").addEventListener("click", () => {
    const safe = (state.data?.items || []).filter((item) => item.risk === "safe" && item.action === "delete");
    for (const item of safe) state.selected.add(item.id);
    render();
  });
  $("#btn-clear").addEventListener("click", () => {
    state.selected.clear();
    render();
  });
  $("#btn-clean").addEventListener("click", openCleanModal);

  $("#filters").addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (chip) setFilter(chip.dataset.filter);
  });

  let searchTimer = null;
  $("#search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = setTimeout(() => {
      state.query = value.trim().toLocaleLowerCase("tr-TR");
      renderContent();
    }, 110);
  });

  $("#only-selected").addEventListener("change", (event) => {
    state.onlySelected = event.target.checked;
    renderContent();
  });

  $("#content").addEventListener("click", (event) => {
    const terminal = event.target.closest("[data-terminal]");
    if (terminal) {
      event.preventDefault();
      event.stopPropagation();
      openTerminal(terminal.dataset.terminal);
      return;
    }
    const row = event.target.closest(".item");
    if (!row) return;
    if (event.target.closest("input, button, code, a")) return;
    toggleItem(row.dataset.id);
  });

  $("#content").addEventListener("change", (event) => {
    if (!event.target.classList.contains("cb")) return;
    const row = event.target.closest(".item");
    if (row) toggleItem(row.dataset.id, event.target.checked);
  });

  $("#confirm-check").addEventListener("change", updateConfirmButton);
  $("#modal-confirm").addEventListener("click", runClean);
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-cancel").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (event) => {
    if (event.target === $("#modal")) closeModal();
  });

  $$(".mode").forEach((mode) => {
    mode.addEventListener("click", () => {
      state.mode = mode.dataset.mode;
      $$(".mode").forEach((other) => other.classList.toggle("active", other === mode));
      const radio = mode.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  $("#result-close").addEventListener("click", () => $("#result-modal").classList.add("hidden"));
  $("#result-close-2").addEventListener("click", () => $("#result-modal").classList.add("hidden"));
  $("#result-modal").addEventListener("click", (event) => {
    if (event.target === $("#result-modal")) $("#result-modal").classList.add("hidden");
    const terminal = event.target.closest("[data-terminal]");
    if (terminal) {
      event.preventDefault();
      openTerminal(terminal.dataset.terminal);
    }
    if (event.target.id === "result-empty-trash") emptyTrashFromResults();
  });

  const help = $("#help-drawer");
  const helpOverlay = $("#help-overlay");
  const toggleHelp = (open) => {
    help.classList.toggle("open", open);
    helpOverlay.classList.toggle("open", open);
  };
  $("#btn-help").addEventListener("click", () => toggleHelp(true));
  $("#help-close").addEventListener("click", () => toggleHelp(false));
  helpOverlay.addEventListener("click", () => toggleHelp(false));

  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    const modalOpen =
      !$("#modal").classList.contains("hidden") ||
      !$("#result-modal").classList.contains("hidden") ||
      $("#help-drawer").classList.contains("open");
    if (event.key === "Escape") {
      closeModal();
      $("#result-modal").classList.add("hidden");
      toggleHelp(false);
    } else if (event.key === "/" && !typing && !modalOpen) {
      event.preventDefault();
      $("#search").focus();
    } else if (event.key.toLowerCase() === "s" && !typing && !modalOpen && !event.ctrlKey && !event.metaKey) {
      const phase = state.data?.phase;
      if (phase === "ready" || phase === "idle") startScan();
    }
  });
}

/* ------------------------------------------------------------------ başlat */

(async function boot() {
  bindEvents();
  try {
    const data = await refresh();
    if (data.phase === "idle") {
      await startScan();
    }
  } catch (error) {
    toast(`Sunucuya ulaşılamadı: ${error.message}`, "error");
  }
  schedulePoll(1200);
})();
