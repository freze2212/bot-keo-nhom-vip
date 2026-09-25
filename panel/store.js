/**
 * Tenant = 1 license + 1 acc Tele + nhiều nhóm
 * Mỗi nhóm sync → 1 bot_customer_* trong tele_forward_accounts.json
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.join(__dirname, "..");
const TENANTS_DIR = path.join(ROOT, "tenants");
const CUSTOMERS_DIR = path.join(ROOT, "customers"); // legacy flat
const LICENSES_FILE = path.join(ROOT, "panel_data", "licenses.json");
const STATE_FILE = path.join(ROOT, "panel_data", "state.json");
const SESSIONS_FILE = path.join(ROOT, "panel_data", "sessions.json");

const PLAN_PRESETS = {
  trial: { days: 3, label: "Dùng thử 3 ngày", max_groups: 2 },
  week: { days: 7, label: "1 tuần", max_groups: 3 },
  month: { days: 30, label: "1 tháng", max_groups: 10 },
};

function ensureDirs() {
  for (const d of [TENANTS_DIR, CUSTOMERS_DIR, path.dirname(LICENSES_FILE)]) {
    if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  }
  if (!fs.existsSync(LICENSES_FILE)) {
    fs.writeFileSync(
      LICENSES_FILE,
      JSON.stringify(
        {
          licenses: [
            {
              key: "TRIAL-DEMO-001",
              plan: "trial",
              days: 3,
              max_groups: 2,
              created_at: new Date().toISOString(),
              expires_at: null,
              activated_at: null,
              tenant_id: null,
              enabled: true,
            },
            {
              key: "PRO-DEMO-001",
              plan: "month",
              days: 30,
              max_groups: 10,
              created_at: new Date().toISOString(),
              expires_at: null,
              activated_at: null,
              tenant_id: null,
              enabled: true,
            },
          ],
        },
        null,
        2
      ),
      "utf8"
    );
  }
  if (!fs.existsSync(STATE_FILE)) {
    fs.writeFileSync(
      STATE_FILE,
      JSON.stringify({ forward_pid: null, login_pid: null }, null, 2),
      "utf8"
    );
  }
  if (!fs.existsSync(SESSIONS_FILE)) {
    fs.writeFileSync(SESSIONS_FILE, JSON.stringify({ sessions: [] }, null, 2));
  }
}

function newId(prefix = "t") {
  return `${prefix}_${crypto.randomBytes(4).toString("hex")}`;
}

function defaultGroup(partial = {}) {
  const isVirtual = !!partial.is_virtual;
  return {
    id: partial.id || newId("grp"),
    name: partial.name || (isVirtual ? "Nhóm ảo" : "Nhóm thật"),
    group_id: String(partial.group_id || "").trim(),
    is_virtual: isVirtual,
    bet_amount_label: String(partial.bet_amount_label || "1000"),
    interval_minutes: [2, 5, 10, 15, 30, 60].includes(Number(partial.interval_minutes))
      ? Number(partial.interval_minutes)
      : 5,
    start_time: partial.start_time || "08:00",
    end_time: partial.end_time || "23:00",
    rounds_per_slot: Math.min(5, Math.max(1, Number(partial.rounds_per_slot) || 1)),
    win_rate: Number(partial.win_rate) || 0.8,
    loss_rate: Number(partial.loss_rate) || 0.15,
    tie_rate: Number(partial.tie_rate) || 0.05,
    // Báo bàn: ảo tắt; 24/24 bắt buộc nhóm riêng; thật theo tùy chọn
    send_table_preview: isVirtual
      ? false
      : !!partial.continuous_mode
        ? true
        : !!partial.send_table_preview,
    table_preview_group_id: isVirtual
      ? ""
      : String(partial.table_preview_group_id || "").trim(),
    // Wizard content — index tin nguồn (UI chọn, không bắt user gõ số)
    open_msgs: Array.isArray(partial.open_msgs)
      ? partial.open_msgs.map(Number)
      : [0, 1],
    after_preview_msgs: Array.isArray(partial.after_preview_msgs)
      ? partial.after_preview_msgs.map(Number)
      : isVirtual
        ? []
        : [2],
    win_msg: partial.win_msg != null ? Number(partial.win_msg) : 5,
    loss_msg: partial.loss_msg != null ? Number(partial.loss_msg) : 3,
    tie_msg: partial.tie_msg != null ? Number(partial.tie_msg) : 6,
    end_msgs: Array.isArray(partial.end_msgs)
      ? partial.end_msgs.map(Number)
      : [4],
    step_delay: Number(partial.step_delay) || 20,
    enabled: partial.enabled !== false,
    continuous_mode: !!partial.continuous_mode,
    continuous_gap_sec: Math.min(30, Math.max(0.5, Number(partial.continuous_gap_sec) || 2)),
    continuous_slim: partial.continuous_slim !== false,
    result_crop_mode: partial.result_crop_mode || (partial.continuous_mode ? "bottom_right" : ""),
    result_crop_right_frac: Number(partial.result_crop_right_frac) || 0.3,
    result_crop_bottom_frac: Number(partial.result_crop_bottom_frac) || 0.3,
    result_crop_right_trim_frac: Number(partial.result_crop_right_trim_frac) || 0.035,
    token_bot: String(partial.token_bot || "").trim(),
    // bot = BotFather | boss = userbot (số Tele đã login)
    send_via: (() => {
      const v = String(partial.send_via || "").trim().toLowerCase();
      if (v === "bot" || v === "boss") return v;
      return String(partial.token_bot || "").trim() ? "bot" : "boss";
    })(),
    // Kết quả: stamp | caption | forward (tin từ kênh nguồn)
    kq_style: (() => {
      const k = String(partial.kq_style || "").trim().toLowerCase();
      if (k === "stamp" || k === "caption" || k === "forward") return k;
      if (partial.result_via_source_messages) return "forward";
      if (partial.stamp_result_on_image) return "stamp";
      return "caption";
    })(),
    content_style: String(partial.content_style || "simple").trim() || "simple",
    gap_thep_ladder: String(partial.gap_thep_ladder || "50,100,200,400,800").trim(),
    gap_thep_day_open: Number(partial.gap_thep_day_open) || 0,
    ho_template: String(partial.ho_template || ""),
    outcome_caption_mode: String(partial.outcome_caption_mode || "default").trim() || "default",
    stamp_result_on_image: !!partial.stamp_result_on_image,
    outcome_caption_win: String(partial.outcome_caption_win || ""),
    outcome_caption_loss: String(partial.outcome_caption_loss || ""),
    outcome_caption_tie: String(partial.outcome_caption_tie || ""),
    result_via_source_messages: !!partial.result_via_source_messages,
    // Tình trạng nhóm (ok / paused / banned / no_access / error / unknown)
    health: partial.health || (partial.enabled === false ? "paused" : "unknown"),
    health_msg: partial.health_msg || "",
    health_at: partial.health_at || null,
  };
}

function defaultTenant(partial = {}) {
  const groups = Array.isArray(partial.groups)
    ? partial.groups.map(defaultGroup)
    : partial.group_id
      ? [defaultGroup(partial)]
      : [];
  return {
    id: partial.id || newId("tenant"),
    display_name: partial.display_name || partial.name || "Tài khoản thuê",
    license_key: partial.license_key || "",
    phone: partial.phone || "",
    api_id: partial.api_id || "",
    api_hash: partial.api_hash || "",
    twofa: partial.twofa || "",
    session_name: partial.session_name || "",
    source_username: partial.source_username || "frezeit",
    tele_ok: !!partial.tele_ok,
    groups,
    created_at: partial.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function tenantPath(id) {
  return path.join(TENANTS_DIR, `${id}.json`);
}

function listTenants() {
  ensureDirs();
  migrateLegacyCustomers();
  return fs
    .readdirSync(TENANTS_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => {
      try {
        return JSON.parse(fs.readFileSync(path.join(TENANTS_DIR, f), "utf8"));
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function getTenant(id) {
  ensureDirs();
  const p = tenantPath(id);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function getTenantByLicense(key) {
  const k = String(key || "").trim();
  return listTenants().find((t) => t.license_key === k) || null;
}

function saveTenant(body) {
  ensureDirs();
  const prev = body.id ? getTenant(body.id) : null;
  const merged = defaultTenant({ ...(prev || {}), ...body });
  if (!merged.session_name && merged.phone) {
    const digits = String(merged.phone).replace(/\D/g, "");
    merged.session_name = digits
      ? `user_session_${digits}`
      : `user_session_${merged.id}`;
  }
  // Force ảo: tắt báo bàn. 24/24: luôn báo bàn + bắt buộc nhóm riêng.
  merged.groups = (merged.groups || []).map((g) => {
    const gg = defaultGroup(g);
    if (gg.is_virtual) {
      gg.send_table_preview = false;
      gg.table_preview_group_id = "";
      gg.continuous_mode = false;
    } else if (gg.continuous_mode) {
      gg.send_table_preview = true;
      // 24/24 không dùng tin thắng/thua/mở đầu từ kênh
      gg.open_msgs = [];
      gg.after_preview_msgs = [];
      gg.end_msgs = [];
      gg.win_msg = null;
      gg.loss_msg = null;
      gg.tie_msg = null;
      if (gg.kq_style === "forward") {
        gg.kq_style = "caption";
      }
    }
    // Đồng bộ send_via ↔ token + kq_style ↔ stamp/caption/forward
    if (gg.send_via === "boss") {
      gg.token_bot = "";
    }
    if (gg.kq_style === "stamp") {
      gg.stamp_result_on_image = true;
      gg.outcome_caption_mode = "none";
      gg.result_via_source_messages = false;
    } else if (gg.kq_style === "forward") {
      gg.stamp_result_on_image = false;
      gg.outcome_caption_mode = "none";
      gg.result_via_source_messages = true;
    } else {
      // caption
      gg.stamp_result_on_image = false;
      gg.result_via_source_messages = false;
      if (!gg.outcome_caption_mode || gg.outcome_caption_mode === "none") {
        gg.outcome_caption_mode =
          gg.outcome_caption_win || gg.outcome_caption_loss || gg.outcome_caption_tie
            ? "template"
            : "default";
      }
    }
    return gg;
  });
  merged.updated_at = new Date().toISOString();
  fs.writeFileSync(tenantPath(merged.id), JSON.stringify(merged, null, 2), "utf8");
  return merged;
}

function deleteTenant(id) {
  const p = tenantPath(id);
  if (fs.existsSync(p)) fs.unlinkSync(p);
  return true;
}

/** Migrate customers/*.json cũ → tenants (1 file = 1 nhóm) */
function migrateLegacyCustomers() {
  if (!fs.existsSync(CUSTOMERS_DIR)) return;
  const files = fs.readdirSync(CUSTOMERS_DIR).filter((f) => f.endsWith(".json"));
  for (const f of files) {
    try {
      const c = JSON.parse(fs.readFileSync(path.join(CUSTOMERS_DIR, f), "utf8"));
      if (!c.license_key && !c.phone) continue;
      let t = c.license_key ? getTenantByLicense(c.license_key) : null;
      if (!t) {
        t = defaultTenant({
          id: c.id && String(c.id).startsWith("tenant_") ? c.id : newId("tenant"),
          display_name: c.name || "Khách legacy",
          license_key: c.license_key,
          phone: c.phone,
          api_id: c.api_id,
          api_hash: c.api_hash,
          twofa: c.twofa,
          session_name: c.session_name,
          source_username: c.source_username,
          groups: [],
        });
      }
      const gid = String(c.group_id || "");
      if (gid && !t.groups.some((g) => g.group_id === gid)) {
        t.groups.push(
          defaultGroup({
            id: c.id || newId("grp"),
            name: c.name,
            group_id: gid,
            is_virtual: c.is_virtual,
            bet_amount_label: c.bet_amount_label,
            interval_minutes: c.interval_minutes,
            start_time: c.start_time,
            end_time: c.end_time,
            rounds_per_slot: c.rounds_per_slot,
            send_table_preview: c.send_table_preview,
            table_preview_group_id: c.table_preview_group_id,
            open_msgs: c.opening_order,
            after_preview_msgs: c.opening_after_preview,
            win_msg: (c.outcome_message_map || {}).WIN,
            loss_msg: (c.outcome_message_map || {}).LOSS,
            tie_msg: (c.outcome_message_map || {}).TIE,
            end_msgs: c.ending_order,
            enabled: c.enabled,
          })
        );
      }
      fs.writeFileSync(tenantPath(t.id), JSON.stringify(defaultTenant(t), null, 2));
      fs.renameSync(
        path.join(CUSTOMERS_DIR, f),
        path.join(CUSTOMERS_DIR, f + ".migrated")
      );
    } catch {
      /* skip */
    }
  }
}

