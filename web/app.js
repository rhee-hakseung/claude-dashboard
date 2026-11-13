/* 상태·갱신·버튼·끌어다 놓기. 화면 그리기는 render.js, 실제 동작은 Python(web_api.Api). */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const ui = { filter: "all", q: "", expanded: new Set() };
  const FILTER_LABEL = { WAITING: "나를 기다림", WORKING: "작업 중", ENDED: "끝난 세션" };
  let view = null, rev = -1, pending = null, busy = false, lastMsg = 0, drag = null, toastTimer = 0;

  const api = () => (window.pywebview && window.pywebview.api) || null;
  const call = (name, ...args) => { const a = api(); if (a) a[name](...args).then(poll); };

  /* ── 갱신 ───────────────────────────────────────────── */
  async function poll() {
    const a = api();
    if (!a) return;
    const v = await a.view(rev);
    if (v) { pending = v; flush(); }
  }
  /** 이름을 고치거나 끌고 있는 동안은 다시 그리지 않는다 — 끝나면 밀린 최신 뷰를 그린다. */
  function flush() {
    if (busy || !pending) return;
    view = pending; rev = view.rev; pending = null;
    render();
    if (view.msg_seq !== lastMsg) { if (lastMsg || view.msg_seq) toast(view.message); lastMsg = view.msg_seq; }
  }

  function render() {
    if (!view) return;
    applyTheme();
    $("#root-path").textContent = view.root || "";
    if (view.labels) R.labels = view.labels;
    $("#summary").innerHTML = R.summary(view, ui);
    $("#favs").innerHTML = R.favs(view);
    const cards = view.projects.map((p) => R.card(p, ui)).join("");
    $("#grid").innerHTML = cards;
    const narrowed = ui.q || ui.filter !== "all";
    $("#grid-head").innerHTML = `<div class="section-head">프로젝트<span class="count">${view.summary.projects}</span>`
      + (ui.filter !== "all" ? `<span class="hint">‘${FILTER_LABEL[ui.filter]}’만 보는 중</span>
         <button class="btn" data-act="filter" data-filter="all">전체 보기</button>` : "") + "</div>";
    const empty = $("#empty");
    empty.hidden = !!cards;
    empty.textContent = cards ? "" : !view.projects.length ? "세션을 읽는 중…" : narrowed ? "조건에 맞는 세션이 없습니다" : "";
    $("#status").textContent = view.status || "";
  }

  function applyTheme() {
    const sys = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const theme = (view && view.theme) || sys;
    document.documentElement.dataset.theme = theme;
    $("#theme").innerHTML = icon(theme === "dark" ? "sun" : "moon");
  }

  function toast(text) {
    if (!text) return;
    const el = $("#toast");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 4500);
  }

  /* ── 버튼 ───────────────────────────────────────────── */
  const favIds = () => view.favorites.map((f) => f.id);
  const ACT = {
    jump: (el) => call("jump", el.dataset.sid),
    resume: (el) => call("resume", el.dataset.path),
    trash: (el) => call("trash", el.dataset.path),
    new: (el, name) => call("new_claude", name),
    ps: (el, name) => call("powershell", name),
    exp: (el, name) => call("explorer", name),
    fold: (el, name) => call("fold", name, !el.closest(".card").classList.contains("folded")),
    fav: (el) => { const id = el.dataset.sid, ids = favIds(); call("set_favorites", ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]); },
    unfav: (el) => call("set_favorites", favIds().filter((x) => x !== el.dataset.sid)),
    more: (el, name) => { ui.expanded.has(name) ? ui.expanded.delete(name) : ui.expanded.add(name); render(); },
    filter: (el) => { const f = el.dataset.filter; ui.filter = ui.filter === f ? "all" : f; render(); },
    rename: (el) => startRename(el.closest(".card")),
  };
  document.addEventListener("click", (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const cardEl = el.closest(".card");
    ACT[el.dataset.act](el, cardEl ? cardEl.dataset.name : null);
  });
  document.addEventListener("dblclick", (ev) => { const t = ev.target.closest(".card-title"); if (t) startRename(t.closest(".card")); });

  function startRename(cardEl) {
    const titles = $(".card-titles", cardEl), name = cardEl.dataset.name;
    const input = Object.assign(document.createElement("input"), { className: "title-edit", value: cardEl.dataset.alias || $(".card-title", cardEl).textContent,
      placeholder: "표시 이름 (비우면 폴더 이름)" });
    busy = true;
    titles.replaceWith(input);
    input.focus(); input.select();
    let done = false;
    const finish = (save) => { if (done) return; done = true; busy = false; if (save) call("rename", name, input.value); render(); flush(); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); });
    input.addEventListener("blur", () => finish(true));
  }

  /* ── 검색·테마·단축키 ───────────────────────────────── */
  const q = $("#q");
  q.addEventListener("input", () => { ui.q = q.value.trim().toLowerCase(); $("#q-clear").hidden = !q.value; $("#q-hint").hidden = !!q.value; render(); });
  $("#q-clear").addEventListener("click", () => { q.value = ""; q.dispatchEvent(new Event("input")); q.focus(); });
  $("#theme").addEventListener("click", () => call("set_theme", document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey && e.key.toLowerCase() === "k") || (e.key === "/" && document.activeElement.tagName !== "INPUT")) { e.preventDefault(); q.focus(); q.select(); }
    else if (e.key === "Escape" && document.activeElement === q) { q.value = ""; q.dispatchEvent(new Event("input")); q.blur(); }
  });

  /* ── 끌어다 놓기: 세션 → 즐겨찾기(추가·순서), 카드 손잡이 → 프로젝트 순서 ───── */
  document.addEventListener("mousedown", (e) => { const g = e.target.closest(".grip"); if (g) g.closest(".card").draggable = true; });
  document.addEventListener("mouseup", () => document.querySelectorAll(".card[draggable]").forEach((c) => c.removeAttribute("draggable")));
  const clearMarks = () => document.querySelectorAll(".drop-before, .drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after"));

  document.addEventListener("dragstart", (e) => {
    const cardEl = e.target.closest && e.target.closest(".card[draggable]"), row = e.target.closest && e.target.closest(".row, .fav");
    if (row && row.dataset.sid && !(cardEl && e.target === cardEl)) drag = { type: "session", sid: row.dataset.sid, el: row };
    else if (cardEl) drag = { type: "card", name: cardEl.dataset.name, el: cardEl };
    else return;
    busy = true;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", drag.sid || drag.name);
    document.body.classList.add("drag-" + drag.type);
    // 즐겨찾기 칸이 화면에 온전히 안 보이면 맨 위에 놓는 곳을 띄운다(끌기가 시작된 뒤에 — 시작 순간 화면을 바꾸면 끌기가 끊긴다)
    const r = $("#fav-list").getBoundingClientRect(), far = drag.type === "session" && (r.top < 70 || r.bottom > innerHeight);
    setTimeout(() => { if (!drag) return; drag.el.classList.add("dragging"); document.body.classList.toggle("fav-far", far); });
  });
  document.addEventListener("dragover", (e) => {
    if (!drag) return;
    clearMarks();
    $("#fav-drop").classList.toggle("over", !!e.target.closest("#fav-drop"));
    if (drag.type === "session" && e.target.closest("#fav-drop")) e.preventDefault();
    else if (drag.type === "session" && e.target.closest("#favs")) {
      e.preventDefault();
      const over = e.target.closest(".fav");
      if (over && over !== drag.el) over.classList.add("drop-before");
    } else if (drag.type === "card") {
      const over = e.target.closest(".card");
      if (!over || over === drag.el) return;
      e.preventDefault();
      const r = over.getBoundingClientRect(), single = getComputedStyle($("#grid")).gridTemplateColumns.split(" ").length < 2;
      const after = single ? e.clientY > r.top + r.height / 2 : e.clientX > r.left + r.width / 2;
      over.classList.add(after ? "drop-after" : "drop-before");
    }
  });
  document.addEventListener("drop", (e) => {
    if (!drag) return;
    e.preventDefault();
    if (drag.type === "session" && e.target.closest("#favs, #fav-drop")) {
      const ids = favIds().filter((x) => x !== drag.sid), over = e.target.closest(".fav");
      const at = over && over !== drag.el ? ids.indexOf(over.dataset.sid) : -1;
      ids.splice(at < 0 ? ids.length : at, 0, drag.sid);
      call("set_favorites", ids);
    } else if (drag.type === "card") {
      const mark = $(".card.drop-before, .card.drop-after");
      if (mark) {
        const names = [...document.querySelectorAll("#grid .card")].map((c) => c.dataset.name).filter((n) => n !== drag.name);
        const all = view.projects.map((p) => p.name).filter((n) => n !== drag.name);   // 필터로 숨은 카드도 순서에 남긴다
        const at = all.indexOf(mark.dataset.name) + (mark.classList.contains("drop-after") ? 1 : 0);
        all.splice(names.length ? at : all.length, 0, drag.name);
        call("reorder", all);
      }
    }
  });
  document.addEventListener("dragend", () => {
    if (!drag) return;
    drag.el.classList.remove("dragging");
    drag.el.removeAttribute(drag.type === "card" ? "draggable" : "data-x");
    document.body.classList.remove("drag-session", "drag-card", "fav-far");
    $("#fav-drop").classList.remove("over");
    clearMarks();
    drag = null; busy = false;
    flush();
  });

  /* ── 시작 ───────────────────────────────────────────── */
  fillIcons();
  setInterval(poll, 300);
  setInterval(() => document.querySelectorAll("[data-mtime]").forEach((el) => { el.textContent = R.ageOf(+el.dataset.mtime); }), 20000);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  window.addEventListener("pywebviewready", poll);
  const mock = new URLSearchParams(location.search).get("mock");   // 화면 확인용: ?mock=<뷰를 담은 js 파일>
  if (mock) { const s = document.createElement("script"); s.src = mock; s.onload = () => { pending = window.MOCK_VIEW; flush(); }; document.head.append(s); }
  else applyTheme();
})();
