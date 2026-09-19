const { firefox } = require("playwright");
const path = require("path");
const fs = require("fs");
require("dotenv").config({ path: path.resolve(__dirname, ".env") });
const { imageCapcha, helper } = require("./utilities");

const DOMAIN = process.env.DOMAIN || "https://www.rr9900.com";
const USERNAME = process.env.USERNAME_ACCOUNT || "bosdx22";
const PASSWORD = process.env.PASSWORD_ACCOUNT || "yocvsjwc";

console.log("==========================================================");
console.log(`🚀 [PLAYWRIGHT] KHỞI ĐỘNG FIREFOX (FULL ANTI-BLANK BYPASS)`);
console.log(`👉 Trang web: ${DOMAIN}`);
console.log(`👉 Tài khoản: ${USERNAME}`);
console.log("==========================================================");

async function dismissPopups(page) {
  if (!page || page.isClosed()) return;
  try {
    await page.evaluate(() => {
      const selectors = [
        ".publicModal .tcg_modal_close",
        ".tcg_modal_close",
        ".van-popup__close-icon",
        ".dialog-close",
        ".close-btn",
        ".modal-close",
        "button.close",
        ".announcement-close",
        ".notice-close",
        ".el-dialog__headerbtn",
        ".mask-close",
        ".layui-layer-close",
        "[class*='close-btn']",
        "[class*='modal_close']",
        "i.van-icon-cross"
      ];
      selectors.forEach((sel) => {
        document.querySelectorAll(sel).forEach((el) => {
          try {
            if (typeof el.click === "function") el.click();
            else el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
          } catch (_) {}
        });
      });
    });
  } catch (_) {}
}

async function dumpPageData(page, label = "Tự động") {
  if (!page || page.isClosed()) return;
  const currentUrl = page.url();
  if (!currentUrl || currentUrl.startsWith("about:blank")) return;

  console.log(`\n----------------------------------------------------------`);
  console.log(`📥 [EXTRACT] ${label} - URL: ${currentUrl}`);

  // 1. Screenshot
  try {
    const shotPath = path.join(__dirname, "withdraw_screenshot.png");
    await page.screenshot({ path: shotPath });
    console.log(`📸 [1/3] Đã lưu ảnh: withdraw_screenshot.png`);
  } catch (e) {
    console.log(`[Ảnh]: ${e.message}`);
  }

  // 2. HTML DOM
  try {
    const html = await page.content();
    const htmlPath = path.join(__dirname, "withdraw_page.html");
    fs.writeFileSync(htmlPath, html, "utf8");
    console.log(`📄 [2/3] Đã lưu mã nguồn HTML: withdraw_page.html (${html.length.toLocaleString()} ký tự)`);
  } catch (e) {
    console.log(`[HTML]: ${e.message}`);
  }

  // 3. JSON Elements
  try {
    const elementsData = await page.evaluate(() => {
      const res = {
        title: document.title,
        url: window.location.href,
        time: new Date().toLocaleString(),
        inputs: [],
        buttons: [],
        selects: [],
        bankAccounts: [],
        labels: [],
        tips: []
      };

      // Inputs & Textareas
      document.querySelectorAll("input, textarea").forEach((el, i) => {
        res.inputs.push({
          index: i,
          type: el.type,
          name: el.name || null,
          id: el.id || null,
          placeholder: el.placeholder || null,
          value: el.value || null,
          class: el.className || null,
          disabled: el.disabled
        });
      });

      // Buttons
      document.querySelectorAll("button, [role='button'], input[type='button'], input[type='submit'], .submit-btn, .btn, a").forEach((el, i) => {
        const text = (el.innerText || el.textContent || "").trim();
        if (text || el.id || el.className) {
          res.buttons.push({
            index: i,
            text: text.slice(0, 80),
            id: el.id || null,
            class: el.className || null,
            disabled: el.disabled || false
          });
        }
      });

      // Select / Dropdown
      document.querySelectorAll("select, .van-dropdown-menu, .el-select, [class*='select']").forEach((el, i) => {
        const opts = Array.from(el.querySelectorAll("option, li, [class*='item']")).map(o => (o.innerText || "").trim()).filter(Boolean);
        res.selects.push({
          index: i,
          id: el.id || null,
          class: el.className || null,
          text: (el.innerText || "").trim().slice(0, 80),
          options: opts.slice(0, 15)
        });
      });

      // Bank & Card items
      document.querySelectorAll("[class*='bank'], [class*='card'], [class*='account'], .bank-item").forEach((el, i) => {
        const txt = (el.innerText || "").trim();
        if (txt && txt.length < 200) {
          res.bankAccounts.push({
            index: i,
            class: el.className || null,
            text: txt
          });
        }
      });

      // Labels & Instructions
      document.querySelectorAll("label, .van-field__label, .el-form-item__label, [class*='tip'], [class*='rule']").forEach((el, i) => {
        const txt = (el.innerText || "").trim();
        if (txt && txt.length < 200) {
          res.labels.push({
            index: i,
            class: el.className || null,
            text: txt
          });
        }
      });

      return res;
    });

    const jsonPath = path.join(__dirname, "withdraw_elements.json");
    fs.writeFileSync(jsonPath, JSON.stringify(elementsData, null, 2), "utf8");
    console.log(`📊 [3/3] Đã lưu cấu trúc Element: withdraw_elements.json`);
    console.log(`   ├─ Inputs: ${elementsData.inputs.length} ô nhập liệu`);
    console.log(`   ├─ Buttons: ${elementsData.buttons.length} nút bấm`);
    console.log(`   ├─ Selects: ${elementsData.selects.length} dropdown`);
    console.log(`   └─ Bank cards: ${elementsData.bankAccounts.length} mục thẻ`);
  } catch (e) {
    console.log(`[JSON]: ${e.message}`);
  }
  console.log(`----------------------------------------------------------\n`);
}