function loadLicenses() {
  ensureDirs();
  return JSON.parse(fs.readFileSync(LICENSES_FILE, "utf8"));
}

function saveLicenses(data) {
  ensureDirs();
  fs.writeFileSync(LICENSES_FILE, JSON.stringify(data, null, 2), "utf8");
}

function groupKindOf(group) {
  if (group && group.continuous_mode && !group.is_virtual) return "24h";
  if (group && group.is_virtual) return "virtual";
  return "real";
}

function groupRights(lic) {
  return {
    allow_real: !lic || lic.allow_real !== false,
    allow_virtual: !lic || lic.allow_virtual !== false,
    allow_24h: !lic || lic.allow_24h !== false,
  };
}

function groupKindError(lic, group) {
  const rights = groupRights(lic);
  const kind = groupKindOf(group);
  if (kind === "24h" && !rights.allow_24h) return "Mã này không được tạo nhóm 24/24.";
  if (kind === "virtual" && !rights.allow_virtual) return "Mã này không được tạo nhóm ảo.";
  if (kind === "real" && !rights.allow_real) return "Mã này không được tạo nhóm thật.";
  return null;
}

function readRightsPatch(src) {
  const flag = (v) => v === true || v === "true" || v === 1 || v === "1";
  const out = {};
  if (src && src.allow_real != null) out.allow_real = flag(src.allow_real);
  if (src && src.allow_virtual != null) out.allow_virtual = flag(src.allow_virtual);
  if (src && src.allow_24h != null) out.allow_24h = flag(src.allow_24h);
  return out;
}

