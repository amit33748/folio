/* Folio PDF editor: tap text to change it in its original font, add text/images/signatures,
   whiteout, highlight, freehand ink and form filling. Coordinates are kept in PDF points. */
(() => {
  "use strict";
  const F = () => window.Folio;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const h = (...a) => F().h(...a);

  const ed = $("#editor");
  const pagesEl = $("#edPages");
  const stage = $("#edStage");
  const props = $("#edProps");

  let doc = null; // {sid, name, pages}
  let tool = null;
  let mode = "text";
  let zoom = 1;
  let base = 1; // px per pt at zoom 1
  let pageEls = [];
  const edits = new Map(); // spanId -> {page, span, text, size, color}
  let items = []; // added objects
  const fields = new Map(); // name -> {page, value}
  const undos = [];
  const fonts = new Map(); // xref -> css family or null
  let selected = null;
  let pendingPlace = null; // {kind:'image', data, w, h}
  let seq = 0;
  let signInk = "#1b1915";

  /* ---------- helpers ---------- */
  const px = (pt) => pt * base * zoom;
  const pt = (pxv) => pxv / (base * zoom);
  const dirty = () => edits.size + items.length + fields.size > 0;
  const markDirty = () => { $("#edSave").disabled = !dirty(); };

  function cssFamily(span) {
    const web = fonts.get(span.xref);
    const n = (span.font || "").toLowerCase();
    const serif = span.serif || /times|georgia|garamond|cambria|serif|minion|book|roman|palatino/.test(n);
    const mono = span.mono || /courier|mono|consol/.test(n);
    const stack = mono ? '"Liberation Mono", "Courier New", monospace'
      : serif ? '"Liberation Serif", "Times New Roman", Georgia, serif'
      : n.includes("calibri") ? 'Calibri, Carlito, "Segoe UI", Arial, sans-serif'
      : 'Arial, "Liberation Sans", Helvetica, sans-serif';
    return web ? `"${web}", ${stack}` : stack;
  }

  function loadFonts() {
    const seen = new Set();
    for (const p of doc.pages) for (const s of p.spans) {
      if (!s.web || seen.has(s.xref)) continue;
      seen.add(s.xref);
      const fam = `pdf-${doc.sid.slice(0, 6)}-${s.xref}`;
      const face = new FontFace(fam, `url(/api/editor/${doc.sid}/font/${s.xref})`);
      face.load().then((f) => { document.fonts.add(f); fonts.set(s.xref, fam); restyleSpans(); }).catch(() => fonts.set(s.xref, null));
    }
  }

  function sampleBg(pageIndex, bbox) {
    const pe = pageEls[pageIndex];
    if (!pe?.canvas) return "#ffffff";
    const k = pe.canvas.width / doc.pages[pageIndex].w;
    const ctx = pe.canvas.getContext("2d", { willReadFrequently: true });
    const pts = [[bbox[0] - 2, bbox[1] + 1], [bbox[2] + 2, bbox[1] + 1], [bbox[0] - 2, bbox[3] - 1], [bbox[2] + 2, bbox[3] - 1]];
    const cols = pts.map(([x, y]) => {
      const d = ctx.getImageData(Math.max(0, Math.min(pe.canvas.width - 1, x * k)), Math.max(0, Math.min(pe.canvas.height - 1, y * k)), 1, 1).data;
      return [d[0], d[1], d[2]];
    }).sort((a, b) => (b[0] + b[1] + b[2]) - (a[0] + a[1] + a[2]));
    const c = cols[1];
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  /* ---------- open / close ---------- */
  function open(t, file) {
    tool = t;
    reset();
    ed.hidden = false;
    document.body.classList.add("locked", "ws-open");
    $("#edName").textContent = t.name;
    ed.style.setProperty("--c", F().catColor(t.category));
    showOpen(true);
    if (file) load(file);
  }

  function close(push = true) {
    if (ed.hidden) return;
    if (dirty() && push && !confirm("Discard your edits?")) return;
    ed.hidden = true;
    document.body.classList.remove("locked", "ws-open");
    if (doc) fetch(`/api/editor/${doc.sid}`, { method: "DELETE" }).catch(() => {});
    reset();
    if (push && location.hash.startsWith("#/tool/")) history.pushState("", "", location.pathname);
  }

  function reset() {
    doc = null; edits.clear(); items = []; fields.clear(); undos.length = 0; pageEls = []; selected = null; pendingPlace = null;
    pagesEl.innerHTML = ""; props.hidden = true; zoom = 1;
    $("#edSave").disabled = true;
    $("#edTools").hidden = true;
    stage.hidden = true;
    setMode("text");
  }

  function showOpen(on) {
    $("#edOpen").hidden = !on;
    stage.hidden = on;
    $("#edTools").hidden = on;
  }

  async function load(file, password) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    if (password) fd.append("password", password);
    $(".drop-title", $("#edDrop")).textContent = "Opening…";
    let res;
    try {
      res = await fetch("/api/editor/open", { method: "POST", body: fd });
    } catch {
      F().toast("Network error");
      return resetDrop();
    }
    const data = await res.json();
    if (!res.ok) {
      if (data.needs_password) {
        const pw = prompt("This PDF is password protected. Enter the password:");
        if (pw) return load(file, pw);
      }
      F().toast(data.error || "Couldn't open the PDF");
      return resetDrop();
    }
    doc = data;
    $("#edName").textContent = data.name;
    showOpen(false);
    loadFonts();
    build();
    const nf = data.pages.reduce((n, p) => n + p.widgets.length, 0);
    if (tool.id === "sign-pdf") { setMode("sign"); openSig(); }
    else if (tool.id === "fill-form") F().toast(nf ? `${nf} form field${nf > 1 ? "s" : ""} found — tap to fill` : "No fillable fields — use Add text instead");
    else F().toast("Tap any text to edit it");
  }
  function resetDrop() { $(".drop-title", $("#edDrop")).textContent = "Open a PDF to edit"; }

  /* ---------- build pages ---------- */
  function fitBase() {
    const avail = Math.min(stage.clientWidth - (F().mobile() ? 16 : 64), 980);
    const maxW = Math.max(...doc.pages.map((p) => p.w));
    base = avail / maxW;
  }

  function build() {
    pagesEl.innerHTML = "";
    pageEls = [];
    fitBase();
    doc.pages.forEach((p, i) => {
      const wrap = h("div", { class: "ed-page", "data-page": i });
      const img = h("img", { alt: `Page ${i + 1}`, draggable: "false", decoding: "async" });
      const layer = h("div", { class: "ed-layer" });
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.classList.add("ed-ink");
      layer.append(svg);
      wrap.append(img, layer, h("span", { class: "ed-pno" }, `${i + 1} / ${doc.pages.length}`));
      pagesEl.append(wrap);
      const pe = { wrap, img, layer, svg, spans: [], widgets: [], canvas: null, src: "" };
      pageEls.push(pe);
      img.addEventListener("load", () => {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext("2d").drawImage(img, 0, 0);
        pe.canvas = c;
      });
      p.spans.forEach((s) => {
        if (!s.editable) return;
        const el = h("div", { class: "ed-span", "data-id": s.id, title: `${s.font} · ${s.size}pt` });
        el.addEventListener("click", (e) => { if (mode === "text") { e.stopPropagation(); editSpan(i, s, el); } });
        layer.append(el);
        pe.spans.push({ s, el });
      });
      p.widgets.forEach((w) => {
        const el = widgetEl(i, w);
        if (el) { layer.append(el); pe.widgets.push({ w, el }); }
      });
      wireLayer(i, pe);
    });
    layout();
    lazyImages();
  }

  function lazyImages() {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) setImg(+e.target.dataset.page);
    }, { root: stage, rootMargin: "800px 0px" });
    pageEls.forEach((pe) => io.observe(pe.wrap));
  }

  function setImg(i) {
    const pe = pageEls[i];
    const want = Math.min(2400, Math.ceil((px(doc.pages[i].w) * (window.devicePixelRatio || 1)) / 200) * 200);
    const src = `/api/editor/${doc.sid}/page/${i}.jpg?w=${want}`;
    if (pe.src !== src && (!pe.srcW || want > pe.srcW)) { pe.img.src = src; pe.src = src; pe.srcW = want; }
  }

  function place(el, rect) {
    el.style.left = `${px(rect[0])}px`;
    el.style.top = `${px(rect[1])}px`;
    el.style.width = `${px(rect[2] - rect[0])}px`;
    el.style.height = `${px(rect[3] - rect[1])}px`;
  }

  function layout() {
    doc.pages.forEach((p, i) => {
      const pe = pageEls[i];
      pe.wrap.style.width = `${px(p.w)}px`;
      pe.wrap.style.height = `${px(p.h)}px`;
      pe.svg.setAttribute("viewBox", `0 0 ${p.w} ${p.h}`);
      pe.spans.forEach(({ s, el }) => {
        place(el, s.bbox);
        styleSpan(el, s);
      });
      pe.widgets.forEach(({ w, el }) => { place(el, w.rect); el.style.fontSize = `${Math.max(9, px(Math.min(12, (w.rect[3] - w.rect[1]) * 0.7)))}px`; });
      if (pe.src) setImg(i);
    });
    items.forEach(layoutItem);
    $("#zoomLabel").textContent = `${Math.round(zoom * 100)}%`;
  }

  function styleSpan(el, s) {
    const e = edits.get(s.id);
    el.style.fontFamily = cssFamily(s);
    el.style.fontWeight = s.bold ? "700" : "400";
    el.style.fontStyle = s.italic ? "italic" : "normal";
    el.style.fontSize = `${px(e?.size || s.size)}px`;
    el.style.lineHeight = `${px(s.bbox[3] - s.bbox[1])}px`;
    el.style.color = e?.color || s.color;
  }
  function restyleSpans() { pageEls.forEach((pe) => pe.spans.forEach(({ s, el }) => styleSpan(el, s))); }

  /* ---------- edit existing text ---------- */
  function editSpan(pageIndex, s, el) {
    select(null);
    const cur = edits.get(s.id);
    el.classList.add("editing", "edited");
    el.style.background = el.style.background || sampleBg(pageIndex, s.bbox);
    el.contentEditable = "plaintext-only";
    if (el.contentEditable !== "plaintext-only") el.contentEditable = "true";
    el.textContent = cur ? cur.text : s.text;
    el.focus();
    const r = document.createRange();
    r.selectNodeContents(el);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    showProps({
      label: `${s.font || "Unknown font"} · ${s.size}pt`,
      size: cur?.size || s.size, color: cur?.color || s.color,
      onSize: (v) => { upsert(pageIndex, s, { size: v }); styleSpan(el, s); },
      onColor: (v) => { upsert(pageIndex, s, { color: v }); styleSpan(el, s); },
      onDelete: () => { el.textContent = ""; finish(); },
      onRevert: () => { edits.delete(s.id); el.textContent = ""; el.classList.remove("edited"); el.style.background = ""; styleSpan(el, s); el.blur(); markDirty(); },
      deleteLabel: "Delete text",
    });
    const finish = () => {
      el.contentEditable = "false";
      el.classList.remove("editing");
      const text = el.textContent;
      if (text === s.text && !edits.get(s.id)?.size && !edits.get(s.id)?.color) {
        edits.delete(s.id); el.textContent = ""; el.classList.remove("edited"); el.style.background = "";
      } else {
        const prev = edits.get(s.id);
        upsert(pageIndex, s, { text });
        undos.push(() => {
          if (prev) edits.set(s.id, prev); else edits.delete(s.id);
          el.textContent = prev ? prev.text : "";
          el.classList.toggle("edited", !!prev);
          if (!prev) el.style.background = "";
          styleSpan(el, s);
        });
      }
      markDirty();
    };
    el.onblur = () => { setTimeout(() => { if (!props.contains(document.activeElement)) { finish(); hideProps(); } }, 0); };
    el.onkeydown = (e) => { if (e.key === "Escape") { el.textContent = cur ? cur.text : s.text; el.blur(); } if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); el.blur(); } };
  }

  function upsert(page, s, patch) {
    const prev = edits.get(s.id) || { page, span: s.id, text: s.text };
    edits.set(s.id, { ...prev, ...patch });
    markDirty();
  }

  /* ---------- properties bar ---------- */
  function showProps(o) {
    props.innerHTML = "";
    props.hidden = false;
    const size = h("input", { type: "number", min: 4, max: 300, step: "0.5", value: Number(o.size).toFixed(1), "aria-label": "Font size", inputmode: "decimal" });
    size.addEventListener("input", () => { const v = parseFloat(size.value); if (v > 0) o.onSize(v); });
    const color = h("input", { type: "color", value: o.color?.startsWith("#") ? o.color : "#000000", "aria-label": "Colour" });
    color.addEventListener("input", () => o.onColor(color.value));
    props.append(h("span", { class: "p-font", title: o.label }, o.label));
    if (o.size != null) props.append(h("label", { class: "p-size" }, "Size", size, "pt"));
    if (o.color != null) props.append(h("label", { class: "p-color" }, color));
    if (o.onRevert) props.append(h("button", { type: "button", class: "p-btn", onmousedown: (e) => e.preventDefault(), onclick: o.onRevert }, "Revert"));
    if (o.onDelete) props.append(h("button", { type: "button", class: "p-btn danger", onmousedown: (e) => e.preventDefault(), onclick: o.onDelete }, o.deleteLabel || "Delete"));
    props.append(h("button", { type: "button", class: "p-btn ok", onclick: () => { document.activeElement?.blur(); hideProps(); select(null); } }, "Done"));
  }
  function hideProps() { props.hidden = true; }

  /* ---------- added items ---------- */
  function nearestSpan(pageIndex, x, y) {
    let best = null, bd = Infinity;
    for (const s of doc.pages[pageIndex].spans) {
      const cx = Math.max(s.bbox[0], Math.min(x, s.bbox[2]));
      const cy = Math.max(s.bbox[1], Math.min(y, s.bbox[3]));
      const d = Math.hypot(cx - x, cy - y);
      if (d < bd) { bd = d; best = s; }
    }
    return bd < 200 ? best : null;
  }

  function addItem(it, record = true) {
    it.id = ++seq;
    items.push(it);
    const pe = pageEls[it.page];
    const el = h("div", { class: `ed-item ed-${it.type}` });
    it.el = el;
    if (it.type === "text") {
      el.textContent = it.text;
      el.contentEditable = "plaintext-only";
      if (el.contentEditable !== "plaintext-only") el.contentEditable = "true";
      el.addEventListener("input", () => { it.text = el.innerText; });
      el.addEventListener("focus", () => select(it));
    } else if (it.type === "image") {
      el.append(h("img", { src: it.data, alt: "", draggable: "false" }));
    } else if (it.type === "line") {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      path.setAttribute("points", it.points.map((p) => p.join(",")).join(" "));
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", it.color);
      path.setAttribute("stroke-width", it.width);
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("stroke-linejoin", "round");
      pe.svg.append(path);
      it.svgEl = path;
    }
    if (it.type !== "line") {
      const grip = h("span", { class: "ed-move", title: "Drag to move" });
      const del = h("button", { class: "ed-del", type: "button", "aria-label": "Delete", onclick: (e) => { e.stopPropagation(); removeItem(it); } });
      del.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>';
      el.append(grip, del);
      if (it.type !== "text") el.append(h("span", { class: "ed-resize", title: "Drag to resize" }));
      dragify(it, grip, "move");
      if (it.type !== "text") dragify(it, el, "move");
      const rs = $(".ed-resize", el);
      if (rs) dragify(it, rs, "resize");
      el.addEventListener("pointerdown", (e) => { e.stopPropagation(); select(it); });
      pe.layer.append(el);
    }
    layoutItem(it);
    if (record) undos.push(() => removeItem(it, false));
    markDirty();
    return it;
  }

  function removeItem(it, record = true) {
    items = items.filter((x) => x !== it);
    it.el?.remove();
    it.svgEl?.remove();
    if (selected === it) { selected = null; hideProps(); }
    if (record) undos.push(() => { items.push(it); (it.type === "line" ? pageEls[it.page].svg : pageEls[it.page].layer).append(it.type === "line" ? it.svgEl : it.el); layoutItem(it); markDirty(); });
    markDirty();
  }

  function layoutItem(it) {
    if (it.type === "line") return;
    const el = it.el;
    if (it.type === "text") {
      el.style.left = `${px(it.x)}px`;
      el.style.top = `${px(it.y)}px`;
      el.style.fontSize = `${px(it.size)}px`;
      el.style.color = it.color;
      el.style.fontFamily = it.like ? cssFamily(it.like) : { helv: "Arial, sans-serif", tiro: '"Times New Roman", serif', cour: "monospace" }[it.font] || "Arial";
      el.style.fontWeight = it.like?.bold ? "700" : "400";
      el.style.fontStyle = it.like?.italic ? "italic" : "normal";
      return;
    }
    place(el, it.rect);
    if (it.type === "rect") el.style.background = it.fill;
    if (it.type === "highlight") el.style.background = it.color;
  }

  function select(it) {
    $$(".ed-item.sel").forEach((e) => e.classList.remove("sel"));
    selected = it;
    if (!it) { hideProps(); return; }
    it.el?.classList.add("sel");
    if (it.type === "text") {
      showProps({
        label: it.like ? `Matched: ${it.like.font}` : "New text",
        size: it.size, color: it.color,
        onSize: (v) => { it.size = v; layoutItem(it); },
        onColor: (v) => { it.color = v; layoutItem(it); },
        onDelete: () => removeItem(it),
      });
    } else if (it.type === "rect") {
      showProps({ label: "Whiteout box", color: it.fill, onColor: (v) => { it.fill = v; layoutItem(it); }, onDelete: () => removeItem(it) });
    } else {
      showProps({ label: it.type === "image" ? (it.sig ? "Signature" : "Image") : "Highlight", onDelete: () => removeItem(it) });
    }
  }

  function dragify(it, handle, kind) {
    handle.addEventListener("pointerdown", (e) => {
      if (it.type === "text" && kind === "move" && handle === it.el) return;
      e.preventDefault();
      e.stopPropagation();
      select(it);
      handle.setPointerCapture(e.pointerId);
      const sx = e.clientX, sy = e.clientY;
      const start = it.type === "text" ? [it.x, it.y] : [...it.rect];
      const ratio = it.type === "image" ? (start[3] - start[1]) / (start[2] - start[0]) : null;
      const move = (ev) => {
        const dx = pt(ev.clientX - sx), dy = pt(ev.clientY - sy);
        if (it.type === "text") { it.x = start[0] + dx; it.y = start[1] + dy; }
        else if (kind === "move") it.rect = [start[0] + dx, start[1] + dy, start[2] + dx, start[3] + dy];
        else {
          const w = Math.max(8, start[2] - start[0] + dx);
          it.rect = [start[0], start[1], start[0] + w, start[1] + (ratio ? w * ratio : Math.max(4, start[3] - start[1] + dy))];
        }
        layoutItem(it);
      };
      const up = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up); };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
  }

  /* ---------- page interactions per mode ---------- */
  function localPt(pe, e) {
    const r = pe.wrap.getBoundingClientRect();
    return [pt(e.clientX - r.left), pt(e.clientY - r.top)];
  }

  function wireLayer(i, pe) {
    pe.layer.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".ed-item, .ed-field")) return;
      const [x, y] = localPt(pe, e);
      if (pendingPlace) {
        const p = pendingPlace;
        pendingPlace = null;
        stage.classList.remove("placing");
        const w = p.w, hgt = p.h;
        const it = addItem({ type: "image", page: i, rect: [x - w / 2, y - hgt / 2, x + w / 2, y + hgt / 2], data: p.data, sig: p.sig });
        select(it);
        return;
      }
      if (mode === "add") {
        const like = nearestSpan(i, x, y);
        const it = addItem({ type: "text", page: i, x, y: y - (like?.size || 12) * 0.6, text: "Type here", size: like?.size || 12,
          color: like?.color || "#000000", like, font: "helv" });
        setTimeout(() => {
          it.el.focus();
          const r = document.createRange(); r.selectNodeContents(it.el);
          const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        }, 0);
        return;
      }
      if (["whiteout", "highlight", "draw"].includes(mode)) {
        e.preventDefault();
        pe.layer.setPointerCapture(e.pointerId);
        let it;
        if (mode === "draw") {
          it = addItem({ type: "line", page: i, points: [[x, y]], color: signInk, width: 1.6 }, false);
        } else {
          it = addItem(mode === "whiteout"
            ? { type: "rect", page: i, rect: [x, y, x, y], fill: sampleBg(i, [x, y, x, y]) }
            : { type: "highlight", page: i, rect: [x, y, x, y], color: "rgba(255, 214, 10, .42)" }, false);
        }
        const move = (ev) => {
          const [mx, my] = localPt(pe, ev);
          if (it.type === "line") {
            it.points.push([+mx.toFixed(1), +my.toFixed(1)]);
            it.svgEl.setAttribute("points", it.points.map((p) => p.join(",")).join(" "));
          } else {
            it.rect = [Math.min(x, mx), Math.min(y, my), Math.max(x, mx), Math.max(y, my)];
            layoutItem(it);
          }
        };
        const up = () => {
          pe.layer.removeEventListener("pointermove", move);
          pe.layer.removeEventListener("pointerup", up);
          const tiny = it.type === "line" ? it.points.length < 2 : (it.rect[2] - it.rect[0] < 3 || it.rect[3] - it.rect[1] < 3);
          if (tiny) removeItem(it, false);
          else undos.push(() => removeItem(it, false));
          markDirty();
        };
        pe.layer.addEventListener("pointermove", move);
        pe.layer.addEventListener("pointerup", up);
        return;
      }
      select(null);
    });
  }

  /* ---------- form fields ---------- */
  function widgetEl(i, w) {
    const set = (v) => { fields.set(w.name, { page: i, value: v }); markDirty(); };
    let el;
    if (w.type === "checkbox" || w.type === "radiobutton") {
      el = h("input", { type: "checkbox", class: "ed-field", checked: !!w.value, title: w.label });
      el.addEventListener("change", () => set(el.checked));
    } else if (w.options) {
      el = h("select", { class: "ed-field", title: w.label });
      for (const o of w.options) el.append(h("option", { value: o, selected: o === w.value }, o));
      el.addEventListener("change", () => set(el.value));
    } else if (w.type === "text") {
      const multi = w.rect[3] - w.rect[1] > 30;
      el = h(multi ? "textarea" : "input", { class: "ed-field", title: w.label, placeholder: w.label, value: multi ? null : (w.value || "") });
      if (multi) el.value = w.value || "";
      el.addEventListener("input", () => set(el.value));
    } else return null;
    return el;
  }

  /* ---------- modes & toolbar ---------- */
  function setMode(m) {
    mode = m;
    $$("#edTools [data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
    stage.dataset.mode = m;
    pendingPlace = null;
    stage.classList.remove("placing");
  }

  function wireTools() {
    $("#edTools").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.act === "undo") {
        const fn = undos.pop();
        if (fn) { fn(); markDirty(); } else F().toast("Nothing to undo");
        return;
      }
      const m = b.dataset.mode;
      if (m === "sign") { setMode("sign"); openSig(); return; }
      if (m === "image") {
        setMode("image");
        const inp = h("input", { type: "file", accept: "image/*" });
        inp.addEventListener("change", () => inp.files[0] && readImage(inp.files[0], false));
        inp.click();
        return;
      }
      setMode(m);
      F().toast({ text: "Tap text to edit it", add: "Tap where the new text should go", whiteout: "Drag to cover an area",
        highlight: "Drag over text to highlight", draw: "Draw with your finger or mouse" }[m]);
    });
  }

  function readImage(file, sig) {
    const r = new FileReader();
    r.onload = () => armPlace(r.result, sig);
    r.readAsDataURL(file);
  }

  function armPlace(dataUrl, sig) {
    const img = new Image();
    img.onload = () => {
      const w = sig ? 150 : Math.min(220, img.naturalWidth * 0.75);
      pendingPlace = { data: dataUrl, w, h: w * img.naturalHeight / img.naturalWidth, sig };
      stage.classList.add("placing");
      F().toast(sig ? "Tap where the signature goes" : "Tap where the image goes");
    };
    img.src = dataUrl;
  }

  /* ---------- signature pad ---------- */
  const sigModal = $("#sigModal");
  const canvas = $("#sigCanvas");
  const cx = canvas.getContext("2d");
  let strokes = 0;

  function openSig() {
    sigModal.hidden = false;
    cx.clearRect(0, 0, canvas.width, canvas.height);
    strokes = 0;
    const saved = F().store.get("folio.sig", null);
    if (saved) {
      const im = new Image();
      im.onload = () => { cx.drawImage(im, 0, 0, canvas.width, canvas.height); strokes = 1; };
      im.src = saved;
    }
  }

  function wireSig() {
    let drawing = false, last = null;
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height]; };
    canvas.addEventListener("pointerdown", (e) => { drawing = true; last = pos(e); canvas.setPointerCapture(e.pointerId); strokes++; });
    canvas.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      const p = pos(e);
      cx.strokeStyle = signInk; cx.lineWidth = 5 * (e.pressure > 0 && e.pointerType === "pen" ? 0.5 + e.pressure : 1);
      cx.lineCap = "round"; cx.lineJoin = "round";
      cx.beginPath(); cx.moveTo(...last); cx.lineTo(...p); cx.stroke();
      last = p;
    });
    ["pointerup", "pointercancel"].forEach((ev) => canvas.addEventListener(ev, () => (drawing = false)));
    $("#sigClear").addEventListener("click", () => { cx.clearRect(0, 0, canvas.width, canvas.height); strokes = 0; F().store.set("folio.sig", null); });
    $("#inkSwatches").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      signInk = b.dataset.ink;
      $$("#inkSwatches button").forEach((x) => x.classList.toggle("on", x === b));
    });
    $$('input[name="sigmode"]').forEach((r) => r.addEventListener("change", () => {
      $$(".sig-pane").forEach((p) => (p.hidden = p.dataset.pane !== r.value));
    }));
    $("#sigText").addEventListener("input", () => $$("#sigFonts button").forEach((b) => (b.textContent = $("#sigText").value || "Signature")));
    $("#sigFonts").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      $$("#sigFonts button").forEach((x) => x.classList.toggle("on", x === b));
    });
    $$("#sigFonts button").forEach((b) => (b.style.fontFamily = `"${b.dataset.font}", cursive`));
    sigModal.addEventListener("click", (e) => { if (e.target === sigModal || e.target.closest("[data-close-modal]")) sigModal.hidden = true; });
    $("#sigUse").addEventListener("click", async () => {
      const m = $('input[name="sigmode"]:checked').value;
      let url;
      if (m === "draw") {
        if (!strokes) return F().toast("Draw your signature first");
        url = trimCanvas(canvas);
        F().store.set("folio.sig", canvas.toDataURL("image/png"));
      } else if (m === "type") {
        const text = $("#sigText").value.trim();
        if (!text) return F().toast("Type your name first");
        const font = $("#sigFonts .on").dataset.font;
        await document.fonts.load(`80px "${font}"`);
        const c = document.createElement("canvas");
        const g = c.getContext("2d");
        g.font = `80px "${font}"`;
        c.width = Math.ceil(g.measureText(text).width + 40); c.height = 130;
        g.font = `80px "${font}"`; g.fillStyle = signInk; g.textBaseline = "middle";
        g.fillText(text, 20, 68);
        url = c.toDataURL("image/png");
      } else {
        const f = $("#sigUpload").files[0];
        if (!f) return F().toast("Choose an image");
        url = await knockOutWhite(f);
      }
      sigModal.hidden = true;
      armPlace(url, true);
    });
  }

  function trimCanvas(c) {
    const g = c.getContext("2d");
    const d = g.getImageData(0, 0, c.width, c.height).data;
    let x0 = c.width, y0 = c.height, x1 = 0, y1 = 0;
    for (let y = 0; y < c.height; y += 2) for (let x = 0; x < c.width; x += 2) {
      if (d[(y * c.width + x) * 4 + 3] > 10) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    }
    if (x1 <= x0) return c.toDataURL("image/png");
    const pad = 8;
    const o = document.createElement("canvas");
    o.width = x1 - x0 + pad * 2; o.height = y1 - y0 + pad * 2;
    o.getContext("2d").drawImage(c, x0 - pad, y0 - pad, o.width, o.height, 0, 0, o.width, o.height);
    return o.toDataURL("image/png");
  }

  function knockOutWhite(file) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement("canvas");
        const k = Math.min(1, 1200 / img.naturalWidth);
        c.width = img.naturalWidth * k; c.height = img.naturalHeight * k;
        const g = c.getContext("2d");
        g.drawImage(img, 0, 0, c.width, c.height);
        const id = g.getImageData(0, 0, c.width, c.height);
        for (let i = 0; i < id.data.length; i += 4) {
          const l = (id.data[i] + id.data[i + 1] + id.data[i + 2]) / 3;
          if (l > 200) id.data[i + 3] = 0; else if (l > 150) id.data[i + 3] = (200 - l) * 5;
        }
        g.putImageData(id, 0, 0);
        resolve(trimCanvas(c));
      };
      img.src = URL.createObjectURL(file);
    });
  }

  /* ---------- save ---------- */
  async function save() {
    document.activeElement?.blur();
    await new Promise((r) => setTimeout(r, 30));
    const ops = [];
    for (const [id, e] of edits) ops.push({ type: "edit-text", page: e.page, span: id, text: e.text, size: e.size, color: e.color });
    for (const it of items) {
      if (it.type === "text") ops.push({ type: "add-text", page: it.page, x: it.x, y: it.y, text: it.text, size: it.size, color: it.color, like: it.like?.id, font: it.font });
      else if (it.type === "image") ops.push({ type: "image", page: it.page, rect: it.rect, data: it.data });
      else if (it.type === "rect") ops.push({ type: "rect", page: it.page, rect: it.rect, fill: rgbToHex(it.fill) });
      else if (it.type === "highlight") ops.push({ type: "highlight", page: it.page, rect: it.rect, color: "#ffd60a" });
      else if (it.type === "line") ops.push({ type: "line", page: it.page, points: it.points, color: it.color, width: it.width });
    }
    for (const [name, f] of fields) ops.push({ type: "field", page: f.page, name, value: f.value });
    const btn = $("#edSave");
    btn.disabled = true;
    btn.textContent = "Saving…";
    try {
      const res = await fetch(`/api/editor/${doc.sid}/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ops }) });
      if (!res.ok) {
        let msg = `Save failed (${res.status})`;
        try { const j = await res.json(); msg = j.error || j.detail || msg; } catch {}
        throw new Error(msg);
      }
      const blob = await res.blob();
      const name = `${doc.name}_edited.pdf`;
      let note = res.headers.get("X-Folio-Note") || ""; try { note = decodeURIComponent(note); } catch {}
      showSaved(blob, name, note);
    } catch (e) {
      F().toast(e.message);
    } finally {
      btn.textContent = "Save PDF";
      markDirty();
    }
  }

  function rgbToHex(c) {
    const m = String(c).match(/\d+/g);
    if (!m || c.startsWith("#")) return c;
    return "#" + m.slice(0, 3).map((v) => (+v).toString(16).padStart(2, "0")).join("");
  }

  function showSaved(blob, name, note) {
    const card = h("div", { class: "modal", role: "dialog", "aria-modal": "true" });
    const inner = h("div", { class: "modal-card saved" },
      h("div", { class: "stamp", html: `<div>${F().ui("check")}Saved</div>` }),
      h("h3", {}, "Your edited PDF is ready."),
      h("p", { class: "fname" }, `${name} · ${F().fmtBytes(blob.size)}`),
      note ? h("p", { class: "note" }, note) : null);
    const row = h("footer", {},
      h("button", { class: "btn btn-ghost", type: "button", onclick: () => card.remove() }, "Keep editing"),
      h("button", { class: "btn btn-accent", type: "button", onclick: () => F().download(blob, name) }, "Download"));
    if (F().canShareFiles()) row.append(h("button", { class: "btn btn-ink", type: "button", onclick: () => F().share(blob, name) }, "Share"));
    inner.append(row);
    card.append(inner);
    card.addEventListener("click", (e) => { if (e.target === card) card.remove(); });
    ed.append(card);
    if (!F().mobile()) F().download(blob, name);
  }

  /* ---------- wiring ---------- */
  function wire() {
    const drop = $("#edDrop"), input = $("#edFile");
    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") input.click(); });
    input.addEventListener("change", () => { if (input.files[0]) load(input.files[0]); input.value = ""; });
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) load(f); });
    $("#edClose").addEventListener("click", () => close(true));
    $("#edSave").addEventListener("click", save);
    $("#zoomIn").addEventListener("click", () => { zoom = Math.min(3, +(zoom + 0.25).toFixed(2)); layout(); });
    $("#zoomOut").addEventListener("click", () => { zoom = Math.max(0.5, +(zoom - 0.25).toFixed(2)); layout(); });
    window.addEventListener("resize", () => { if (doc && !ed.hidden) { fitBase(); layout(); } });
    document.addEventListener("keydown", (e) => {
      if (ed.hidden) return;
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.target.isContentEditable && e.target.tagName !== "INPUT") { e.preventDefault(); undos.pop()?.(); markDirty(); }
      if ((e.key === "Delete" || e.key === "Backspace") && selected && !e.target.isContentEditable && e.target.tagName !== "INPUT") removeItem(selected);
    });
    window.addEventListener("beforeunload", (e) => { if (!ed.hidden && dirty()) { e.preventDefault(); e.returnValue = ""; } });
    wireTools();
    wireSig();
  }

  wire();
  window.FolioEditor = { open, close };
})();