async function start() {
  console.log(`[LAUNCH] Khởi chạy Firefox Native (Headless=false)...`);
  const browser = await firefox.launch({
    headless: false,
    firefoxUserPrefs: {
      "network.trr.mode": 5,
      "network.dns.disableIPv6": true,
      "media.autoplay.default": 0,
      "media.autoplay.enabled.user-gestures-needed": false,
      "dom.webnotifications.enabled": false,
      "webgl.force-enabled": true,
      "layers.acceleration.force-enabled": true,
      "gfx.webrender.all": true,
      "gfx.canvas.accelerated": true,
      "layout.frame_rate": 60,
    }
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "vi-VN",
    ignoreHTTPSErrors: true,
  });

  // Chặn bẫy văng about:blank
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    window.chrome = { runtime: {} };
    const noop = () => {};
    window.console.clear = noop;
    window.console.table = noop;
    window.console.dir = noop;

    const originalReplace = window.location.replace;
    window.location.replace = function(url) {
      if (typeof url === "string" && url.includes("about:blank")) {
        console.warn("[ANTI-BOT] Blocked replace to about:blank");
        return;
      }
      return originalReplace.apply(this, arguments);
    };

    const originalAssign = window.location.assign;
    window.location.assign = function(url) {
      if (typeof url === "string" && url.includes("about:blank")) {
        console.warn("[ANTI-BOT] Blocked assign to about:blank");
        return;
      }
      return originalAssign.apply(this, arguments);
    };
  }).catch(() => {});

  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  page.setDefaultNavigationTimeout(60000);

  console.log(`[NAVIGATE] Đang kết nối tới ${DOMAIN}...`);
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto(DOMAIN, { waitUntil: "commit", timeout: 45000 });
      console.log(`[NAVIGATE] Đã vào trang ${DOMAIN} thành công!`);
      break;
    } catch (err) {
      console.log(`[NAVIGATE Lần ${attempt}]: ${err.message}`);
      await helper.delay(2000);
    }
  }

  await page.bringToFront().catch(() => {});
  await helper.delay(3000);
  await dismissPopups(page);

  // Đăng nhập
  console.log(`[LOGIN] Đang mở modal đăng nhập...`);
  await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll("a, button, span, div"));
    const btn = all.find(e => (e.innerText || "").trim().toUpperCase() === "ĐĂNG NHẬP" && e.offsetParent !== null);
    if (btn) btn.click();
  });

  await helper.delay(1500);

  // Điền Tên người dùng & Mật khẩu
  try {
    console.log(`[LOGIN] Đang điền tài khoản: ${USERNAME}...`);
    const userInp = await page.waitForSelector(
      "input[placeholder*='Tên người dùng'], input[placeholder*='người dùng'], input[placeholder*='tài khoản'], input[name='username'], .username_input",
      { timeout: 8000 }
    ).catch(() => null);

    if (userInp) {
      await userInp.fill(USERNAME);
      await helper.delay(300);
    }

    const passInp = await page.waitForSelector(
      "input[placeholder*='Mật khẩu'], input[placeholder*='mật khẩu'], input[name='password'], input[type='password'], .password_input",
      { timeout: 8000 }
    ).catch(() => null);

    if (passInp) {
      await passInp.fill(PASSWORD);
      await helper.delay(300);
    }

    // Submit ĐĂNG NHẬP bên trong modal
    console.log(`[LOGIN] Bấm nút ĐĂNG NHẬP trong modal...`);
    await page.evaluate(() => {
      const modal = document.querySelector(".van-popup, .modal, .dialog, div[class*='login'], div[class*='dialog']") || document.body;
      const allBtns = Array.from(modal.querySelectorAll("button, [role='button'], div, span"));
      const submitBtn = allBtns.find(b => (b.innerText || "").trim().toUpperCase() === "ĐĂNG NHẬP" && b.offsetParent !== null && !b.classList.contains("header_btn"));
      if (submitBtn) {
        submitBtn.click();
      }
    });

    await helper.delay(4000);
  } catch (e) {
    console.log(`[LOGIN EXCEPTION]: ${e.message}`);
  }

  await dismissPopups(page);
  await helper.delay(2000);

  // Bấm vào mục "Rút tiền"
  console.log(`[WITHDRAW] Đang tìm và bấm vào mục 'Rút tiền'...`);
  let clicked = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll("a, button, span, div, li, p"));
    const w = all.find(e => {
      const t = (e.innerText || "").trim();
      const h = e.getAttribute("href") || "";
      const c = e.className || "";
      return (t === "Rút tiền" || t === "Rút Tiền" || t === "RÚT TIỀN" || h.includes("withdraw") || c.includes("withdraw")) && e.offsetParent !== null;
    });
    if (w) {
      w.click();
      return true;
    }
    return false;
  });

  if (!clicked) {
    const selList = ["a:has-text('Rút tiền')", "button:has-text('Rút tiền')", "span:has-text('Rút tiền')", ".header_nav_withdraw", ".btn-withdraw"];
    for (const s of selList) {
      try {
        const el = await page.$(s);
        if (el && (await el.isVisible())) {
          await el.click().catch(() => {});
          clicked = true;
          break;
        }
      } catch (_) {}
    }
  }

  console.log(`[WITHDRAW CLICK] ${clicked ? "Đã bấm vào Rút tiền!" : "Chưa bấm tự động (bạn có thể click trực tiếp trên màn hình)"}`);

  await helper.delay(4000);
  await dismissPopups(page);

  // Tải dữ liệu ban đầu
  await dumpPageData(page, "Lần đầu");

  console.log(`\n======================================================================`);
  console.log(`🖥️  TRÌNH DUYỆT ĐANG HIỆN TRÊN MÀN HÌNH CỦA BẠN!`);
  console.log(`👉 Bạn có thể xem và thao tác trực tiếp trên màn hình.`);
  console.log(`🔄 Hệ thống sẽ tự động cập nhật lại toàn bộ Element & HTML sau mỗi 5s.`);
  console.log(`======================================================================\n`);

  let count = 0;
  while (true) {
    await helper.delay(5000);
    count++;
    const pages = context.pages();
    const active = pages.find(p => p.url() && !p.url().startsWith("about:blank")) || page;
    await dumpPageData(active, `Live Update #${count}`);
  }
}

start().catch(err => {
  console.error("[CRITICAL ERROR]", err);
});