function createLicense({ plan, note, max_groups, days, allow_real, allow_virtual, allow_24h }) {
  const preset = PLAN_PRESETS[plan] || PLAN_PRESETS.month;
  const rights = readRightsPatch({ allow_real, allow_virtual, allow_24h });
  const allowReal = rights.allow_real !== false;
  const allowVirtual = rights.allow_virtual !== false;
  const allow24 = rights.allow_24h !== false;
  if (!allowReal && !allowVirtual && !allow24) {
    return { ok: false, error: "Chọn ít nhất một loại nhóm: thật, ảo hoặc 24/24." };
  }
  const data = loadLicenses();
  const lic = {
    key: `${String(plan || "month").toUpperCase()}-${crypto
      .randomBytes(3)
      .toString("hex")
      .toUpperCase()}`,
    plan: plan || "month",
    days: days != null ? Number(days) : preset.days,
    max_groups:
      max_groups != null ? Number(max_groups) : preset.max_groups,
    allow_real: allowReal,
    allow_virtual: allowVirtual,
    allow_24h: allow24,
    note: note || "",
    created_at: new Date().toISOString(),
    expires_at: null,
    activated_at: null,
    tenant_id: null,
    enabled: true,
  };
  data.licenses = data.licenses || [];
  data.licenses.push(lic);
  saveLicenses(data);
  return { ok: true, license: lic, preset };
}

