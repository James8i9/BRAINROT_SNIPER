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
  let canAccess = false;

  function initData() {
    return (tg && tg.initData) || "";
  }

  async function api(path, opts) {
    opts = opts || {};
    const headers = { "X-Telegram-Init-Data": initData() };
    if (opts.body) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    return { res: res, data: data };
  }

  function setStatus(kind, text) {
    $("statusPill").className = "pill " + kind;
    $("statusPill").textContent = text;
  }

  function toast(msg, ok) {
    const el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden", "bad", "good");
    el.classList.add(ok === false ? "bad" : "good");
    setTimeout(function () { el.classList.add("hidden"); }, 3200);
  }

  function shortAddr(a) {
    if (!a) return "—";
    return a.length > 12 ? a.slice(0, 4) + "…" + a.slice(-4) : a;
  }

  function fmtSol(n) {
    if (n === null || n === undefined || isNaN(n)) return "?";
    return Number(n).toFixed(4);
  }

  function fmtUsd(n) {
    if (n === null || n === undefined || isNaN(n)) return "$—";
    return "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function renderWallets(list, el) {
    if (!el) return;
    if (!list || !list.length) {
      el.innerHTML = "<div class=\"muted\">No wallets yet</div>";
      return;
    }
    el.innerHTML = list.map(function (w) {
      const tag = (w.type || "").toUpperCase();
      const bal = w.balance_sol == null ? "?" : fmtSol(w.balance_sol);
      return (
        "<div class=\"wallet-row\">" +
          "<div><span class=\"tag\">" + tag + "</span> " +
          "<code>" + shortAddr(w.address) + "</code></div>" +
          "<div class=\"wbal\"><b>" + bal + "</b> SOL</div>" +
        "</div>"
      );
    }).join("");
  }

  function applyPortfolio(data) {
    const total = data.total_sol;
    $("balSol").textContent = total == null ? "—" : fmtSol(total);
    if (data.total_usd != null) {
      $("balUsd").textContent = "≈ " + fmtUsd(data.total_usd) + " USD";
    } else {
      $("balUsd").textContent = "≈ $— USD";
    }
    const hint = $("balHint");
    if (hint) {
      hint.textContent =
        (data.buy_count || 0) + " buy · " +
        (data.fund_address ? "fund set" : "no fund") +
        " · live RPC";
    }

    renderWallets(data.wallets, $("walletPreviewList"));
    renderWallets(data.wallets, $("walletFullList"));

    const fundStatus = $("fundStatus");
    const importBox = $("importBox");
    if (data.fund_address) {
      fundStatus.textContent = data.fund_address;
      importBox.classList.add("hidden");
    } else {
      fundStatus.textContent = "Not imported";
      importBox.classList.remove("hidden");
    }
  }

  async function loadPortfolio() {
    if (!canAccess) return;
    const { res, data } = await api("/api/portfolio");
    if (!res.ok || !data.ok) {
      toast((data && data.error) || "Portfolio failed", false);
      return;
    }
    applyPortfolio(data);
  }

  function showPanel(name) {
    document.querySelectorAll(".panel").forEach(function (p) {
      p.classList.add("hidden");
    });
    const el = $("panel-" + name);
    if (el) el.classList.remove("hidden");
    document.querySelectorAll(".tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === name);
    });
  }

  async function boot() {
    if (!initData()) {
      setStatus("offline", "OPEN IN TELEGRAM");
      $("userLine").textContent = "Open from @ShadowSnipebot → /app";
      return;
    }

    const { res, data } = await api("/api/me");
    if (!res.ok || !data.ok) {
      setStatus("offline", "AUTH FAILED");
      $("userLine").textContent = "Could not verify Telegram session.";
      return;
    }

    const u = data.user;
    const name = u.username ? "@" + u.username : (u.first_name || u.id);
    $("userLine").textContent = name + " · id " + u.id;
    canAccess = !!u.can_access;

    if (!canAccess) {
      setStatus("locked", "LOCKED");
      $("gateCard").classList.remove("hidden");
      $("balSol").textContent = "—";
      $("balUsd").textContent = "Activate license in the bot";
      return;
    }

    setStatus("online", "ONLINE");
    $("gateCard").classList.add("hidden");
    await loadPortfolio();
  }

  // Theme
  const root = document.documentElement;
  const saved = localStorage.getItem("ss_theme");
  if (saved) root.setAttribute("data-theme", saved);
  $("themeToggle").addEventListener("click", function () {
    const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    localStorage.setItem("ss_theme", next);
  });

  $("btnRefresh").addEventListener("click", function () {
    loadPortfolio().then(function () { toast("Refreshed"); });
  });

  document.querySelectorAll(".tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      showPanel(btn.getAttribute("data-tab"));
    });
  });

  const gotoWallets = $("gotoWallets");
  if (gotoWallets) {
    gotoWallets.addEventListener("click", function () { showPanel("wallets"); });
  }

  document.querySelectorAll(".chip").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".chip").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
    });
  });

  $("btnImportFund").addEventListener("click", async function () {
    const key = ($("fundKeyInput").value || "").trim();
    if (!key) { toast("Paste a private key", false); return; }
    $("btnImportFund").disabled = true;
    try {
      const { res, data } = await api("/api/wallets/import-fund", {
        method: "POST",
        body: { private_key: key },
      });
      if (!res.ok || !data.ok) {
        toast((data && data.error) || "Import failed", false);
        return;
      }
      $("fundKeyInput").value = "";
      applyPortfolio(data);
      toast("Fund wallet imported");
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    } finally {
      $("btnImportFund").disabled = false;
    }
  });

  $("btnGenBuy").addEventListener("click", async function () {
    const count = parseInt($("buyCount").value || "5", 10);
    $("btnGenBuy").disabled = true;
    try {
      const { res, data } = await api("/api/wallets/generate-buy", {
        method: "POST",
        body: { count: count },
      });
      if (!res.ok || !data.ok) {
        toast((data && data.error) || "Generate failed", false);
        return;
      }
      applyPortfolio(data);
      toast("Generated " + count + " buy wallet(s)");
    } finally {
      $("btnGenBuy").disabled = false;
    }
  });

  $("btnDistribute").addEventListener("click", async function () {
    const amount = parseFloat($("distAmount").value || "0");
    if (!(amount > 0)) { toast("Enter SOL amount each", false); return; }
    $("btnDistribute").disabled = true;
    $("distResult").textContent = "Sending…";
    try {
      const { res, data } = await api("/api/wallets/distribute", {
        method: "POST",
        body: { amount_each: amount },
      });
      if (!res.ok || !data.ok) {
        $("distResult").textContent = "";
        toast((data && data.error) || "Distribute failed", false);
        return;
      }
      applyPortfolio(data);
      const d = data.distribute || {};
      $("distResult").textContent =
        "Sent " + (d.total_sent || "?") + " SOL · " + (d.signature || "").slice(0, 16) + "…";
      toast("Distribution OK");
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    } finally {
      $("btnDistribute").disabled = false;
    }
  });

  boot().catch(function (err) {
    console.error(err);
    setStatus("offline", "ERROR");
    $("userLine").textContent = String(err && err.message ? err.message : err);
  });
})();
