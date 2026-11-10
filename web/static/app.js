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
  const balSol = $("balSol");
  const balUsd = $("balUsd");

  function initData() {
    return (tg && tg.initData) || "";
  }

  async function api(path) {
    const res = await fetch(path, {
      headers: {
        "X-Telegram-Init-Data": initData(),
      },
    });
    const data = await res.json().catch(() => ({}));
    return { res, data };
  }

  function setStatus(kind, text) {
    statusPill.className = "pill " + kind;
    statusPill.textContent = text;
  }

  async function boot() {
    if (!initData()) {
      setStatus("offline", "OPEN IN TELEGRAM");
      userLine.textContent = "Open this page from @ShadowSnipebot → /app";
      return;
    }

    const { res, data } = await api("/api/me");
    if (!res.ok || !data.ok) {
      setStatus("offline", "AUTH FAILED");
      userLine.textContent = "Could not verify Telegram session.";
      return;
    }

    const u = data.user;
    const name = u.username ? "@" + u.username : (u.first_name || u.id);
    userLine.textContent = name + " · id " + u.id;

    if (!u.can_access) {
      setStatus("locked", "LOCKED");
      gateCard.classList.remove("hidden");
      balSol.textContent = "—";
      balUsd.textContent = "Activate license in the bot";
      return;
    }

    setStatus("online", "ONLINE");
    gateCard.classList.add("hidden");

    // Phase 3 stub — Phase 1 fills real numbers
    const port = await api("/api/portfolio");
    if (port.res.ok && port.data.ok) {
      balSol.textContent = "0.0000";
      balUsd.textContent = "≈ $0.00 USD · live data next";
    }
  }

  // Theme toggle
  const root = document.documentElement;
  const saved = localStorage.getItem("ss_theme");
  if (saved) root.setAttribute("data-theme", saved);
  $("themeToggle").addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    localStorage.setItem("ss_theme", next);
  });

  // Chips / tabs (UI only in Phase 3)
  document.querySelectorAll(".chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  boot().catch((err) => {
    console.error(err);
    setStatus("offline", "ERROR");
    userLine.textContent = String(err && err.message ? err.message : err);
  });
})();