function findLicense(key) {
  const data = loadLicenses();
  const lic = (data.licenses || []).find(
    (l) => String(l.key).trim() === String(key).trim()
  );
  return { data, lic };
}

function updateLicense(key, patch = {}) {
  const { data, lic } = findLicense(key);
  if (!lic) return { ok: false, error: "Không tìm thấy mã" };
  if (patch.note != null) lic.note = String(patch.note);
  if (patch.max_groups != null) {
    const n = Number(patch.max_groups);
    if (!Number.isFinite(n) || n < 1 || n > 50) {
      return { ok: false, error: "Số nhóm tối đa từ 1–50" };
    }
    lic.max_groups = n;
  }
  if (patch.days != null && !lic.activated_at) {
    const d = Number(patch.days);
    if (!Number.isFinite(d) || d < 1) {
      return { ok: false, error: "Số ngày không hợp lệ" };
    }
    lic.days = d;
  }
  if (patch.plan != null && PLAN_PRESETS[patch.plan]) {
    lic.plan = patch.plan;
  }
  const rights = readRightsPatch(patch);
  const nextRights = groupRights({ ...lic, ...rights });
  if (!nextRights.allow_real && !nextRights.allow_virtual && !nextRights.allow_24h) {
    return { ok: false, error: "Chọn ít nhất một loại nhóm: thật, ảo hoặc 24/24." };
  }
  if (rights.allow_real != null) lic.allow_real = rights.allow_real;
  if (rights.allow_virtual != null) lic.allow_virtual = rights.allow_virtual;
  if (rights.allow_24h != null) lic.allow_24h = rights.allow_24h;
  if (patch.enabled != null) lic.enabled = !!patch.enabled;
  saveLicenses(data);
  return { ok: true, license: lic };
}

