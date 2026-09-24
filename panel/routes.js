/**
 * Panel API v2 — tenant + nhiều nhóm, license khóa ngày
 */
const express = require("express");
const path = require("path");
const fs = require("fs");
const { spawn, spawnSync } = require("child_process");
const store = require("./store");

const router = express.Router();
store.ensureDirs();

function pyBin() {
  return process.platform === "win32" ? "py" : "python3";
}
function pyArgs(a) {
  return process.platform === "win32" ? ["-3.12", ...a] : a;
}
function isPidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
function bearer(req) {
  const h = req.headers.authorization || "";
  if (h.toLowerCase().startsWith("bearer ")) return h.slice(7).trim();
  return req.headers["x-panel-token"] || "";
}
function authRequired(req, res, next) {
  const s = store.getSession(bearer(req));
  if (!s) return res.status(401).json({ ok: false, error: "Chưa đăng nhập" });
  req.panelSession = s;
  next();
}
function adminRequired(req, res, next) {
  authRequired(req, res, () => {
    if (req.panelSession.role !== "admin") {
      return res.status(403).json({ ok: false, error: "Chỉ admin" });
    }
    next();
  });
}

router.get("/api/health", (_req, res) => {
  res.json({
    ok: true,
    plans: store.PLAN_PRESETS,
    public_url: process.env.PANEL_PUBLIC_URL || null,
  });
});

router.get("/api/plans", (_req, res) => {
  res.json({ ok: true, plans: store.PLAN_PRESETS });
});

router.post("/api/auth/login", (req, res) => {
  const key = String(req.body.key || "").trim();
  const adminKey = String(process.env.PANEL_ADMIN_KEY || "").trim();

  if (adminKey && key === adminKey) {
    const sess = store.createSession({ role: "admin", license_key: key });
    return res.json({
      ok: true,
      role: "admin",
      token: sess.token,
      expires_at: sess.expires_at,
    });
  }

  let chk = store.checkLicense(key);
  if (chk.needs_activate || (!chk.ok && chk.error === "Key không hợp lệ")) {
    // try activate if exists but fresh
  }
  if (chk.needs_activate) {
    const act = store.activateLicense(key, null);
    if (!act.ok) return res.status(400).json({ ok: false, error: act.error });
    chk = store.checkLicense(key);
  }
  if (!chk.ok) {
    const act = store.activateLicense(key, null);
    if (!act.ok) return res.status(400).json({ ok: false, error: act.error || chk.error });
    chk = store.checkLicense(key);
  }
  if (!chk.ok) return res.status(400).json({ ok: false, error: chk.error });

  let tenant = store.getTenantByLicense(key);
  if (!tenant) {
    tenant = store.saveTenant(
      store.defaultTenant({
        license_key: key,
        display_name: "Khách " + key.slice(0, 12),
        groups: [],
      })
    );
    store.activateLicense(key, tenant.id);
  }

  const sess = store.createSession({
    role: "customer",
    license_key: key,
    tenant_id: tenant.id,
  });
  res.json({
    ok: true,
    role: "customer",
    token: sess.token,
    expires_at: sess.expires_at,
    tenant_id: tenant.id,
    license: store.licenseInfoPublic(chk.license),
  });
});

router.post("/api/auth/logout", (req, res) => {
  const t = bearer(req);
  if (t) store.revokeSession(t);
  res.json({ ok: true });
});

router.get("/api/auth/me", authRequired, (req, res) => {
  const out = { ok: true, session: req.panelSession };
  if (req.panelSession.role === "customer" && req.panelSession.license_key) {
    const chk = store.checkLicense(req.panelSession.license_key);
    out.license = store.licenseInfoPublic(chk.license);
    out.tenant = store.getTenant(req.panelSession.tenant_id) ||
      store.getTenantByLicense(req.panelSession.license_key);
  }
  res.json(out);
});

router.use((req, res, next) => {
  if (!req.path.startsWith("/api")) return next();
  if (req.path.startsWith("/api/auth/") || req.path === "/api/health" || req.path === "/api/plans")
    return next();
  return authRequired(req, res, next);
});

function assertTenantAccess(req, tenantId) {
  if (req.panelSession.role === "admin") return true;
  const t = store.getTenant(tenantId);
  return t && t.license_key === req.panelSession.license_key;
}

