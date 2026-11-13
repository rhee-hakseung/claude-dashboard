/* 뷰(JSON) → HTML 문자열. DOM도 상태도 만지지 않는다(app.js가 끼워 넣는다). */
(() => {
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  const ENDED_SHOWN = 3;   // 펼치기 전까지 카드에 보이는 끝난 세션 수

  /** 검색어와 맞는 부분을 <mark>로 감싼다(대소문자 무시). */
  function hi(text, q) {
    text = String(text ?? "");
    if (!q) return esc(text);
    const at = text.toLowerCase().indexOf(q);
    if (at < 0) return esc(text);
    return esc(text.slice(0, at)) + "<mark>" + esc(text.slice(at, at + q.length)) + "</mark>" + esc(text.slice(at + q.length));
  }

  function age(sec) {
    if (!(sec >= 0)) return "";
    if (sec < 60) return "방금";
    if (sec < 3600) return Math.floor(sec / 60) + "분 전";
    if (sec < 86400) return Math.floor(sec / 3600) + "시간 전";
    return Math.floor(sec / 86400) + "일 전";
  }
  const ageOf = (mtime) => (mtime ? age(Date.now() / 1000 - mtime) : "");

  function size(bytes) {
    if (bytes == null) return "";
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
    if (bytes < 1024 ** 3) return Math.round(bytes / 1024 / 1024) + " MB";
    return (bytes / 1024 ** 3).toFixed(1) + " GB";
  }

  const dot = (it) => `<span class="dot ${it.hl ? "hl" : it.kind === "ended" ? "ENDED" : it.state}"></span>`;
  const star = (it) => `<button class="icon-btn hover ${it.fav ? "on" : ""}" data-act="fav" data-sid="${esc(it.id)}"
      title="${it.fav ? "즐겨찾기에서 빼기" : "즐겨찾기에 추가"}">${icon("star")}</button>`;

  /** 세션 한 줄의 주 버튼: 라이브 = 점프(백그라운드는 열기), 끝남 = 재개. */
  function mainButton(it) {
    if (it.kind === "live") {
      const label = it.host === "bg" ? "열기" : it.host === "orphan" ? "이어 열기" : "점프";
      const off = !it.jumpable ? ' disabled title="창을 찾을 수 없습니다"'
        : it.host === "orphan" ? ' title="창이 닫힌 세션입니다. 새 탭에서 이어 엽니다"' : "";
      return `<button class="btn soft" data-act="jump" data-sid="${esc(it.id)}"${off}>${icon("jump")}${label}</button>`;
    }
    return it.resumable
      ? `<button class="btn quiet" data-act="resume" data-path="${esc(it.path)}">${icon("play")}재개</button>` : "";
  }

  function liveRow(it, q) {
    return `<div class="row live ${it.hl ? "hl" : ""}" draggable="true" data-sid="${esc(it.id)}">
      ${dot(it)}<span class="row-title" title="${esc(it.title)}">${hi(it.title, q)}</span>
      ${it.shell ? '<span class="row-note">+ 백그라운드 실행 중</span>' : ""}
      ${it.host === "orphan" ? '<span class="row-note">창 닫힘</span>' : ""}
      ${it.disagree ? '<span class="row-note" title="상태 출처 불일치">?</span>' : ""}
      <span class="pill ${it.hl ? "hl" : it.state}">${esc(it.label)}</span>${star(it)}${mainButton(it)}</div>`;
  }

  function endedRow(it, q) {
    const notes = [it.stub && "빈 기록", it.dup && "다른 프로젝트에 같은 기록 있음", it.resuming && "재개 중…"].filter(Boolean);
    const plain = !it.stub && !it.dup;
    return `<div class="row ended ${it.stub ? "stub" : ""}" ${plain ? 'draggable="true"' : ""} data-sid="${esc(it.id)}">
      ${dot(it)}<span class="row-title" title="${esc(it.title)}">${hi(it.title, q)}</span>
      ${notes.map((n) => `<span class="row-note">${n}</span>`).join("")}
      <span class="row-age" data-mtime="${it.mtime}">${ageOf(it.mtime)}</span>
      ${it.resuming ? "" : (plain ? star(it) : "") + `<button class="icon-btn hover danger" data-act="trash"
        data-path="${esc(it.path)}" title="휴지통으로 보내기">${icon("trash")}</button>` + mainButton(it)}</div>`;
  }

  /** 필터·검색을 적용한 카드 한 장의 보이는 줄들. `show`가 false면 카드를 통째로 숨긴다. */
  function visible(p, ui) {
    const q = ui.q, f = ui.filter;
    const projHit = !!q && [p.title, p.name, p.sub].join(" ").toLowerCase().includes(q);
    const hit = (it) => !q || projHit || it.title.toLowerCase().includes(q);
    const live = f === "ENDED" ? [] : p.live.filter((it) => (f === "all" || f === it.state) && hit(it));
    let ended = f === "all" || f === "ENDED" ? p.ended.filter(hit) : [];
    let hidden = 0;
    if (!q && f === "all" && !ui.expanded.has(p.name) && ended.length > ENDED_SHOWN) {
      hidden = ended.length - ENDED_SHOWN;
      ended = ended.slice(0, ENDED_SHOWN);
    }
    const narrowed = !!q || f !== "all";
    return { live, ended, hidden, show: !narrowed || live.length + ended.length > 0 || (projHit && f === "all") };
  }

  function spark(values) {
    if (!values) return "";
    const max = Math.max(1, ...values);
    return `<span class="spark" title="최근 ${values.length}일 활동 (오른쪽이 오늘)">${values.map((v) =>
      `<i class="${v ? "" : "z"}" style="height:${v ? Math.max(3, Math.round((v / max) * 22)) : 2}px"></i>`).join("")}</span>`;
  }

  function meta(p) {
    const st = p.stats || {}, chips = [];
    if (p.last_activity) chips.push(`<span class="chip" title="마지막 활동">${icon("clock")}<span data-mtime="${p.last_activity}">${ageOf(p.last_activity)}</span></span>`);
    chips.push(`<span class="chip" title="세션 수 (진행 중 + 끝남)">${icon("chat")}${p.live.length + p.ended.length}</span>`);
    if (st.size != null) chips.push(`<span class="chip" title="폴더 용량">${icon("disk")}${size(st.size)}</span>`);
    if (st.git) {
      chips.push(`<span class="chip" title="git 브랜치">${icon("branch")}${esc(st.git.branch || "?")}</span>`);
      chips.push(st.git.dirty ? `<span class="chip warn" title="커밋하지 않은 변경">변경 ${st.git.dirty}</span>`
        : `<span class="chip ok" title="커밋하지 않은 변경 없음">${icon("check")}</span>`);
    } else if ("git" in st) chips.push('<span class="chip faint" title="git 저장소가 아닙니다">git 없음</span>');
    return `<div class="card-meta">${chips.join("")}</div>`;
  }

  function mini(p) {
    const n = (s) => p.live.filter((it) => it.state === s).length, out = [];
    if (n("WAITING")) out.push(`<span><span class="dot ${p.lit ? "hl" : "WAITING"}"></span>${n("WAITING")}</span>`);
    if (n("WORKING")) out.push(`<span><span class="dot WORKING"></span>${n("WORKING")}</span>`);
    if (p.ended.length) out.push(`<span><span class="dot ENDED"></span>${p.ended.length}</span>`);
    return `<span class="mini">${out.join("")}</span>`;
  }

  function card(p, ui) {
    const v = visible(p, ui);
    if (!v.show) return "";
    const head = `<div class="card-head">
      <span class="grip" title="끌어서 순서 바꾸기">${icon("grip")}</span>
      <div class="card-titles"><span class="card-title" title="${esc(p.path)}">${hi(p.title, ui.q)}</span>
        <span class="card-sub">${hi(p.sub, ui.q)}</span></div>
      <button class="icon-btn rename" data-act="rename" title="이름 바꾸기">${icon("pencil")}</button>
      ${p.folded ? mini(p) : ""}
      <button class="icon-btn fold" data-act="fold" title="${p.folded ? "펼치기" : "접기"}">${icon("chevron")}</button></div>`;
    let body = "";
    if (!p.folded) {
      const rows = v.live.map((it) => liveRow(it, ui.q)).join("") + v.ended.map((it) => endedRow(it, ui.q)).join("")
        + (v.hidden ? `<button class="more" data-act="more">${icon("chevron")}끝난 세션 ${v.hidden}개 더 보기</button>` : "")
        + (ui.expanded.has(p.name) && !ui.q && ui.filter === "all" && p.ended.length > ENDED_SHOWN
          ? `<button class="more" data-act="more">접기</button>` : "")
        + p.jobs.map((j) => `<div class="job">${esc(j)}</div>`).join("");
      body = meta(p) + `<div class="card-actions">
        <button class="btn primary" data-act="new">${icon("plus")}새 claude</button>
        <button class="btn" data-act="ps">${icon("terminal")}${esc(R.labels.shell)}</button>
        <button class="btn" data-act="exp">${icon("folder")}${esc(R.labels.files)}</button>${spark((p.stats || {}).spark)}</div>`
        + (rows ? `<div class="rows">${rows}</div>` : "");
    }
    return `<article class="card ${p.folded ? "folded" : ""} ${p.lit ? "lit" : ""}" data-name="${esc(p.name)}"
      data-alias="${esc(p.alias)}">${head}${body}</article>`;
  }

  function summary(view, ui) {
    const s = view.summary;
    const tiles = [["WAITING", "waiting", "bell", s.waiting, "나를 기다림"], ["WORKING", "working", "spin", s.working, "작업 중"],
      ["ENDED", "ended", "archive", s.ended, "끝난 세션"], ["all", "all", "grid", s.projects, "프로젝트"]];
    return tiles.map(([key, tone, ic, num, label]) => `<button class="tile tone-${tone} ${ui.filter === key && key !== "all" ? "active" : ""}"
      data-act="filter" data-filter="${key}" title="${key === "all" ? "전체 보기" : label + "만 보기"}">
      <span class="tile-icon">${icon(ic)}</span><span><div class="tile-num">${num}</div><div class="tile-label">${label}</div></span>
      ${key === "WAITING" && s.attention ? `<span class="tile-badge"><span class="dot hl"></span>새로 ${s.attention}</span>` : ""}</button>`).join("");
  }

  function favs(view) {
    const items = view.favorites.map((it) => `<div class="fav" draggable="true" data-sid="${esc(it.id)}" data-fav="1">
      ${dot(it)}<div class="fav-main"><div class="fav-title" title="${esc(it.title)}">${esc(it.title)}</div>
      <div class="fav-sub">${esc(it.project)} · ${it.kind === "live" ? esc(it.label) : `<span data-mtime="${it.mtime}">${ageOf(it.mtime)}</span>`}</div></div>
      ${mainButton(it)}<button class="icon-btn" data-act="unfav" data-sid="${esc(it.id)}" title="즐겨찾기에서 빼기">${icon("x")}</button></div>`);
    return `<div class="section-head">${icon("star")}즐겨찾기<span class="count">${items.length || ""}</span>
      <span class="hint">세션을 끌어다 놓거나 ☆를 눌러 추가</span></div>
      <div class="fav-list ${items.length ? "" : "empty"}" id="fav-list">${items.join("") || "주의 깊게 볼 세션을 여기로 끌어다 놓으세요"}</div>`;
  }

  // 버튼 이름은 OS마다 다르다(뷰의 labels: Windows는 PowerShell·탐색기, 맥은 터미널·Finder)
  window.R = { esc, age, ageOf, summary, favs, card, labels: { shell: "PowerShell", files: "탐색기" } };
})();