/** Cộng thêm ngày vào hạn (đã kích hoạt) hoặc tăng days (chưa kích hoạt) */
function extendLicense(key, extraDays) {
  const days = Number(extraDays);
  if (!Number.isFinite(days) || days < 1) {
    return { ok: false, error: "Số ngày cộng thêm phải ≥ 1" };
  }
  const { data, lic } = findLicense(key);
  if (!lic) return { ok: false, error: "Không tìm thấy mã" };
  if (!lic.activated_at) {
    lic.days = Number(lic.days || 0) + days;
  } else {
    const base =
      lic.expires_at && new Date(lic.expires_at) > new Date()
        ? new Date(lic.expires_at)
        : new Date();
    lic.expires_at = new Date(base.getTime() + days * 86400000).toISOString();
    lic.days = Number(lic.days || 0) + days;
  }
  if (lic.enabled === false) lic.enabled = true;
  saveLicenses(data);
  return { ok: true, license: lic, added_days: days };
}

function deleteLicense(key) {
  const data = loadLicenses();
  const before = (data.licenses || []).length;
  data.licenses = (data.licenses || []).filter(
    (l) => String(l.key).trim() !== String(key).trim()
  );
  if (data.licenses.length === before) {
    return { ok: false, error: "Không tìm thấy mã" };
  }
  saveLicenses(data);
  return { ok: true };
}

function groupStatusLabel(g) {
  if (g.enabled === false) return { code: "paused", label: "Tạm dừng" };
  const h = g.health || "unknown";
  const map = {
    ok: "Đang ổn",
    paused: "Tạm dừng",
    banned: "Nhóm bị bay / cấm",
    no_access: "Không gửi được",
    error: "Lỗi gửi",
    slow: "Giới hạn tốc độ",
    unknown: "Chưa phát",
  };
  return { code: h, label: map[h] || map.unknown };
}

function tenantGroupStats(t) {
  const gs = t.groups || [];
  const running = gs.filter((g) => g.enabled !== false && g.group_id).length;
  const paused = gs.filter((g) => g.enabled === false).length;
  const bad = gs.filter((g) =>
    ["banned", "no_access", "error"].includes(g.health)
  ).length;
  return {
    total: gs.length,
    running,
    paused,
    problem: bad,
  };
}

/** Admin: danh sách mã + thống kê nhóm đang chạy */
function licensesOverview() {
  const data = loadLicenses();
  const tenants = listTenants();
  return (data.licenses || []).map((lic) => {
    const t =
      (lic.tenant_id && getTenant(lic.tenant_id)) ||
      getTenantByLicense(lic.key);
    const chk = checkLicense(lic.key);
    const stats = t ? tenantGroupStats(t) : { total: 0, running: 0, paused: 0, problem: 0 };
    const maxG = lic.max_groups || PLAN_PRESETS[lic.plan]?.max_groups || 5;
    let status = "chưa dùng";
    if (!lic.enabled) status = "đã tắt";
    else if (lic.activated_at && lic.expires_at && new Date(lic.expires_at) < new Date())
      status = "hết hạn";
    else if (lic.activated_at) status = "đang dùng";
    return {
      ...lic,
      ...groupRights(lic),
      max_groups: maxG,
      status,
      days_left: chk.ok && chk.license ? chk.license.days_left : null,
      groups_total: stats.total,
      groups_running: stats.running,
      groups_paused: stats.paused,
      groups_problem: stats.problem,
      groups_limit: maxG,
      at_limit: stats.total >= maxG,
      tenant_name: t ? t.display_name || t.phone || t.id : null,
      tenant_phone: t ? t.phone || null : null,
      tenant_id: t ? t.id : lic.tenant_id || null,
      groups: (t && t.groups) || [],
    };
  });
}

