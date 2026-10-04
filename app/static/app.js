/* Folio front-end: catalog, hash router, tool workspace, PWA shell. No build step. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "style") el.style.cssText = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
  const mobile = () => matchMedia("(max-width: 760px)").matches;
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };

  /* ---------- Glyphs: 24×24 stroke icons ---------- */
  const P = {
    doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    md: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 15V9l2.5 3L11 9v6M15.5 9v6m0 0-2-2m2 2 2-2"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5"/>',
    merge: '<path d="M4 4h6v7H4zM14 4h6v7h-6z"/><path d="M7 11v3a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-3M12 16v5m-2.5-2.5L12 21l2.5-2.5"/>',
    split: '<path d="M4 3h16v7H4zM4 14h16v7H4z"/><path d="M2 12h3m3 0h3m3 0h3m3 0h2"/>',
    remove: '<path d="M6 3h8l4 4v14H6z"/><path d="M9.5 12.5l5 5m0-5-5 5"/>',
    extract: '<path d="M4 7h10v14H4z"/><path d="M9 3h11v14"/><path d="M12 10l4-4m0 0h-3m3 0v3"/>',
    reorder: '<path d="M4 4h7v7H4zM13 13h7v7h-7z"/><path d="M17 4h3v3M20 4l-5 5M7 20H4v-3M4 20l5-5"/>',
    rotate: '<path d="M7 7h10v14H7z"/><path d="M4 9a8 8 0 0 1 10-6.5M14 2.5 12.5 5M14 2.5 11.3 1.6"/>',
    compress: '<path d="M6 3h12v18H6z"/><path d="M12 6v4m0 0-2-2m2 2 2-2M12 18v-4m0 0-2 2m2-2 2 2M9 12h6"/>',
    repair: '<path d="M14.5 5.5a4 4 0 0 0-5 5L4 16l4 4 5.5-5.5a4 4 0 0 0 5-5L16 12l-4-4z"/>',
    ocr: '<path d="M3 8V4h4M17 4h4v4M21 16v4h-4M7 20H3v-4"/><path d="M8 9h8M8 12h8M8 15h5"/>',
    gray: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none" opacity=".35"/>',
    word: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M8.5 11l1.5 6 2-4.5 2 4.5 1.5-6"/>',
    powerpoint: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M10 17v-6h2.5a2 2 0 0 1 0 4H10"/>',
    excel: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 11l5 6m0-6-5 6"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    archive: '<path d="M3 4h18v4H3zM5 8v12h14V8"/><path d="M10 12h4"/>',
    text: '<path d="M5 5h14M12 5v14M9 19h6"/>',
    watermark: '<path d="M6 3h8l4 4v14H6z"/><path d="M8.5 17l7-7" stroke-dasharray="2 2"/>',
    numbers: '<path d="M6 3h8l4 4v14H6z"/><path d="M10.5 14.5l1.5-1v5m-1.5 0h3"/>',
    crop: '<path d="M6 2v16h16"/><path d="M2 6h16v16"/>',
    flatten: '<path d="M12 3 3 8l9 5 9-5z"/><path d="M3 12.5l9 5 9-5M3 17l9 5 9-5"/>',
    compare: '<path d="M4 4h6v16H4zM14 4h6v16h-6z"/><path d="M6 8h2M6 11h2M16 8h2M16 11h2M16 14h2"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><circle cx="12" cy="15.5" r="1.3"/>',
    unlock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.7-1.5"/><circle cx="12" cy="15.5" r="1.3"/>',
    redact: '<path d="M6 3h8l4 4v14H6z"/><rect x="8" y="10" width="8" height="2.6" fill="currentColor"/><rect x="8" y="15" width="5" height="2.6" fill="currentColor"/>',
    sanitize: '<path d="M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
    ratio: '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M7 10V9h2M17 14v1h-2"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    add: '<path d="M6 3h8l4 4v14H6z"/><path d="M12 11v6M9 14h6"/>',
    bolt: '<path d="M13 3 5 13.5h6L10 21l8-10.5h-6z"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><circle cx="7.5" cy="8.5" r="1.3"/>',
    vector: '<path d="M5 19C8 9 16 15 19 5"/><rect x="3" y="17" width="4" height="4"/><rect x="17" y="3" width="4" height="4"/><circle cx="12" cy="12" r="1.5"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    book: '<path d="M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2z"/><path d="M4 20a2 2 0 0 0 2 1h13v-3"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    sign: '<path d="M3 17c3 0 4-9 6-9s1 8 3 8 2-4 4-4 2 3 5 3"/><path d="M3 21h18"/>',
    form: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h3M13 12h3M8 16h8"/>',
    id: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2.3"/><path d="M5.5 16c.7-1.6 2-2.4 3.5-2.4s2.8.8 3.5 2.4M14.5 10h4M14.5 13h3"/>',
    convert: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    smile: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14c.8 1.4 2 2 3.5 2s2.7-.6 3.5-2"/><path d="M9 9.5h.01M15 9.5h.01" stroke-width="2.4"/>',
    face: '<circle cx="12" cy="10" r="4"/><path d="M4.5 20c1.4-3.3 4.2-5 7.5-5s6.1 1.7 7.5 5"/><path d="M3 3l18 18" opacity=".6"/>',
    cutout: '<path d="M8 21c-1-4 0-6 2-8-1.6-1.3-2-3-1.5-4.6C9.2 6 11 5 12.5 5.4 15 6 15.8 8.6 14.6 10.6c2.6 1.6 3.6 5 2.4 10.4"/><path d="M3 3h3M3 3v3M21 3h-3M21 3v3M3 21h3M3 21v-3M21 21h-3M21 21v-3"/>',
    expand: '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01" stroke-width="2.2"/>',
    film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    audio: '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    scissors: '<circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/><path d="M8 8.5 20 17M8 15.5 20 7"/>',
    mute: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l4 6M21 9l-4 6"/>',
    font: '<path d="M4 20 10 4h1l6 16M6.5 14h8.5"/><path d="M17 20h4"/>',
  };
  const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${P[name] || P.doc}</svg>`;
  const UI = {
    up: '<path d="M12 19V5m-6 6 6-6 6 6"/>', down: '<path d="M12 5v14m-6-6 6 6 6-6"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>', check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
    alert: '<path d="M12 8v5m0 3.5v.5"/>',
    share: '<path d="M12 15V3m-4 4 4-4 4 4"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/>',
    dl: '<path d="M12 4v12m-5-5 5 5 5-5M5 20h14"/>',
  };
  const ui = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${UI[n]}</svg>`;

  const EXT_COLOR = {
    pdf: "#d8401f", doc: "#24489a", docx: "#24489a", odt: "#24489a", rtf: "#24489a", txt: "#554e43",
    ppt: "#c2571a", pptx: "#c2571a", odp: "#c2571a", xls: "#1d6b57", xlsx: "#1d6b57", ods: "#1d6b57", csv: "#1d6b57",
    md: "#1b1915", html: "#9a3a5a", htm: "#9a3a5a", jpg: "#0f7385", jpeg: "#0f7385", png: "#0f7385", webp: "#0f7385",
    heic: "#0f7385", mp4: "#b0562a", mov: "#b0562a", mp3: "#b0562a", wav: "#b0562a", zip: "#4a5a6e", epub: "#4a5a6e",
  };

  const NEXT = {
    merge: ["compress", "page-numbers", "protect", "edit-pdf"],
    split: ["merge", "compress"],
    compress: ["protect", "pdf-to-markdown", "merge"],
    "compress-pdf-to-size": ["protect", "merge"],
    "word-to-pdf": ["compress", "merge", "edit-pdf"],
    "image-to-pdf": ["ocr", "compress-pdf-to-size", "merge"],
    "scan-to-pdf": ["compress-pdf-to-size", "edit-pdf", "merge"],
    ocr: ["pdf-to-markdown", "pdf-to-word", "edit-pdf"],
    "pdf-to-image": ["image-to-pdf", "image-to-size"],
    "any-to-markdown": ["markdown-to-pdf", "convert-document"],
    "pdf-to-markdown": ["markdown-to-pdf", "convert-document"],
    "resize-image": ["image-to-size", "convert-image", "image-to-pdf"],
    "crop-ratio": ["image-to-size", "resize-image"],
    "form-photo": ["image-to-size", "image-to-pdf"],
    "image-to-size": ["image-to-pdf", "resize-image"],
    "remove-bg": ["crop-ratio", "image-to-size"],
    "convert-video": ["compress-video", "resize-video"],
    "resize-video": ["compress-video", "video-to-gif"],
  };
  const DEFAULT_NEXT = ["compress", "merge", "edit-pdf", "image-to-size"];

  /* ---------- State ---------- */
  let DATA = { categories: [], tools: [] };
  let byId = {};
  let current = null;
  let files = [];
  let asset = null;
  let lastBlobUrl = null;
  let xhr = null;
  let carry = null;
  let deferredInstall = null;

  const fmtBytes = (n) => {
    if (!n && n !== 0) return "";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n < 10 && i ? 1 : 0)} ${u[i]}`;
  };
  const extOf = (name) => (name.split(".").pop() || "").toLowerCase();
  const toast = (msg) => {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 2800);
  };
  const catColor = (id) => `var(--c-${id})`;
  const acceptsFile = (t, name) => !t.accept.length || t.accept.includes("." + extOf(name));

  /* ---------- Catalog ---------- */
  async function load() {
    try {
      const res = await fetch("/api/tools");
      DATA = await res.json();
    } catch {
      $("#catalog").innerHTML = '<p class="no-results">The tool server is not reachable.</p>';
      return;
    }
    byId = Object.fromEntries(DATA.tools.map((t) => [t.id, t]));
    renderNav();
    renderCatalog();
    renderStats();
    renderShelves();
    renderBrowse();
    observeCards();
    route();
    receiveShared();
  }

  function renderStats() {
    const fmts = new Set(DATA.tools.flatMap((t) => t.accept)).size;
    $("#heroStats").append(
      h("div", {}, h("dt", {}, "tools on the desk"), h("dd", {}, String(DATA.tools.length))),
      h("div", {}, h("dt", {}, "file formats"), h("dd", {}, `${fmts}+`)),
      h("div", {}, h("dt", {}, "uploads kept"), h("dd", {}, "0")),
    );
  }

  function renderNav() {
    const nav = $("#catNav");
    for (const c of DATA.categories) nav.append(h("a", { href: `#cat-${c.id}`, style: `--c:${catColor(c.id)}`, "data-cat": c.id }, c.name));
    nav.addEventListener("click", (e) => {
      const a = e.target.closest("a");
      if (!a) return;
      e.preventDefault();
      document.getElementById(`cat-${a.dataset.cat}`)?.scrollIntoView({ behavior: "smooth" });
    });
  }

  function tileFor(t, i = 0) {
    const a = h("a", { class: "tile", href: `#/tool/${t.id}`, style: `--c:${catColor(t.category)};animation-delay:${i * 0.04}s` });
    a.innerHTML = `<span class="glyph">${icon(t.glyph)}</span><span><b>${esc(t.name)}</b><small>${esc(DATA.categories.find((c) => c.id === t.category)?.name || "")}</small></span>`;
    return a;
  }

  function renderShelves() {
    const order = ["edit-pdf", "image-to-size", "compress", "any-to-markdown", "form-photo", "merge", "scan-to-pdf", "sign-pdf",
      "compress-pdf-to-size", "pdf-to-word", "resize-image", "remove-bg", "convert-image", "compress-video", "resize-video", "convert-document"];
    const rank = (t) => { const i = order.indexOf(t.id); return i < 0 ? 99 : i; };
    const pop = DATA.tools.filter((t) => t.popular).sort((a, b) => rank(a) - rank(b));
    $("#popularRail").replaceChildren(...pop.map(tileFor));
    const recent = store.get("folio.recent", []).filter((id) => byId[id]);
    $("#recentShelf").hidden = !recent.length;
    $("#recentRail").replaceChildren(...recent.map((id, i) => tileFor(byId[id], i)));
  }

  function pushRecent(id) {
    const r = [id, ...store.get("folio.recent", []).filter((x) => x !== id)].slice(0, 10);
    store.set("folio.recent", r);
    renderShelves();
  }

  function renderCatalog() {
    const root = $("#catalog");
    DATA.categories.forEach((c, ci) => {
      const rank = (t) => (t.kind === "editor" ? 0 : t.popular ? 1 : 2);
      const tools = DATA.tools.filter((t) => t.category === c.id).sort((a, b) => rank(a) - rank(b));
      const grid = h("div", { class: "grid" });
      tools.forEach((t, i) => {
        const card = h("a", {
          class: "card", href: `#/tool/${t.id}`, style: `--c:${catColor(c.id)};--d:${(i % 8) * 0.05}s`,
          "data-id": t.id,
          "data-search": `${t.name} ${t.description} ${c.name} ${t.keywords} ${t.accept.join(" ")}`.toLowerCase(),
        });
        const badge = c.id === "markdown" ? '<span class="badge">MarkItDown</span>' : t.popular ? '<span class="badge hot">Popular</span>' : "";
        card.innerHTML = `
          <span class="glyph">${icon(t.glyph)}</span>${badge}
          <div class="txt"><h3>${esc(t.name)}</h3><p>${esc(t.description)}</p></div>
          <svg class="arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`;
        grid.append(card);
      });
      const sec = h("section", { class: `cat${tools.length > 5 ? " collapsed" : ""}`, id: `cat-${c.id}`, style: `--c:${catColor(c.id)}` },
        h("header", { class: "cat-head" },
          h("span", { class: "cat-num" }, `${String(ci + 1).padStart(2, "0")} — ${tools.length} tools`),
          h("h2", {}, c.name), h("p", {}, c.blurb), h("span", { class: "cat-ink" })),
        h("div", {}, grid, tools.length > 5 ? h("button", {
          class: "link-btn more", type: "button",
          onclick: (e) => { sec.classList.remove("collapsed"); e.currentTarget.remove(); },
        }, `Show all ${tools.length}`) : null));
      root.append(sec);
    });
  }

  function renderBrowse() {
    const g = $("#browseGrid");
    DATA.categories.forEach((c, i) => {
      const n = DATA.tools.filter((t) => t.category === c.id).length;
      const first = DATA.tools.find((t) => t.category === c.id);
      const a = h("a", { class: "browse-cat", href: `#cat-${c.id}`, style: `--c:${catColor(c.id)};animation-delay:${i * 0.03}s` });
      a.innerHTML = `${icon(first?.glyph)}<span><b>${esc(c.name)}</b><br><small>${n} tools</small></span>`;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        closeBrowse();
        const sec = document.getElementById(`cat-${c.id}`);
        sec.classList.remove("collapsed");
        sec.querySelector(".more")?.remove();
        sec.scrollIntoView({ behavior: "smooth" });
      });
      g.append(a);
    });
  }
  const openBrowse = () => { $("#browse").hidden = false; setTab("browse"); };
  const closeBrowse = () => { $("#browse").hidden = true; setTab("home"); };

  function observeCards() {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -40px 0px" });
    $$(".card").forEach((c) => io.observe(c));
    const navIo = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const id = e.target.id.replace("cat-", "");
        $$(".cat-nav a").forEach((a) => a.classList.toggle("active", a.dataset.cat === id));
      }
    }, { rootMargin: "-45% 0px -50% 0px" });
    $$(".cat").forEach((s) => navIo.observe(s));
  }

  /* ---------- Search ---------- */
  function filter(q) {
    q = q.trim().toLowerCase();
    let shown = 0;
    const words = q.split(/\s+/).filter(Boolean);
    $$(".card").forEach((card) => {
      const match = !q || words.every((w) => card.dataset.search.includes(w));
      card.hidden = !match;
      card.classList.add("in");
      const title = $("h3", card);
      title.innerHTML = esc(byId[card.dataset.id].name);
      if (q && match) {
        const re = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
        title.innerHTML = title.innerHTML.replace(new RegExp(`(${re})`, "gi"), "<mark>$1</mark>");
      }
      shown += match;
    });
    $$(".cat").forEach((s) => {
      s.hidden = !$$(".card", s).some((c) => !c.hidden);
      if (q) s.classList.remove("collapsed");
    });
    $("#recentShelf").hidden = !!q || !store.get("folio.recent", []).length;
    $("#popularShelf").hidden = !!q;
    $(".hero").hidden = !!q && mobile();
    const nr = $("#noResults");
    nr.hidden = shown > 0;
    $("span", nr).textContent = q;
  }

  /* ---------- Router & tabs ---------- */
  function setTab(name) { $$(".tabbar a").forEach((a) => a.classList.toggle("on", a.dataset.tab === name)); }

  function route() {
    const hash = location.hash;
    const m = hash.match(/^#\/tool\/([\w-]+)/);
    if (m && byId[m[1]]) {
      const t = byId[m[1]];
      pushRecent(t.id);
      if (t.kind === "editor") {
        if (current) closeTool(false);
        window.FolioEditor?.open(t, takeCarry(t));
        setTab(t.id === "edit-pdf" ? "edit" : "home");
      } else {
        window.FolioEditor?.close(false);
        openTool(t);
        setTab(t.id === "scan-to-pdf" ? "scan" : "home");
      }
      return;
    }
    if (current) closeTool(false);
    window.FolioEditor?.close(false);
    if (hash === "#/browse") return openBrowse();
    $("#browse").hidden = true;
    if (hash === "#/search") {
      document.body.classList.add("searching");
      setTab("search");
      setTimeout(() => $("#search").focus(), 50);
      return;
    }
    setTab("home");
  }

  function takeCarry(t) {
    const c = carry && acceptsFile(t, carry.name) ? carry : null;
    carry = null;
    return c ? new File([c.blob], c.name, { type: c.blob.type }) : null;
  }

  /* ---------- Workspace ---------- */
  function openTool(t) {
    const fresh = !current;
    current = t;
    files = [];
    asset = null;
    const ws = $("#workspace");
    const sheet = $(".ws-sheet", ws);
    sheet.style.setProperty("--c", catColor(t.category));
    $("#wsSwatch").innerHTML = icon(t.glyph);
    $("#wsCat").textContent = DATA.categories.find((c) => c.id === t.category)?.name || "";
    $("#wsTitle").textContent = t.name;
    $("#wsDesc").textContent = t.description;
    const short = t.name.replace(/ PDF$/, "");
    $(".run-label", ws).textContent = / (to|from)$/i.test(short) ? t.name : short;

    const input = $("#fileInput");
    input.multiple = t.multiple;
    input.accept = t.accept.join(",");
    const noFiles = t.min_files === 0 && t.accept.length === 0;
    $("#drop").hidden = noFiles;
    $("#pickRow").hidden = noFiles;
    $("#pickRow").style.display = noFiles ? "none" : "";
    $("#pickCamera").hidden = !(t.capture || (t.accept.some((a) => [".jpg", ".png", ".heic"].includes(a)) && mobile()));
    $("#cameraInput").multiple = t.multiple;
    $("#pickFiles").classList.toggle("primary", !t.capture);
    $("#pickCamera").classList.toggle("primary", !!t.capture);
    $("#drop").classList.remove("compact");
    $(".drop-title", $("#drop")).innerHTML = t.multiple ? "Drop files here or <u>browse</u>" : "Drop a file here or <u>browse</u>";
    $("#dropHint").textContent = t.accept.length
      ? `${t.accept.slice(0, 14).map((a) => a.slice(1)).join(" · ")}${t.accept.length > 14 ? " …" : ""}${t.min_files > 1 ? ` — at least ${t.min_files} files` : ""} — up to ${DATA.max_upload_mb} MB`
      : `Any file type — up to ${DATA.max_upload_mb} MB`;

    const c = takeCarry(t);
    if (c) files = [c];
    renderOptions(t);
    renderFiles();
    showPane("body");

    ws.hidden = false;
    ws.classList.remove("closing");
    document.body.classList.add("ws-open");
    if (!fresh) { sheet.style.animation = "none"; void sheet.offsetHeight; sheet.style.animation = ""; }
    document.body.classList.add("locked");
    sheet.scrollTop = 0;
    if (c) setTimeout(() => toast(`Carried over ${c.name}`), 450);
    else if (!mobile()) setTimeout(() => (noFiles ? $("input, textarea", $("#optForm")) : $("#drop"))?.focus({ preventScroll: true }), 350);
    document.title = `${t.name} — Folio`;
  }

  function closeTool(push = true) {
    if (xhr) { xhr.abort(); xhr = null; }
    const ws = $("#workspace");
    ws.classList.add("closing");
    setTimeout(() => { ws.hidden = true; ws.classList.remove("closing"); }, 300);
    document.body.classList.remove("locked", "ws-open");
    current = null;
    document.title = "Folio — every document tool on one desk";
    if (push && location.hash.startsWith("#/tool/")) history.pushState("", "", location.pathname + location.search);
    setTab("home");
  }

  function showPane(which) {
    $("#wsBody").hidden = which !== "body";
    $("#wsProgress").hidden = which !== "progress";
    $("#wsResult").hidden = which !== "result";
    $(".ws-sheet").scrollTop = 0;
  }

  /* ---------- Options form ---------- */
  function renderOptions(t) {
    const form = $("#optForm");
    form.innerHTML = "";
    for (const o of t.options) {
      const id = `opt-${o.name}`;
      const f = h("div", { class: `field${o.half ? " half" : ""}`, "data-name": o.name });
      if (o.when) f.dataset.when = JSON.stringify(o.when);
      const lab = (extra) => h("label", { for: id }, o.label, extra || "");
      switch (o.type) {
        case "segmented": {
          f.append(h("span", { class: "label" }, o.label));
          const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": o.label });
          for (const [v, l] of o.choices) seg.append(h("label", {}, h("input", { type: "radio", name: o.name, value: v, checked: String(o.default) === v }), h("span", {}, l)));
          f.append(seg);
          break;
        }
        case "grid9": {
          f.append(h("span", { class: "label" }, o.label));
          const g = h("div", { class: "grid9", role: "radiogroup", "aria-label": o.label });
          for (const [v, l] of o.choices) g.append(h("label", { class: v === "tile" ? "wide" : "" }, h("input", { type: "radio", name: o.name, value: v, checked: o.default === v, "aria-label": v }), h("span", {}, l)));
          f.append(g);
          break;
        }
        case "cards": {
          f.append(h("span", { class: "label" }, o.label));
          const wrap = h("div", { class: "choice-cards" });
          for (const [v, l, d] of o.choices) wrap.append(h("label", {}, h("input", { type: "radio", name: o.name, value: v, checked: o.default === v }), h("b", {}, l), h("small", {}, d)));
          f.append(wrap);
          break;
        }
        case "chips": {
          f.append(h("span", { class: "label" }, o.label));
          const wrap = h("div", { class: "chips-opt" });
          for (const [v, l] of o.choices) {
            wrap.append(h("button", { type: "button", "data-v": v, onclick: (e) => {
              $$("button", wrap).forEach((b) => b.classList.toggle("on", b === e.currentTarget));
              applySets(o.sets?.[v]);
            } }, l));
          }
          f.append(wrap, h("input", { type: "hidden", name: o.name, value: o.default ?? "" }));
          break;
        }
        case "select": {
          f.append(lab());
          const s = h("select", { id, name: o.name });
          for (const [v, l] of o.choices) s.append(h("option", { value: v, selected: o.default === v }, l));
          if (o.sets) s.addEventListener("change", () => applySets(o.sets[s.value]));
          f.append(s);
          break;
        }
        case "checkbox":
          f.append(h("label", { class: "check" }, h("input", { type: "checkbox", name: o.name, checked: !!o.default }), o.label));
          break;
        case "range": {
          const out = h("output", {}, `${o.default}${o.unit || ""}`);
          const r = h("input", { type: "range", id, name: o.name, min: o.min, max: o.max, value: o.default });
          r.addEventListener("input", () => (out.textContent = `${r.value}${o.unit || ""}`));
          f.append(lab(out), r);
          break;
        }
        case "textarea":
          f.append(lab(), h("textarea", { id, name: o.name, placeholder: o.placeholder || "" }, o.default || ""));
          break;
        case "file": {
          const inp = h("input", { type: "file", id, accept: o.accept || "" });
          inp.addEventListener("change", () => { asset = inp.files[0] || null; validate(); });
          f.append(lab(), inp);
          break;
        }
        default:
          f.append(lab(), h("input", {
            type: o.type, id, name: o.name, value: o.default ?? "", placeholder: o.placeholder || "",
            min: o.min, max: o.max, step: o.type === "number" ? "any" : null,
            inputmode: o.type === "number" ? "decimal" : null,
            autocomplete: o.type === "password" ? "new-password" : "off", spellcheck: "false",
          }));
      }
      if (o.help) f.append(h("p", { class: "help" }, o.help));
      form.append(f);
    }
    form.oninput = form.onchange = () => { applyWhen(); validate(); };
    form.onsubmit = (e) => { e.preventDefault(); run(); };
    // presets attached to a select apply their defaults immediately
    for (const o of t.options) if (o.type === "select" && o.sets?.[o.default]) applySets(o.sets[o.default]);
    applyWhen();
    validate();
  }

  function applySets(values) {
    if (!values) return;
    const form = $("#optForm");
    for (const [k, v] of Object.entries(values)) {
      const radios = form.querySelectorAll(`input[type=radio][name="${k}"]`);
      if (radios.length) { radios.forEach((r) => (r.checked = r.value === String(v))); continue; }
      const el = form.elements[k];
      if (!el) continue;
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    applyWhen();
    validate();
  }

  function formValues() {
    const out = {};
    const form = $("#optForm");
    for (const o of current.options) {
      if (o.type === "file") continue;
      if (o.type === "checkbox") out[o.name] = form.elements[o.name].checked;
      else if (["segmented", "cards", "grid9"].includes(o.type)) out[o.name] = (form.querySelector(`input[name="${o.name}"]:checked`) || {}).value ?? o.default;
      else out[o.name] = form.elements[o.name]?.value ?? "";
    }
    return out;
  }

  function applyWhen() {
    const vals = formValues();
    $$(".field[data-when]", $("#optForm")).forEach((f) => {
      const cond = JSON.parse(f.dataset.when);
      f.hidden = !Object.entries(cond).every(([k, v]) => {
        const val = typeof vals[k] === "boolean" ? vals[k] : String(vals[k]);
        return Array.isArray(v) ? v.includes(val) : val === v;
      });
    });
  }

  function validate() {
    if (!current) return false;
    const vals = formValues();
    const visible = (name) => !$(`.field[data-name="${name}"]`, $("#optForm"))?.hidden;
    const missing = current.options.some((o) => o.required && visible(o.name) && !String(vals[o.name] ?? "").trim());
    const needsAsset = current.options.some((o) => o.type === "file" && visible(o.name)) && !asset;
    const ok = files.length >= current.min_files && !missing && !needsAsset;
    $("#runBtn").disabled = !ok;
    return ok;
  }


  /* ---------- Previews ---------- */
  const NATIVE_IMG = ["jpg", "jpeg", "png", "webp", "gif", "bmp", "svg", "avif", "ico", "jfif"];
  const NATIVE_VIDEO = ["mp4", "webm", "m4v"];
  const AUDIO_EXT = ["mp3", "wav", "m4a", "ogg", "oga", "opus", "flac", "aac"];
  const TEXTY = ["txt", "md", "markdown", "csv", "tsv", "json", "xml", "html", "htm", "py", "js", "ts", "css", "log", "yaml",
    "yml", "ini", "sql", "sh", "c", "cpp", "java", "rst", "tex", "conf", "org", "adoc"];
  const pvCache = new WeakMap();
  let selected = 0;

  async function serverPreview(file, { first = 0, count = 12, width = 300 } = {}) {
    if (file.size > 120 * 1024 * 1024) return { kind: "none", error: "Too large to preview" };
    const fd = new FormData();
    fd.append("file", file, file.name || "file");
    fd.append("first", first); fd.append("count", count); fd.append("width", width);
    try { return await (await fetch("/api/preview", { method: "POST", body: fd })).json(); } catch { return { kind: "none" }; }
  }

  function preview(file) {
    if (pvCache.has(file)) return pvCache.get(file);
    const ext = extOf(file.name || "");
    let p;
    if (NATIVE_IMG.includes(ext)) {
      p = new Promise((res) => {
        const url = URL.createObjectURL(file);
        const im = new Image();
        im.onload = () => res({ kind: "image", url, thumb: url, w: im.naturalWidth, h: im.naturalHeight });
        im.onerror = () => serverPreview(file).then(res);
        im.src = url;
      });
    } else if (NATIVE_VIDEO.includes(ext)) {
      p = new Promise((res) => {
        const url = URL.createObjectURL(file);
        const v = document.createElement("video");
        v.preload = "metadata"; v.muted = true; v.playsInline = true;
        v.onloadedmetadata = () => { v.currentTime = Math.min(1, (v.duration || 2) / 2); };
        v.onseeked = () => {
          const c = document.createElement("canvas");
          c.width = Math.min(640, v.videoWidth || 320); c.height = Math.round(c.width * (v.videoHeight || 180) / (v.videoWidth || 320));
          c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
          res({ kind: "video", url, thumb: c.toDataURL("image/jpeg", 0.8), w: v.videoWidth, h: v.videoHeight, duration: v.duration });
        };
        v.onerror = () => serverPreview(file).then((r) => res({ ...r, kind: "video", thumb: r.pages?.[0] }));
        v.src = url;
      });
    } else if (AUDIO_EXT.includes(ext)) {
      p = new Promise((res) => {
        const url = URL.createObjectURL(file);
        const a = document.createElement("audio");
        a.preload = "metadata";
        a.onloadedmetadata = () => res({ kind: "audio", url, duration: a.duration });
        a.onerror = () => res({ kind: "audio", url });
        a.src = url;
      });
    } else if (TEXTY.includes(ext)) {
      p = file.slice(0, 8000).text().then((text) => ({ kind: "text", text, more: file.size > 8000 }));
    } else {
      p = serverPreview(file).then((r) => ({ ...r, thumb: r.pages?.[0] }));
    }
    pvCache.set(file, p);
    return p;
  }

  const ratioText = (w, h) => {
    const g = (a, b) => (b ? g(b, a % b) : a);
    const d = g(w, h);
    const a = w / d, b = h / d;
    return a <= 32 && b <= 32 ? `${a}:${b}` : `${(w / h).toFixed(2)}:1`;
  };
  const paperName = (w, h) => {
    const near = (a, b) => Math.abs(a - b) < 4;
    const [s, l] = w < h ? [w, h] : [h, w];
    const name = near(s, 595) && near(l, 842) ? "A4" : near(s, 612) && near(l, 792) ? "Letter" : near(s, 420) && near(l, 595) ? "A5"
      : near(s, 842) && near(l, 1191) ? "A3" : near(s, 612) && near(l, 1008) ? "Legal" : `${Math.round(w / 72 * 25.4)}×${Math.round(h / 72 * 25.4)} mm`;
    return `${name}${w > h ? " landscape" : ""}`;
  };
  const clock = (sec) => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;

  function pvMeta(pv, file) {
    const size = fmtBytes(file.size);
    if (pv.kind === "pages") return `${pv.page_count} page${pv.page_count > 1 ? "s" : ""} · ${paperName(pv.w, pv.h)} · ${size}`;
    if (pv.kind === "image") return `${pv.w} × ${pv.h} px · ${ratioText(pv.w, pv.h)} · ${size}`;
    if (pv.kind === "video") return [pv.w ? `${pv.w} × ${pv.h}` : "", pv.duration ? clock(pv.duration) : "", size].filter(Boolean).join(" · ");
    if (pv.kind === "audio") return [pv.duration ? clock(pv.duration) : "", size].filter(Boolean).join(" · ");
    if (pv.kind === "list") return `${pv.count} file${pv.count === 1 ? "" : "s"} inside · ${size}`;
    return size;
  }

  // Renders a preview of `file` into `box`. Used for uploads and for results.
  async function renderPreview(box, file, { large = false, label = "" } = {}) {
    box.innerHTML = "";
    const head = h("div", { class: "pv-head" }, h("b", {}, label || file.name), h("span", { class: "pv-meta" }, fmtBytes(file.size)));
    const body = h("div", { class: "pv-body" }, h("div", { class: "pv-loading" }, h("span", { class: "spin" }), "Rendering preview…"));
    box.append(head, body);
    const pv = await preview(file);
    if (!box.isConnected) return pv;
    $(".pv-meta", head).textContent = pvMeta(pv, file);
    body.innerHTML = "";
    if (pv.kind === "pages") {
      const grid = h("div", { class: `pv-pages${large ? " large" : ""}` });
      const add = (urls, start) => urls.forEach((u, k) => {
        const n = start + k;
        grid.append(h("figure", { onclick: () => lightbox(file, n, pv.page_count) },
          h("img", { src: u, alt: `Page ${n + 1}`, loading: "lazy" }), h("figcaption", {}, String(n + 1))));
      });
      add(pv.pages, 0);
      body.append(grid);
      if (pv.page_count > pv.pages.length) {
        const more = h("button", { class: "link-btn pv-more", type: "button", onclick: async () => {
          more.textContent = "Loading…";
          const have = grid.children.length;
          const r = await serverPreview(file, { first: have, count: 24 });
          add(r.pages || [], have);
          if (grid.children.length >= pv.page_count) more.remove(); else more.textContent = `Show more (${pv.page_count - grid.children.length} left)`;
        } }, `Show all ${pv.page_count} pages`);
        body.append(more);
      }
      if (pv.meta && pv.meta.text === false) body.append(h("p", { class: "pv-hint" }, "No selectable text found — this looks like a scan. OCR PDF makes it searchable."));
    } else if (pv.kind === "image") {
      body.append(h("img", { class: "pv-img", src: pv.url || pv.pages?.[0], alt: file.name, onclick: () => window.open(pv.url || pv.pages?.[0], "_blank") }));
    } else if (pv.kind === "video") {
      body.append(pv.url ? h("video", { class: "pv-video", src: pv.url, poster: pv.thumb || null, controls: true, playsinline: true, preload: "metadata" })
        : h("img", { class: "pv-img", src: pv.thumb, alt: "" }));
    } else if (pv.kind === "audio") {
      body.append(h("audio", { class: "pv-audio", src: pv.url, controls: true, preload: "metadata" }));
    } else if (pv.kind === "text") {
      body.append(h("pre", { class: "pv-text" }, pv.text + (pv.more ? "\n…" : "")));
    } else if (pv.kind === "list") {
      const t = h("table", { class: "pv-list" });
      pv.items.slice(0, 50).forEach(([n, sz]) => t.append(h("tr", {}, h("td", {}, n), h("td", {}, fmtBytes(sz)))));
      body.append(t);
    } else if (pv.kind === "locked") {
      body.append(h("p", { class: "pv-hint" }, `Password protected (${pv.page_count} pages). Unlock PDF first, or enter the password in the tool.`));
    } else {
      body.append(h("p", { class: "pv-hint" }, pv.error || "No preview for this file type."));
    }
    return pv;
  }

  async function lightbox(file, n, total) {
    const img = h("img", { alt: "" });
    const cap = h("span", {});
    const box = h("div", { class: "modal lightbox", role: "dialog", "aria-modal": "true" });
    const load = async () => {
      cap.textContent = `Page ${n + 1} of ${total}`;
      img.style.opacity = ".35";
      const r = await serverPreview(file, { first: n, count: 1, width: Math.min(1400, Math.round(innerWidth * (devicePixelRatio || 1))) });
      if (r.pages?.[0]) img.src = r.pages[0];
      img.style.opacity = "1";
    };
    const go = (d) => { if (n + d >= 0 && n + d < total) { n += d; load(); } };
    const close = () => { box.remove(); document.removeEventListener("keydown", key); };
    const key = (e) => { if (e.key === "Escape") close(); if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); };
    box.append(h("div", { class: "lb-inner" }, img,
      h("div", { class: "lb-bar" },
        h("button", { class: "icon-btn", type: "button", "aria-label": "Previous page", onclick: () => go(-1), html: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>' }),
        cap,
        h("button", { class: "icon-btn", type: "button", "aria-label": "Next page", onclick: () => go(1), html: '<svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg>' }),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: close, html: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>' }))));
    box.addEventListener("click", (e) => { if (e.target === box) close(); });
    document.addEventListener("keydown", key);
    document.body.append(box);
    load();
  }

  async function largeImage(file) {
    const ext = extOf(file.name || "");
    if (NATIVE_IMG.includes(ext)) return URL.createObjectURL(file);
    const r = await serverPreview(file, { first: 0, count: 1, width: 1000 });
    return r.pages?.[0] || null;
  }

  // Before/after slider for single-file tools whose result is the same kind of document.
  async function compareView(input, output) {
    const kindOf = (n) => { const e = extOf(n); return NATIVE_IMG.includes(e) || ["heic", "tif", "tiff"].includes(e) ? "img" : e === "pdf" ? "pdf" : ""; };
    if (!kindOf(input.name) || kindOf(input.name) !== kindOf(output.name)) return null;
    const [a, b] = await Promise.all([largeImage(input), largeImage(output)]);
    if (!a || !b) return null;
    const ia = await loadImg(a), ib = await loadImg(b);
    if (Math.abs(ia.naturalWidth / ia.naturalHeight - ib.naturalWidth / ib.naturalHeight) > 0.02) return null;
    const wrap = h("div", { class: "cmp", style: "--x:50%" });
    const after = h("img", { src: b, alt: "After", class: "cmp-after" });
    const before = h("img", { src: a, alt: "Before", class: "cmp-before" });
    const range = h("input", { type: "range", min: 0, max: 100, value: 50, "aria-label": "Compare before and after" });
    range.addEventListener("input", () => wrap.style.setProperty("--x", `${range.value}%`));
    wrap.append(after, before, h("span", { class: "cmp-line" }), h("span", { class: "cmp-tag l" }, "Before"), h("span", { class: "cmp-tag r" }, "After"), range);
    const zoom = h("button", { class: "link-btn", type: "button", onclick: () => { wrap.classList.toggle("zoomed"); zoom.textContent = wrap.classList.contains("zoomed") ? "Fit" : "Zoom 2× to check detail"; } }, "Zoom 2× to check detail");
    return h("div", { class: "cmp-wrap" }, wrap, zoom);
  }
  const loadImg = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(i); i.src = src; });

  function selectFile(i) {
    selected = Math.max(0, Math.min(i, files.length - 1));
    $$("#fileList .file").forEach((li) => li.classList.toggle("active", +li.dataset.i === selected));
    const panel = $("#pv");
    if (!files.length) { panel.hidden = true; panel.innerHTML = ""; return; }
    panel.hidden = false;
    renderPreview(panel, files[selected]);
  }

  /* ---------- Files ---------- */
  function addFiles(list) {
    let rejected = 0;
    for (const f of list) {
      if (!acceptsFile(current, f.name)) { rejected++; continue; }
      if (!current.multiple) files = [];
      files.push(f);
    }
    if (rejected) toast(`${rejected} file${rejected > 1 ? "s" : ""} skipped — not supported by ${current.name}`);
    selected = Math.max(0, files.length - 1);
    renderFiles();
  }

  function renderFiles() {
    const ol = $("#fileList");
    ol.innerHTML = "";
    const canMove = current?.reorder && files.length > 1;
    files.forEach((f, i) => {
      const ext = extOf(f.name);
      const li = h("li", { class: `file${canMove ? " reorderable" : ""}`, draggable: canMove ? "true" : null, "data-i": i, style: `animation-delay:${Math.min(i, 8) * 0.04}s` });
      li.innerHTML = `
        <span class="handle">${canMove ? ui("grip").replace("<svg", '<svg width="16" height="16" fill="currentColor"') : ""}</span>
        <span class="thumb"><span class="ext" style="--ext:${EXT_COLOR[ext] || "#554e43"}">${esc(ext.slice(0, 4))}</span></span>
        <div class="meta"><div class="name" title="${esc(f.name)}"></div><div class="size">${fmtBytes(f.size)}</div></div>
        <div class="tools">
          <button class="mini move" data-act="up" aria-label="Move up" ${i === 0 ? "disabled" : ""}>${ui("up")}</button>
          <button class="mini move" data-act="down" aria-label="Move down" ${i === files.length - 1 ? "disabled" : ""}>${ui("down")}</button>
        </div>
        <button class="mini del" data-act="del" aria-label="Remove ${esc(f.name)}">${ui("x")}</button>`;
      $(".name", li).textContent = f.name;
      ol.append(li);
      preview(f).then((pv) => {
        const src = pv.thumb || pv.pages?.[0];
        if (src && li.isConnected) { const t = $(".thumb", li); t.classList.add("has-img"); t.prepend(h("img", { src, alt: "" })); }
        if (li.isConnected) $(".size", li).textContent = pvMeta(pv, f);
      });
    });
    const drop = $("#drop");
    drop.classList.toggle("compact", files.length > 0);
    if (current && files.length) {
      $(".drop-title", drop).innerHTML = current.multiple ? "Add more files or <u>browse</u>" : "Replace file — drop or <u>browse</u>";
      $("#pickFiles").lastChild.textContent = current.multiple ? "Add files" : "Replace";
    } else $("#pickFiles").lastChild.textContent = "Choose files";
    validate();
    selectFile(Math.min(selected, files.length - 1));
  }

  function wireFiles() {
    const drop = $("#drop");
    const input = $("#fileInput");
    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    $("#pickFiles").addEventListener("click", () => input.click());
    $("#pickCamera").addEventListener("click", () => $("#cameraInput").click());
    input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
    $("#cameraInput").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
    let depth = 0;
    drop.addEventListener("dragenter", (e) => { if (e.dataTransfer.types.includes("Files")) { depth++; drop.classList.add("over"); } });
    drop.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; drop.classList.remove("over"); } });
    drop.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); });
    drop.addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); depth = 0; drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
    const sheet = $(".ws-sheet");
    sheet.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files") && !$("#wsBody").hidden) e.preventDefault(); });
    sheet.addEventListener("drop", (e) => { if (e.dataTransfer.files.length && !$("#wsBody").hidden) { e.preventDefault(); addFiles(e.dataTransfer.files); } });

    const ol = $("#fileList");
    ol.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) { const li = e.target.closest(".file"); if (li && +li.dataset.i !== selected) selectFile(+li.dataset.i); return; }
      const i = +b.closest(".file").dataset.i;
      if (b.dataset.act === "del") files.splice(i, 1);
      else {
        const j = b.dataset.act === "up" ? i - 1 : i + 1;
        if (j < 0 || j >= files.length) return;
        [files[i], files[j]] = [files[j], files[i]];
      }
      renderFiles();
    });
    let from = null;
    ol.addEventListener("dragstart", (e) => {
      const li = e.target.closest(".file");
      if (!li) return;
      from = +li.dataset.i;
      li.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(from));
    });
    ol.addEventListener("dragover", (e) => {
      if (from == null) return;
      e.preventDefault();
      e.stopPropagation();
      $$(".file", ol).forEach((x) => x.classList.remove("drop-target"));
      e.target.closest(".file")?.classList.add("drop-target");
    });
    ol.addEventListener("drop", (e) => {
      if (from == null) return;
      e.preventDefault();
      e.stopPropagation();
      const li = e.target.closest(".file");
      if (li) {
        const [m] = files.splice(from, 1);
        files.splice(+li.dataset.i, 0, m);
      }
      from = null;
      renderFiles();
    });
    ol.addEventListener("dragend", () => { from = null; $$(".file", ol).forEach((x) => x.classList.remove("dragging", "drop-target")); });
  }

  /* ---------- Run ---------- */
  function run() {
    if (!validate()) return;
    const t = current;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    if (asset) fd.append("asset", asset, asset.name);
    for (const [k, v] of Object.entries(formValues())) fd.append(k, String(v));

    showPane("progress");
    const bar = $("#progBar");
    const label = $("#progLabel");
    const barWrap = bar.parentElement;
    bar.style.width = "0";
    barWrap.classList.toggle("indeterminate", !files.length);
    label.textContent = files.length ? "Uploading…" : "Fetching…";

    xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/tools/${t.id}`);
    xhr.responseType = "blob";
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) bar.style.width = `${(e.loaded / e.total) * 100}%`; };
    xhr.upload.onload = () => {
      barWrap.classList.add("indeterminate");
      label.textContent = { markdown: "Reading & rewriting as Markdown…", media: "Encoding — this can take a minute…", image: "Developing your image…" }[t.category] || "Working on it…";
    };
    xhr.onerror = () => { xhr = null; showError("Network error — is the server still running?"); };
    xhr.onload = async () => {
      const r = xhr;
      xhr = null;
      if (current !== t) return;
      const ctype = r.getResponseHeader("Content-Type") || "";
      if (r.status >= 400) {
        let msg = `Server returned ${r.status}`;
        try { const j = JSON.parse(await r.response.text()); msg = j.error || j.detail || msg; } catch {}
        return showError(msg);
      }
      if (ctype.includes("application/json") && !r.getResponseHeader("Content-Disposition")) {
        const data = JSON.parse(await r.response.text());
        if (data.kind === "markdown") return showMarkdown(data.docs);
        if (data.kind === "html") return showHtml(data);
      }
      const cd = r.getResponseHeader("Content-Disposition") || "";
      const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
      const name = m ? decodeURIComponent(m[1]) : "result";
      const dec = (k) => { const v = r.getResponseHeader(k); try { return v ? decodeURIComponent(v) : ""; } catch { return v || ""; } };
      showFile(r.response, name, {
        before: +r.getResponseHeader("X-Original-Size"), after: +r.getResponseHeader("X-Result-Size"),
        note: dec("X-Folio-Note"), met: r.getResponseHeader("X-Folio-Target-Met"),
      });
    };
    xhr.send(fd);
  }

  function download(blob, name) {
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    lastBlobUrl = URL.createObjectURL(blob);
    const a = h("a", { href: lastBlobUrl, download: name });
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function share(blob, name) {
    const file = new File([blob], name, { type: blob.type || "application/octet-stream" });
    try {
      if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: name });
      else download(blob, name);
    } catch (e) { if (e.name !== "AbortError") toast("Sharing isn't available — downloading instead"), download(blob, name); }
  }
  const canShareFiles = () => !!navigator.canShare && navigator.canShare({ files: [new File([""], "x.txt", { type: "text/plain" })] });

  function nextChips(result) {
    const tool = current;
    const ids = (NEXT[tool.id] || DEFAULT_NEXT).filter((id) => id !== tool.id && byId[id]).slice(0, 4);
    return h("div", { class: "next" }, h("p", {}, result ? `Continue with ${result.name}` : "Continue with"),
      h("div", { class: "chips" }, ids.map((id) => h("a", {
        class: "chip", href: `#/tool/${id}`, style: `--c:${catColor(byId[id].category)}`,
        onclick: () => { carry = result || null; },
      }, byId[id].name))));
  }

  function resetBtn(label = "Start over") {
    return h("button", { class: "btn btn-ghost", type: "button", onclick: () => openTool(current) }, label);
  }

  function resultActions(blob, name) {
    const dl = h("button", { class: "btn btn-accent", type: "button", onclick: () => download(blob, name) }, `Download ${extOf(name).toUpperCase()}`);
    dl.insertAdjacentHTML("beforeend", ui("dl"));
    const row = h("div", { class: "done-actions" }, dl);
    if (canShareFiles()) {
      const sh = h("button", { class: "btn btn-ink", type: "button", onclick: () => share(blob, name) }, "Share");
      sh.insertAdjacentHTML("beforeend", ui("share"));
      row.append(sh);
    }
    return row;
  }

  function showFile(blob, name, info = {}) {
    const res = $("#wsResult");
    res.innerHTML = "";
    const card = h("div", { class: "done" });
    card.append(h("div", { class: "stamp", html: `<div>${ui("check")}Done</div>` }), h("div", {},
      h("h3", {}, "Your file is ready."),
      h("div", { class: "fname" }, `${name} · ${fmtBytes(blob.size)}`)));
    const outFile = new File([blob], name, { type: blob.type });
    const pvBox = h("div", { class: "pv result-pv" });
    card.append(pvBox);
    const input = files.length === 1 ? files[0] : null;
    (async () => {
      const cmp = input ? await compareView(input, outFile) : null;
      if (cmp && pvBox.isConnected) {
        pvBox.append(h("div", { class: "pv-head" }, h("b", {}, "Before / after"), h("span", { class: "pv-meta" }, "Drag the handle to compare")), cmp);
        if (extOf(name) === "pdf") { const more = h("div", { class: "pv" }); pvBox.after(more); renderPreview(more, outFile, { label: "All pages" }); }
      } else if (pvBox.isConnected) renderPreview(pvBox, outFile, { label: "Result preview" });
    })();
    if (info.before && info.after && info.after !== info.before && /compress|size|form-photo/.test(current.id)) {
      const pct = Math.round((1 - info.after / info.before) * 100);
      card.append(h("div", { class: "savings" },
        h("div", { class: "savings-row" }, h("span", {}, `${fmtBytes(info.before)} → ${fmtBytes(info.after)}`),
          h("b", {}, pct > 0 ? `−${pct}%` : `+${-pct}%`)),
        h("div", { class: "bars" }, h("span", { style: `width:${pct > 0 ? 100 : Math.max(2, 100 * info.before / info.after)}%` }),
          h("span", { class: "after", style: `width:${Math.max(2, pct > 0 ? 100 - pct : 100)}%` }))));
    }
    if (info.note) card.append(h("div", { class: `note${info.met === "0" ? " warn" : ""}` }, info.note));
    card.append(resultActions(blob, name));
    $(".done-actions", card).append(resetBtn());
    card.append(nextChips({ blob, name }));
    res.append(card);
    showPane("result");
    if (!mobile()) download(blob, name);
  }

  function showError(msg) {
    const res = $("#wsResult");
    res.innerHTML = "";
    res.append(h("div", { class: "error-card" },
      h("div", { class: "stamp", html: `<div>${ui("alert")}Hold on</div>` }),
      h("h3", {}, "That didn't work."),
      h("p", {}, msg),
      h("button", { class: "btn btn-ink", type: "button", onclick: () => showPane("body") }, "Back to the file")));
    showPane("result");
  }

  /* Markdown viewer */
  function highlightMd(src) {
    return esc(src)
      .replace(/^(#{1,6} .*)$/gm, '<span class="h">$1</span>')
      .replace(/^(\s*(?:[-*+]|\d+\.) )/gm, '<span class="l">$1</span>')
      .replace(/^(\|.*\|)$/gm, '<span class="t">$1</span>');
  }
  function renderProse(md) {
    if (window.marked && window.DOMPurify) return DOMPurify.sanitize(marked.parse(md, { gfm: true }));
    return `<pre>${esc(md)}</pre>`;
  }

  function showMarkdown(docs) {
    const res = $("#wsResult");
    res.innerHTML = "";
    let active = 0;
    let mode = "rendered";
    const view = h("div", { class: "md-view" });
    const title = h("h3", {});
    const tabs = h("div", { class: "doc-tabs", role: "tablist" });
    const pane = h("div", { class: "md-pane" });
    const stats = h("span", { class: "md-stats" });
    const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": "View" },
      ...[["rendered", "Preview"], ["raw", "Markdown"]].map(([v, l]) =>
        h("label", {}, h("input", { type: "radio", name: "mdmode", value: v, checked: v === mode, onchange: () => { mode = v; paint(); } }), h("span", {}, l))));
    const paint = () => {
      const d = docs[active];
      const md = d.markdown || "";
      title.innerHTML = "";
      title.append(current.category === "markdown" ? "Markdown, ready." : "Here it is.", h("small", {}, d.name));
      const words = (md.match(/\S+/g) || []).length;
      stats.textContent = `${md.split("\n").length} lines · ${words.toLocaleString()} words`;
      pane.innerHTML = "";
      if (!md.trim()) pane.append(h("div", { class: "prose" }, h("p", {}, "No text could be extracted. If this is a scan, run OCR first.")));
      else if (mode === "raw") pane.append(h("pre", { class: "md-raw", html: highlightMd(md) }));
      else pane.append(h("article", { class: "prose", html: renderProse(md) }));
      $$("button", tabs).forEach((b, i) => b.setAttribute("aria-selected", String(i === active)));
    };
    if (docs.length > 1) docs.forEach((d, i) => tabs.append(h("button", { role: "tab", type: "button", onclick: () => { active = i; paint(); } }, d.name)));
    const blobOf = (d) => new Blob([d.markdown], { type: "text/markdown" });
    const actions = h("div", { class: "md-actions" },
      h("button", { class: "btn btn-ink", type: "button", onclick: async () => {
        try { await navigator.clipboard.writeText(docs[active].markdown); toast("Copied to clipboard"); } catch { toast("Copy blocked by the browser"); }
      } }, "Copy"),
      h("button", { class: "btn btn-accent", type: "button", onclick: () => download(blobOf(docs[active]), docs[active].name) }, "Download .md"));
    if (canShareFiles()) actions.append(h("button", { class: "btn btn-ghost", type: "button", onclick: () => share(blobOf(docs[active]), docs[active].name) }, "Share"));
    if (docs.length > 1) {
      actions.append(h("button", { class: "btn btn-ghost", type: "button", onclick: () => {
        const all = docs.map((d) => `<!-- ${d.name} -->\n\n${d.markdown}`).join("\n\n---\n\n");
        download(new Blob([all], { type: "text/markdown" }), "combined.md");
      } }, "Download combined"));
    }
    actions.append(resetBtn("New conversion"));
    view.append(h("div", { class: "md-top" }, title, actions), tabs,
      h("div", { class: "md-frame" }, h("div", { class: "md-bar" }, seg, stats), pane),
      nextChips({ blob: blobOf(docs[0]), name: docs[0].name }));
    res.append(view);
    paint();
    showPane("result");
  }

  function showHtml(data) {
    const res = $("#wsResult");
    res.innerHTML = "";
    const frame = h("iframe", { class: "html-frame", sandbox: "", title: "Comparison report" });
    frame.srcdoc = data.html;
    res.append(h("div", { class: "md-view" },
      h("div", { class: "md-top" }, h("h3", {}, "Comparison ready.", h("small", {}, data.filename)),
        h("div", { class: "md-actions" },
          h("button", { class: "btn btn-accent", type: "button", onclick: () => download(new Blob([data.html], { type: "text/html" }), data.filename) }, "Download report"),
          resetBtn("Compare again"))),
      h("div", { class: "md-frame" }, frame)));
    showPane("result");
  }

  /* ---------- PWA: install, service worker, share target ---------- */
  function wirePwa() {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
    window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredInstall = e; $("#installBtn").hidden = false; });
    window.addEventListener("appinstalled", () => { $("#installBtn").hidden = true; toast("Folio is installed"); });
    $("#installBtn").addEventListener("click", async () => {
      if (!deferredInstall) return;
      deferredInstall.prompt();
      await deferredInstall.userChoice;
      deferredInstall = null;
      $("#installBtn").hidden = true;
    });
  }

  // Files shared to the installed app (Android share sheet) arrive via the service worker cache.
  async function receiveShared() {
    if (!location.hash.startsWith("#/shared") || !("caches" in window)) return;
    const cache = await caches.open("folio-shared");
    const keys = await cache.keys();
    const got = [];
    for (const k of keys) {
      const r = await cache.match(k);
      const name = decodeURIComponent(r.headers.get("X-Name") || "shared");
      got.push(new File([await r.blob()], name, { type: r.headers.get("Content-Type") || "" }));
      await cache.delete(k);
    }
    history.replaceState("", "", location.pathname);
    if (!got.length) return;
    const fits = DATA.tools.filter((t) => t.min_files > 0 && got.every((f) => t.accept.length && acceptsFile(t, f.name)));
    const sorted = [...fits.filter((t) => t.popular), ...fits.filter((t) => !t.popular)];
    $("#popularShelf .shelf-head h2").textContent = `What should I do with ${got.length > 1 ? `${got.length} files` : got[0].name}?`;
    $("#popularRail").replaceChildren(...sorted.map((t, i) => {
      const tile = tileFor(t, i);
      tile.addEventListener("click", () => { carry = { blob: got[0], name: got[0].name }; pendingShared = got; });
      return tile;
    }));
    $("#popularShelf").scrollIntoView({ behavior: "smooth" });
  }
  let pendingShared = null;

  /* ---------- Global wiring ---------- */
  function wire() {
    wireFiles();
    wirePwa();
    $("#runBtn").addEventListener("click", run);
    $("#cancelRun").addEventListener("click", () => { if (xhr) { xhr.abort(); xhr = null; } showPane("body"); });
    $("#workspace").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeTool(); });
    $("[data-close-browse]").addEventListener("click", () => { history.pushState("", "", "#/"); closeBrowse(); });
    $("#clearRecent").addEventListener("click", () => { store.set("folio.recent", []); renderShelves(); });
    window.addEventListener("hashchange", () => {
      route();
      if (pendingShared && current && pendingShared.length > 1 && current.multiple) {
        files = pendingShared.filter((f) => acceptsFile(current, f.name));
        renderFiles();
      }
      pendingShared = null;
    });

    const search = $("#search");
    search.addEventListener("input", () => {
      filter(search.value);
      if (search.value && window.scrollY < 300 && !mobile()) $("#catalog").scrollIntoView({ behavior: "smooth" });
    });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { const first = $$(".card").find((c) => !c.hidden); if (first) location.hash = first.getAttribute("href"); }
      if (e.key === "Escape") { search.value = ""; filter(""); search.blur(); }
    });
    search.addEventListener("blur", () => {
      if (mobile() && !search.value) { document.body.classList.remove("searching"); if (location.hash === "#/search") history.replaceState("", "", "#/"); setTab("home"); }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && current) { closeTool(); return; }
      if (e.key === "/" && !current && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) { e.preventDefault(); search.focus(); }
    });
    const mast = $(".masthead");
    window.addEventListener("scroll", () => mast.classList.toggle("scrolled", window.scrollY > 8), { passive: true });
  }

  window.Folio = { $, $$, h, esc, icon, ui, toast, download, share, canShareFiles, fmtBytes, catColor, get byId() { return byId; }, mobile, store };
  wire();
  load();
})();