router.get("/api/tenant", (req, res) => {
  if (req.panelSession.role === "admin") {
    return res.json({
      ok: true,
      tenants: store.listTenants(),
      licenses: store.licensesOverview(),
    });
  }
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key);
  if (!t) return res.status(404).json({ ok: false, error: "Chưa có tài khoản" });
  const chk = store.checkLicense(t.license_key);
  const lic = store.licenseInfoPublic(chk.license);
  const stats = store.tenantGroupStats(t);
  const maxG = (lic && lic.max_groups) || 5;
  const groupsView = (t.groups || []).map((g) => ({
    ...g,
    status: store.groupStatusLabel(g),
  }));
  res.json({
    ok: true,
    tenant: { ...t, groups: groupsView },
    license: lic,
    summary: {
      ...stats,
      max_groups: maxG,
      at_limit: stats.total >= maxG,
      can_add: stats.total < maxG,
      can_run: stats.running > 0 && chk.ok,
    },
  });
});

router.put("/api/tenant", (req, res) => {
  try {
    let t;
    if (req.panelSession.role === "admin" && req.body.id) {
      t = store.getTenant(req.body.id);
    } else {
      t =
        store.getTenant(req.panelSession.tenant_id) ||
        store.getTenantByLicense(req.panelSession.license_key);
    }
    if (!t) return res.status(404).json({ ok: false, error: "Không tìm thấy" });
    if (!assertTenantAccess(req, t.id)) {
      return res.status(403).json({ ok: false, error: "Không có quyền" });
    }

    // Khách không được sửa license / days
    const body = { ...req.body, id: t.id, license_key: t.license_key };
    delete body.days;
    delete body.expires_at;

    // Giới hạn số nhóm theo license
    const chk = store.checkLicense(t.license_key);
    const maxG = (chk.license && chk.license.max_groups) || 5;
    if (Array.isArray(body.groups) && body.groups.length > maxG) {
      return res.status(400).json({
        ok: false,
        error: `Gói của bạn tối đa ${maxG} nhóm. Liên hệ gia hạn để thêm.`,
      });
    }

    const saved = store.saveTenant({ ...t, ...body, license_key: t.license_key });
    const sync = store.syncToTeleForward();
    res.json({
      ok: true,
      tenant: saved,
      sync,
      license: store.licenseInfoPublic(chk.license),
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.post("/api/tenant/groups", (req, res) => {
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key);
  if (!t) return res.status(404).json({ ok: false, error: "Không tìm thấy" });
  const chk = store.checkLicense(t.license_key);
  if (!chk.ok) return res.status(400).json({ ok: false, error: chk.error });
  const maxG = chk.license.max_groups || 5;
  if ((t.groups || []).length >= maxG) {
    return res.status(400).json({
      ok: false,
      error: `Đã đủ ${maxG} nhóm (theo gói). Không thêm được nữa.`,
    });
  }
  const g = store.defaultGroup(req.body || {});
  t.groups = t.groups || [];
  t.groups.push(g);
  const saved = store.saveTenant(t);
  store.syncToTeleForward();
  res.json({ ok: true, group: g, tenant: saved });
});

router.put("/api/tenant/groups/:gid", (req, res) => {
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key);
  if (!t) return res.status(404).json({ ok: false, error: "Không tìm thấy" });
  const idx = (t.groups || []).findIndex((g) => g.id === req.params.gid);
  if (idx < 0) return res.status(404).json({ ok: false, error: "Không có nhóm" });
  t.groups[idx] = store.defaultGroup({ ...t.groups[idx], ...req.body, id: req.params.gid });
  const saved = store.saveTenant(t);
  store.syncToTeleForward();
  res.json({ ok: true, group: t.groups[idx], tenant: saved });
});

/** Khách tạm dừng / bật lại 1 nhóm (không ảnh hưởng nhóm khác) */
router.post("/api/tenant/groups/:gid/toggle", authRequired, async (req, res) => {
  try {
    const t =
      store.getTenant(req.panelSession.tenant_id) ||
      store.getTenantByLicense(req.panelSession.license_key);
    if (!t) return res.status(404).json({ ok: false, error: "Không tìm thấy" });
    const chk = store.checkLicense(t.license_key);
    if (!chk.ok) return res.status(400).json({ ok: false, error: chk.error });
    const idx = (t.groups || []).findIndex((g) => g.id === req.params.gid);
    if (idx < 0) return res.status(404).json({ ok: false, error: "Không có nhóm" });
    const enabled = req.body.enabled !== false && req.body.enabled !== "false";
    if (enabled && !String(t.groups[idx].group_id || "").trim()) {
      return res.status(400).json({
        ok: false,
        error: "Nhóm chưa có ID Telegram — sửa nhóm trước khi bật",
      });
    }
    if (enabled) {
      const maxG = (chk.license && chk.license.max_groups) || 5;
      const running = (t.groups || []).filter(
        (g, i) => i !== idx && g.enabled !== false && g.group_id
      ).length;
      if (running >= maxG) {
        return res.status(400).json({
          ok: false,
          error: `Gói chỉ cho tối đa ${maxG} nhóm đang chạy. Tạm dừng nhóm khác trước khi bật.`,
        });
      }
    }
    t.groups[idx] = store.defaultGroup({
      ...t.groups[idx],
      enabled,
      health: enabled ? (t.groups[idx].health === "paused" ? "unknown" : t.groups[idx].health) : "paused",
      health_msg: enabled ? t.groups[idx].health_msg : "Bạn đã tạm dừng nhóm này",
      id: req.params.gid,
    });
    const saved = store.saveTenant(t);
    store.syncToTeleForward();
    const st = store.readState();
    let restarted = false;
    if (st.forward_pid && isPidAlive(st.forward_pid)) {
      stopForwardProcess();
      restarted = true;
      await new Promise((r) => setTimeout(r, 1200));
      const stillOn = (saved.groups || []).some(
        (g) => g.enabled !== false && g.group_id
      );
      if (stillOn) startForwardProcess(true);
    }
    const name = t.groups[idx].name || "Nhóm";
    res.json({
      ok: true,
      group: t.groups[idx],
      tenant: saved,
      restarted,
      message: enabled
        ? `Đã bật lại “${name}”.`
        : `Đã tạm dừng “${name}”. Nhóm khác vẫn chạy.`,
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.delete("/api/tenant/groups/:gid", authRequired, async (req, res) => {
  try {
    const t =
      store.getTenant(req.panelSession.tenant_id) ||
      store.getTenantByLicense(req.panelSession.license_key);
    if (!t) return res.status(404).json({ ok: false, error: "Không tìm thấy" });
    t.groups = (t.groups || []).filter((g) => g.id !== req.params.gid);
    const saved = store.saveTenant(t);
    store.syncToTeleForward();
    const st = store.readState();
    if (st.forward_pid && isPidAlive(st.forward_pid)) {
      stopForwardProcess();
      await new Promise((r) => setTimeout(r, 1000));
      const stillOn = (saved.groups || []).some(
        (g) => g.enabled !== false && g.group_id
      );
      if (stillOn) startForwardProcess(true);
    }
    res.json({ ok: true, tenant: saved });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.post("/api/licenses", adminRequired, (req, res) => {
  const plan = req.body.plan || "month";
  if (!store.PLAN_PRESETS[plan]) {
    return res.status(400).json({
      ok: false,
      error: "Chỉ chọn gói: trial | week | month",
    });
  }
  const r = store.createLicense({
    plan,
    note: req.body.note,
    max_groups: req.body.max_groups,
    days: req.body.days,
  });
  res.json(r);
});

router.get("/api/licenses", adminRequired, (_req, res) => {
  res.json({
    ok: true,
    licenses: store.licensesOverview(),
    plans: store.PLAN_PRESETS,
    forward_running: isPidAlive(store.readState().forward_pid),
  });
});

router.put("/api/licenses/:key", adminRequired, (req, res) => {
  const r = store.updateLicense(req.params.key, {
    note: req.body.note,
    max_groups: req.body.max_groups,
    days: req.body.days,
    plan: req.body.plan,
    enabled: req.body.enabled,
  });
  if (!r.ok) return res.status(404).json(r);
  store.syncToTeleForward();
  res.json({ ok: true, license: r.license, overview: store.licensesOverview() });
});

router.post("/api/licenses/:key/extend", adminRequired, (req, res) => {
  const r = store.extendLicense(req.params.key, req.body.days || 7);
  if (!r.ok) return res.status(400).json(r);
  res.json({
    ok: true,
    license: r.license,
    added_days: r.added_days,
    message: `Đã cộng thêm ${r.added_days} ngày.`,
    overview: store.licensesOverview(),
  });
});

router.delete("/api/licenses/:key", adminRequired, async (req, res) => {
  try {
    const r = store.deleteLicense(req.params.key);
    if (!r.ok) return res.status(404).json(r);
    const sync = store.syncToTeleForward();
    const st = store.readState();
    if (st.forward_pid && isPidAlive(st.forward_pid)) {
      stopForwardProcess();
      await new Promise((x) => setTimeout(x, 1000));
      startForwardProcess(true);
    }
    res.json({
      ok: true,
      sync,
      message: "Đã xóa mã — nhóm gắn mã này đã dừng.",
      overview: store.licensesOverview(),
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

/** Tắt/bật 1 mã — tắt thì khách không vào được + nhóm bị gỡ khỏi runner */
router.post("/api/licenses/:key/toggle", adminRequired, async (req, res) => {
  try {
    const enabled = req.body.enabled !== false && req.body.enabled !== "false";
    const r = store.setLicenseEnabled(req.params.key, enabled);
    if (!r.ok) return res.status(404).json(r);
    const sync = store.syncToTeleForward();
    const st = store.readState();
    let restarted = false;
    if (st.forward_pid && isPidAlive(st.forward_pid)) {
      stopForwardProcess();
      restarted = true;
      await new Promise((x) => setTimeout(x, 1200));
      startForwardProcess(true);
    }
    res.json({
      ok: true,
      license: r.license,
      sync,
      restarted,
      message: enabled
        ? "Đã bật lại mã."
        : "Đã tắt mã — khách không vào được, nhóm đã dừng.",
      overview: store.licensesOverview(),
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.post("/api/sync", adminRequired, (_req, res) => {
  res.json({ ok: true, sync: store.syncToTeleForward() });
});

router.post("/api/otp", (req, res) => {
  const code = String(req.body.code || "").trim().replace(/\s/g, "");
  if (!code) return res.status(400).json({ ok: false, error: "Thiếu OTP" });
  fs.writeFileSync(path.join(store.ROOT, "telegram_otp.txt"), code, "utf8");
  res.json({ ok: true });
});

router.post("/api/2fa", (req, res) => {
  const pwd = String(req.body.password || "").trim();
  if (!pwd) return res.status(400).json({ ok: false, error: "Thiếu 2FA" });
  fs.writeFileSync(path.join(store.ROOT, "telegram_2fa.txt"), pwd, "utf8");
  res.json({ ok: true });
});

router.post("/api/login/start", (req, res) => {
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key) ||
    (req.body.tenant_id && store.getTenant(req.body.tenant_id));
  if (!t) return res.status(404).json({ ok: false, error: "Chưa có tài khoản" });
  if (!t.phone || !t.api_id || !t.api_hash) {
    return res.status(400).json({ ok: false, error: "Điền SĐT + API ID + API Hash trước" });
  }
  // Tạm tạo 1 forward account để --login nhận id
  store.syncToTeleForward();
  const loginId =
    (t.groups && t.groups[0] && `bot_customer_${t.groups[0].id}`) ||
    `bot_customer_${t.id}_login`;
  // Ensure at least a stub account exists for login
  const telePath = path.join(store.ROOT, "tele_forward_accounts.json");
  const tele = JSON.parse(fs.readFileSync(telePath, "utf8"));
  if (!tele.accounts.some((a) => a.id === loginId)) {
    tele.accounts.push({
      id: loginId,
      name: t.display_name + " login",
      phone: t.phone,
      api_id: Number(t.api_id),
      api_hash: t.api_hash,
      session_name: t.session_name,
      twofa: t.twofa || undefined,
      group_id: (t.groups[0] && t.groups[0].group_id) || "0",
      source_username: t.source_username || "frezeit",
      enabled: false,
      is_virtual: true,
      interval_minutes: 5,
      start_time: "00:00",
      end_time: "23:55",
      min_source_messages: 1,
      opening_order: [0],
      ending_order: [],
    });
    fs.writeFileSync(telePath, JSON.stringify(tele, null, 2));
  }

  const st = store.readState();
  if (st.login_pid && isPidAlive(st.login_pid)) {
    return res.status(409).json({ ok: false, error: "Đang login dở — nhập OTP" });
  }
  const logFile = path.join(store.ROOT, "panel_data", `login_${t.id}.log`);
  const out = fs.openSync(logFile, "w");
  const child = spawn(
    pyBin(),
    pyArgs(["bot_forward_runner.py", "--login", loginId]),
    {
      cwd: store.ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
      detached: true,
      stdio: ["ignore", out, out],
      windowsHide: true,
    }
  );
  child.unref();
  store.writeState({ login_pid: child.pid, login_log: logFile, login_tenant: t.id });
  res.json({
    ok: true,
    pid: child.pid,
    message: "Telegram đã gửi mã. Nhập OTP bên dưới.",
  });
});

router.get("/api/login/status", (_req, res) => {
  const st = store.readState();
  let log_tail = "";
  if (st.login_log && fs.existsSync(st.login_log)) {
    log_tail = fs.readFileSync(st.login_log, "utf8").slice(-3000);
  }
  const okLogin = /Đăng nhập thành công|Da dang nhap|Chào mừng|Chao mung/i.test(log_tail);
  res.json({
    ok: true,
    running: isPidAlive(st.login_pid),
    log_tail,
    success_hint: okLogin,
  });
});

function startForwardProcess(runNow = true) {
  store.syncToTeleForward();
  const st = store.readState();
  if (st.forward_pid && isPidAlive(st.forward_pid)) {
    return { ok: true, already: true, pid: st.forward_pid };
  }
  const args = ["bot_forward_runner.py"];
  if (runNow) args.push("--run-now");
  const logFile = path.join(store.ROOT, "panel_data", "forward_runner.log");
  const out = fs.openSync(logFile, "a");
  const child = spawn(pyBin(), pyArgs(args), {
    cwd: store.ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
    detached: true,
    stdio: ["ignore", out, out],
    windowsHide: true,
  });
  child.unref();
  store.writeState({ forward_pid: child.pid, forward_log: logFile });
  return { ok: true, already: false, pid: child.pid };
}

function stopForwardProcess() {
  const st = store.readState();
  if (st.forward_pid && isPidAlive(st.forward_pid)) {
    if (process.platform === "win32") {
      spawn("taskkill", ["/PID", String(st.forward_pid), "/T", "/F"], {
        windowsHide: true,
      });
    } else {
      try {
        process.kill(st.forward_pid, "SIGTERM");
      } catch (_) {}
    }
  }
  store.writeState({ forward_pid: null });
  return { ok: true };
}

/** Khách tự bật bot — không cần admin */
router.post("/api/tenant/go-live", authRequired, async (req, res) => {
  try {
    const t =
      store.getTenant(req.panelSession.tenant_id) ||
      store.getTenantByLicense(req.panelSession.license_key);
    if (!t) return res.status(404).json({ ok: false, error: "Chưa có tài khoản" });
    const chk = store.checkLicense(t.license_key);
    if (!chk.ok) return res.status(400).json({ ok: false, error: chk.error });
    if (!t.phone || !t.api_id || !t.api_hash) {
      return res.status(400).json({ ok: false, error: "Chưa kết nối Telegram (bước 1)" });
    }
    const maxG = (chk.license && chk.license.max_groups) || 5;
    let groups = (t.groups || []).filter((g) => g.enabled !== false && g.group_id);
    if (!groups.length) {
      return res.status(400).json({
        ok: false,
        error: "Chưa có nhóm — thêm nhóm ở bước 2 rồi thử lại",
      });
    }
    const capped = groups.length > maxG;
    if (capped) groups = groups.slice(0, maxG);
    store.syncToTeleForward();
    const st = store.readState();
    let restarted = false;
    if (st.forward_pid && isPidAlive(st.forward_pid)) {
      stopForwardProcess();
      restarted = true;
      await new Promise((r) => setTimeout(r, 1500));
    }
    const started = startForwardProcess(req.body.run_now !== false);
    res.json({
      ok: true,
      restarted,
      ...started,
      groups: groups.length,
      capped,
      message: capped
        ? `Gói chỉ cho tối đa ${maxG} nhóm đang chạy. Đã bật ${groups.length} nhóm đầu.`
        : restarted
          ? `Đã cập nhật — ${groups.length} nhóm đang chạy.`
          : `Bot đã bật — ${groups.length} nhóm đang chạy.`,
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.post("/api/forward/start", authRequired, (req, res) => {
  try {
    res.json(startForwardProcess(req.body.run_now !== false));
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.post("/api/forward/stop", adminRequired, (_req, res) => {
  try {
    res.json(stopForwardProcess());
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

router.get("/api/forward/status", (_req, res) => {
  const st = store.readState();
  let log_tail = "";
  if (st.forward_log && fs.existsSync(st.forward_log)) {
    log_tail = fs.readFileSync(st.forward_log, "utf8").slice(-4000);
  }
  res.json({
    ok: true,
    running: isPidAlive(st.forward_pid),
    pid: st.forward_pid || null,
    log_tail,
  });
});

router.post("/api/source/preview", (req, res) => {
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key);
  if (!t) return res.status(404).json({ ok: false, error: "Chưa có tài khoản" });
  // Write temp customer-like file for preview script
  const tmp = path.join(store.ROOT, "panel_data", `_preview_${t.id}.json`);
  fs.writeFileSync(
    tmp,
    JSON.stringify({
      phone: t.phone,
      api_id: t.api_id,
      api_hash: t.api_hash,
      session_name: t.session_name,
      source_username: t.source_username || "frezeit",
    }),
    "utf8"
  );
  const r = spawnSync(
    pyBin(),
    pyArgs([
      path.join("panel", "preview_source.py"),
      "--customer",
      tmp,
      "--limit",
      String(Math.min(20, Number(req.body.limit) || 12)),
    ]),
    {
      cwd: store.ROOT,
      encoding: "utf8",
      timeout: 60000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    }
  );
  const out = (r.stdout || "").trim();
  try {
    const j = JSON.parse(out.split("\n").filter(Boolean).pop());
    return res.status(j.ok ? 200 : 400).json(j);
  } catch {
    return res.status(500).json({ ok: false, error: out || "Preview lỗi — cần đăng nhập Tele trước" });
  }
});

/** Kiểm tra từng nhóm còn vào được Telegram không */
router.post("/api/tenant/check-health", authRequired, (req, res) => {
  const t =
    store.getTenant(req.panelSession.tenant_id) ||
    store.getTenantByLicense(req.panelSession.license_key);
  if (!t) return res.status(404).json({ ok: false, error: "Chưa có tài khoản" });
  if (!t.phone || !t.api_id || !t.api_hash) {
    return res.status(400).json({ ok: false, error: "Chưa kết nối Telegram (bước 1)" });
  }
  if (!(t.groups || []).length) {
    return res.status(400).json({ ok: false, error: "Chưa có nhóm để kiểm tra" });
  }
  const tenantFile = path.join(store.TENANTS_DIR, `${t.id}.json`);
  const r = spawnSync(
    pyBin(),
    pyArgs([path.join("panel", "check_groups.py"), "--tenant", tenantFile]),
    {
      cwd: store.ROOT,
      encoding: "utf8",
      timeout: 90000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    }
  );
  const out = (r.stdout || "").trim();
  let j;
  try {
    j = JSON.parse(out.split("\n").filter(Boolean).pop());
  } catch {
    return res.status(500).json({
      ok: false,
      error: out || r.stderr || "Không kiểm tra được — thử lại sau",
    });
  }
  if (!j.ok) return res.status(400).json(j);

  const now = new Date().toISOString();
  const byId = {};
  for (const row of j.groups || []) byId[row.id] = row;
  t.groups = (t.groups || []).map((g) => {
    const row = byId[g.id];
    if (!row) return g;
    return store.defaultGroup({
      ...g,
      health: row.health,
      health_msg: row.health_msg,
      health_at: now,
      id: g.id,
    });
  });
  const saved = store.saveTenant(t);
  const chk = store.checkLicense(t.license_key);
  const lic = store.licenseInfoPublic(chk.license);
  const stats = store.tenantGroupStats(saved);
  res.json({
    ok: true,
    tenant: {
      ...saved,
      groups: (saved.groups || []).map((g) => ({
        ...g,
        status: store.groupStatusLabel(g),
      })),
    },
    license: lic,
    summary: {
      ...stats,
      max_groups: (lic && lic.max_groups) || 5,
      at_limit: stats.total >= ((lic && lic.max_groups) || 5),
      can_add: stats.total < ((lic && lic.max_groups) || 5),
    },
    message: "Đã kiểm tra tình trạng các nhóm.",
  });
});

module.exports = router;