function activateLicense(key, tenantId) {
  const data = loadLicenses();
  const lic = (data.licenses || []).find(
    (l) => String(l.key).trim() === String(key).trim()
  );
  if (!lic || !lic.enabled) {
    return { ok: false, error: "Key không hợp lệ hoặc đã tắt" };
  }
  const now = new Date();
  if (!lic.activated_at) {
    const preset = PLAN_PRESETS[lic.plan] || { days: lic.days || 30 };
    lic.days = preset.days || lic.days; // khóa theo plan
    lic.max_groups = lic.max_groups || preset.max_groups || 5;
    lic.activated_at = now.toISOString();
    lic.expires_at = new Date(
      now.getTime() + Number(lic.days) * 86400000
    ).toISOString();
  }
  if (lic.expires_at && new Date(lic.expires_at) < now) {
    return { ok: false, error: "Key đã hết hạn", license: lic };
  }
  if (tenantId) lic.tenant_id = tenantId;
  saveLicenses(data);
  return { ok: true, license: lic };
}

function setLicenseEnabled(key, enabled) {
  const data = loadLicenses();
  const lic = (data.licenses || []).find(
    (l) => String(l.key).trim() === String(key).trim()
  );
  if (!lic) return { ok: false, error: "Không tìm thấy mã" };
  lic.enabled = !!enabled;
  saveLicenses(data);
  return { ok: true, license: lic };
}

function checkLicense(key) {
  const data = loadLicenses();
  const lic = (data.licenses || []).find(
    (l) => String(l.key).trim() === String(key).trim()
  );
  if (!lic || !lic.enabled) return { ok: false, error: "Key không hợp lệ" };
  if (!lic.activated_at) {
    return { ok: true, license: lic, needs_activate: true };
  }
  if (lic.expires_at && new Date(lic.expires_at) < new Date()) {
    return { ok: false, error: "Key đã hết hạn", license: lic };
  }
  const leftMs = new Date(lic.expires_at) - Date.now();
  const days_left = Math.max(0, Math.ceil(leftMs / 86400000));
  return { ok: true, license: { ...lic, days_left } };
}

function licenseInfoPublic(lic) {
  if (!lic) return null;
  const leftMs = lic.expires_at ? new Date(lic.expires_at) - Date.now() : null;
  return {
    key: lic.key,
    plan: lic.plan,
    days: lic.days,
    max_groups: lic.max_groups || PLAN_PRESETS[lic.plan]?.max_groups || 5,
    activated_at: lic.activated_at,
    expires_at: lic.expires_at,
    days_left:
      leftMs == null ? lic.days : Math.max(0, Math.ceil(leftMs / 86400000)),
    label: PLAN_PRESETS[lic.plan]?.label || `${lic.days} ngày`,
    allow_real: groupRights(lic).allow_real,
    allow_virtual: groupRights(lic).allow_virtual,
    allow_24h: groupRights(lic).allow_24h,
  };
}

function readState() {
  ensureDirs();
  return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
}

function writeState(patch) {
  const cur = readState();
  const next = { ...cur, ...patch };
  fs.writeFileSync(STATE_FILE, JSON.stringify(next, null, 2), "utf8");
  return next;
}

function loadSessions() {
  ensureDirs();
  return JSON.parse(fs.readFileSync(SESSIONS_FILE, "utf8"));
}

function saveSessions(data) {
  fs.writeFileSync(SESSIONS_FILE, JSON.stringify(data, null, 2), "utf8");
}

function createSession({ role, license_key, tenant_id }) {
  const token = crypto.randomBytes(24).toString("hex");
  const data = loadSessions();
  data.sessions = (data.sessions || []).filter(
    (s) => s.expires_at && new Date(s.expires_at) > new Date()
  );
  const expires_at = new Date(Date.now() + 7 * 86400000).toISOString();
  data.sessions.push({
    token,
    role: role || "customer",
    license_key: license_key || null,
    tenant_id: tenant_id || null,
    created_at: new Date().toISOString(),
    expires_at,
  });
  saveSessions(data);
  return { token, expires_at, role: role || "customer", tenant_id };
}

function getSession(token) {
  if (!token) return null;
  const s = (loadSessions().sessions || []).find((x) => x.token === token);
  if (!s || (s.expires_at && new Date(s.expires_at) < new Date())) return null;
  return s;
}

