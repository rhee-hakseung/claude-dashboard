/* 선 아이콘(16×16). icon("name") → <svg> 문자열. [data-icon] 요소는 fillIcons()가 채운다. */
(() => {
  const P = {
    search: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/>',
    plus: '<path d="M8 3v10M3 8h10"/>',
    terminal: '<path d="m3 4.5 3.5 3.5L3 11.5M8.5 12H13"/>',
    folder: '<path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.8l1.5 1.8h4.7A1.5 1.5 0 0 1 14 6.3v5.2a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/>',
    pencil: '<path d="m10.5 2.8 2.7 2.7L6 12.7l-3.2.5.5-3.2z"/>',
    chevron: '<path d="m4 6 4 4 4-4"/>',
    star: '<path d="m8 2 1.8 3.7 4.1.6-3 2.9.7 4.1L8 11.4l-3.6 1.9.7-4.1-3-2.9 4.1-.6z"/>',
    trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8"/>',
    grip: '<circle cx="6" cy="4" r="1.1"/><circle cx="10" cy="4" r="1.1"/><circle cx="6" cy="8" r="1.1"/><circle cx="10" cy="8" r="1.1"/><circle cx="6" cy="12" r="1.1"/><circle cx="10" cy="12" r="1.1"/>',
    sun: '<circle cx="8" cy="8" r="3"/><path d="M8 1.5V3M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1"/>',
    moon: '<path d="M13 9.5A5.5 5.5 0 0 1 6.5 3 5.5 5.5 0 1 0 13 9.5z"/>',
    branch: '<circle cx="4.5" cy="3.5" r="1.5"/><circle cx="4.5" cy="12.5" r="1.5"/><circle cx="11.5" cy="5.5" r="1.5"/><path d="M4.5 5v6M11.5 7c0 2.6-3.4 2-6 3.4"/>',
    clock: '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3l2 1.5"/>',
    disk: '<path d="m2.5 9.5 1.6-5.2a1.5 1.5 0 0 1 1.4-1.1h5a1.5 1.5 0 0 1 1.4 1.1l1.6 5.2v2A1.5 1.5 0 0 1 12 13H4a1.5 1.5 0 0 1-1.5-1.5zM2.5 9.5h11"/>',
    chat: '<path d="M2.5 4A1.5 1.5 0 0 1 4 2.5h8A1.5 1.5 0 0 1 13.5 4v5.5A1.5 1.5 0 0 1 12 11H7l-3 2.5V11a1.5 1.5 0 0 1-1.5-1.5z"/>',
    x: '<path d="m4 4 8 8M12 4l-8 8"/>',
    jump: '<path d="m5 11 6-6M6 5h5v5"/>',
    play: '<path d="m5.5 3.5 6.5 4.5-6.5 4.5z"/>',
    check: '<path d="m3.5 8.5 3 3 6-7"/>',
    bell: '<path d="M4 11V7.5a4 4 0 0 1 8 0V11l1.2 1.5H2.8zM6.5 14h3"/>',
    spin: '<path d="M8 2.5a5.5 5.5 0 1 0 5.5 5.5"/><path d="M8 5.2A2.8 2.8 0 1 1 5.2 8" opacity=".5"/>',
    archive: '<path d="M2.5 3h11v3h-11zM3.5 6v6a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V6M6.5 8.8h3"/>',
    grid: '<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/>',
  };
  window.icon = (name) => `<svg class="i" viewBox="0 0 16 16" aria-hidden="true">${P[name] || ""}</svg>`;
  window.fillIcons = (root = document) => {
    root.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
  };
})();
