(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#0a1018");
      tg.setBackgroundColor("#05080c");
    } catch (_) {}
  }

  const $ = (id) => document.getElementById(id);
  const statusPill = $("statusPill");
  const userLine = $("userLine");
  const gateCard = $("gateCard");

  let canAccess = false;

  function initData() {
    return (tg && tg.initData) || "";
  }

  async function api(path, opts = {}) {
    const headers = {
      "X-Telegram-Init-Data": initData(),
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    };
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    return { res, data };
  }

  function setStatus(kind, text) {
    statusPill.className = "pill " + kind;
    statusPill.textContent = text;
  }

  function toast(msg, ok = true) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hidden", "bad", "good");
    el.classList.add(ok ? "good" : "bad");
    setTimeout(() => el.classList.add("hidden"), 3200);
  }

  function shortAddr(a) {
    if (!a) return "—";
    return a.length > 12 ? a.slice(0, 4) + "…