function revokeSession(token) {
  const data = loadSessions();
  data.sessions = (data.sessions || []).filter((s) => s.token !== token);
  saveSessions(data);
}

function groupToForwardAccount(tenant, group) {
  const isVirtual = !!group.is_virtual;
  const open = group.open_msgs || [0, 1];
  const after = group.after_preview_msgs || [];
  const end = group.end_msgs || [4];
  const indices = [
    ...open,
    ...after,
    group.win_msg,
    group.loss_msg,
    group.tie_msg,
    ...end,
  ].filter((n) => n != null && !Number.isNaN(n));
  const minSrc = Math.max(7, ...(indices.map((n) => n + 1)), 1);

  const acc = {
    id: `bot_customer_${group.id}`,
    name: `${tenant.display_name} · ${group.name}`,
    phone: tenant.phone,
    api_id: Number(tenant.api_id) || tenant.api_id,
    api_hash: tenant.api_hash,
    session_name: tenant.session_name,
    group_id: String(group.group_id || "").trim(),
    name_service: "NS1",
    session_table: "C01",
    source_username: tenant.source_username || "frezeit",
    interval_minutes: Number(group.interval_minutes) || 5,
    run_now_on_start: !group.continuous_mode,
    start_time: group.continuous_mode ? "00:00" : group.start_time || "08:00",
    end_time: group.continuous_mode ? "23:59" : group.end_time || "23:00",
    bet_amount_label: String(group.bet_amount_label || "1000"),
    is_virtual: isVirtual,
    flow_prior_round: true,
    ho_mode: isVirtual ? "match_shot" : "match_vision",
    step_delay: Number(group.step_delay) || 20,
    ho_pre_wait_sec: group.continuous_mode ? 0 : 5,
    ho_listen_timeout_sec: group.continuous_mode ? 75 : 90,
    post_ho_wait_sec: 0.5,
    result_poll_sec: 0.2,
    result_listen_timeout_sec: 60,
    opening_order: open,
    opening_delays: open.map(() => Number(group.step_delay) || 20),
    opening_after_preview: after,
    opening_after_preview_delays: after.map(() => Number(group.step_delay) || 20),
    send_table_preview: isVirtual
      ? false
      : !!group.continuous_mode
        ? true
        : !!group.send_table_preview,
    table_preview_before_ho:
      !isVirtual && (!!group.continuous_mode || !!group.send_table_preview),
    send_table_preview_caption: "🎰 SẢNH SEXY BÀN : {table} 💎",
    result_via_source_messages: !!group.result_via_source_messages || group.kq_style === "forward",
    outcome_message_map: {
      WIN: Number(group.win_msg),
      LOSS: Number(group.loss_msg),
      TIE: Number(group.tie_msg),
    },
    ending_order: end,
    ending_delays: end.map(() => Number(group.step_delay) || 20),
    min_source_messages: group.continuous_mode
      ? 1
      : minSrc,
    enabled: group.enabled !== false && !!group.group_id,
    rounds_per_slot: Math.max(1, Number(group.rounds_per_slot) || 1),
    continuous_mode: !!group.continuous_mode,
    continuous_gap_sec: Number(group.continuous_gap_sec) || 2,
    continuous_slim: group.continuous_slim !== false,
    result_crop_mode:
      group.result_crop_mode ||
      (group.continuous_mode ? "bottom_right" : isVirtual ? "left" : "none"),
    result_crop_right_frac: Number(group.result_crop_right_frac) || 0.3,
    result_crop_bottom_frac: Number(group.result_crop_bottom_frac) || 0.3,
    result_crop_right_trim_frac: Number(group.result_crop_right_trim_frac) || 0.035,
    content_style: String(group.content_style || "simple").trim() || "simple",
    gap_thep_ladder: String(group.gap_thep_ladder || "50,100,200,400,800").trim(),
    gap_thep_day_open: Number(group.gap_thep_day_open) || 0,
    ho_template: String(group.ho_template || ""),
    outcome_caption_mode: String(group.outcome_caption_mode || "default").trim() || "default",
    stamp_result_on_image: !!group.stamp_result_on_image,
    outcome_caption_win: String(group.outcome_caption_win || ""),
    outcome_caption_loss: String(group.outcome_caption_loss || ""),
    outcome_caption_tie: String(group.outcome_caption_tie || ""),
    send_via: group.send_via === "bot" ? "bot" : "boss",
    kq_style: ["stamp", "caption", "forward"].includes(group.kq_style)
      ? group.kq_style
      : "caption",
  };
  // 24/24: không forward tin thắng/thua từ kênh (tránh kẹt step_delay ~20s → miss hô)
  if (!isVirtual && group.continuous_mode) {
    acc.outcome_message_map = {};
    acc.opening_order = [];
    acc.opening_after_preview = [];
    acc.ending_order = [];
    acc.ending_delays = [];
    acc.result_via_source_messages = false;
    if (acc.kq_style === "forward") {
      acc.kq_style = "caption";
      acc.outcome_caption_mode =
        String(group.outcome_caption_mode || "template").trim() || "template";
    }
  }
  if (group.send_via === "bot" && group.token_bot) {
    acc.token_bot = String(group.token_bot).trim();
  }
  if (tenant.twofa) acc.twofa = tenant.twofa;
  if (!isVirtual && group.table_preview_group_id) {
    acc.table_preview_group_id = String(group.table_preview_group_id).trim();
  }
  // 24/24 thiếu nhóm báo bàn riêng → không enable
  if (!isVirtual && group.continuous_mode) {
    const hô = String(group.group_id || "").trim();
    const bao = String(group.table_preview_group_id || "").trim();
    if (!bao || bao === hô) {
      acc.enabled = false;
    }
    if (group.send_via === "bot" && !String(group.token_bot || "").trim()) {
      acc.enabled = false;
    }
  }
  if (isVirtual) {
    acc.win_rate = Number(group.win_rate) || 0.8;
    acc.loss_rate = Number(group.loss_rate) || 0.15;
    acc.tie_rate = Number(group.tie_rate) || 0.05;
    acc.virtual_crop_left_frac = 0.3;
  }
  return acc;
}

function syncToTeleForward() {
  ensureDirs();
  migrateLegacyCustomers();
  const telePath = path.join(ROOT, "tele_forward_accounts.json");
  let data = { accounts: [] };
  if (fs.existsSync(telePath)) {
    data = JSON.parse(fs.readFileSync(telePath, "utf8"));
  }
  const existing = Array.isArray(data.accounts) ? data.accounts : [];
  const kept = existing.filter(
    (a) => a && a.id && !String(a.id).startsWith("bot_customer_")
  );
  const fromTenants = [];
  for (const t of listTenants()) {
    const lic = checkLicense(t.license_key);
    if (!lic.ok) continue;
    const maxG =
      (lic.license && lic.license.max_groups) ||
      PLAN_PRESETS[lic.license?.plan]?.max_groups ||
      5;
    const eligible = (t.groups || []).filter(
      (g) => g.enabled !== false && String(g.group_id || "").trim()
    );
    // Chỉ chạy tối đa max_groups nhóm / mã
    for (const g of eligible.slice(0, maxG)) {
      fromTenants.push(groupToForwardAccount(t, g));
    }
  }
  data.accounts = [...kept, ...fromTenants];
  fs.writeFileSync(telePath, JSON.stringify(data, null, 2), "utf8");
  return {
    kept: kept.length,
    customers: fromTenants.length,
    total: data.accounts.length,
  };
}

module.exports = {
  ROOT,
  TENANTS_DIR,
  PLAN_PRESETS,
  ensureDirs,
  newId,
  defaultGroup,
  defaultTenant,
  listTenants,
  getTenant,
  getTenantByLicense,
  saveTenant,
  deleteTenant,
  loadLicenses,
  saveLicenses,
  createLicense,
  groupKindOf,
  groupKindError,
  updateLicense,
  extendLicense,
  deleteLicense,
  setLicenseEnabled,
  licensesOverview,
  tenantGroupStats,
  groupStatusLabel,
  activateLicense,
  checkLicense,
  licenseInfoPublic,
  readState,
  writeState,
  createSession,
  getSession,
  revokeSession,
  syncToTeleForward,
  groupToForwardAccount,
  // legacy aliases used by old routes during transition
  listCustomers: listTenants,
  getCustomer: getTenant,
  saveCustomer: saveTenant,
  deleteCustomer: deleteTenant,
  CUSTOMERS_DIR: TENANTS_DIR,
  customerPath: tenantPath,
};
