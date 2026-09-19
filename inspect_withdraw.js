const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
require("dotenv").config({ path: path.resolve(__dirname, ".env") });
const { imageCapcha, helper } = require("./utilities");

const DOMAIN = process.env.DOMAIN || "https://www.rr9900.com";
const USERNAME = process.env.USERNAME_ACCOUNT || "bosdx22";
const PASSWORD = process.env.PASSWORD_ACCOUNT || "yocvsjwc";

console.log("==================================================");
console.log(`[START] KHỞI ĐỘNG TRÌNH DUYỆT TRỰC QUAN TRÊN MÀN HÌNH`);
console.log(`[TARGET URL] ${DOMAIN}`);
console.log(`[ACCOUNT] ${USERNAME}`);
console.log("==================================================");

async function dismissSitePopups(targetPage) {
  if (!targetPage || targetPage.isClosed()) return;
  const closeFn = () => {
    const clickSafe = (el) => {
      try {
        if (!el) return;
        if (typeof el.click === "function") el.click();
        else el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      } catch (_) {}
    };

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
      ".sign-in-rules .close-btn",
      "i.van-icon-cross"
    ];

    selectors.forEach((sel) => {
      document.querySelectorAll(sel).forEach(clickSafe);
    });

    const all = Array.from(document.querySelectorAll("div, section, aside"));
    for (const box of all) {
      const txt = (box.innerText || "").slice(0, 80);
      if (/Thông báo/i.test(txt)) {
        const closer = box.querySelector(".tcg_modal_close, .close, .close-btn, [class*='close'], i, svg, span, button");
        if (closer) clickSafe(closer);
      }
    }
  };

  await targetPage.evaluate(closeFn).catch(() => {});
  for (const frame of targetPage.frames() || []) {
    await frame.evaluate(closeFn).catch(() => {});
  }
}

async function fillInputSafe(page, selector, value) {
  try {
    const el = await page.waitForSelector(selector, { timeout: 3000 }).catch(() => null);
    if (el) {
      await el.fill(value);
      return true;
    }
  } catch (_) {}

  return await page.evaluate(({ sel, v }) => {
    const el = document.querySelector(sel);
    if (el) {
      el.value = v;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    return false;
  }, { sel: selector, v: value }).catch(() => false);
}

async function dumpWithdrawData(p, trigger = "auto") {
  if (!p || p.isClosed()) return;
  const currentUrl = p.url();
  if (!currentUrl || currentUrl === "about:blank") return;

  console.log(`\n==================================================`);
  console.log(`🚀 [DUMP] ĐANG TRÍCH XUẤT ELEMENT & HTML (${trigger})`);
  console.log(`[URL HIỆN TẠI] ${currentUrl}`);
  console.log(`==================================================`);

  // 1. Chụp ảnh màn hình
  const screenshotPath = path.join(__dirname, "withdraw_screenshot.png");
  try {
    await p.screenshot({ path: screenshotPath, fullPage: false });
    console.log(`📸 [1/3] Đã lưu ảnh chụp màn hình: withdraw_screenshot.png`);
  } catch (err) {
    console.error(`[LỖI CHỤP ẢNH] ${err.message}`);
  }

  // 2. Lưu toàn bộ HTML DOM
  try {
    const fullHtml = await p.content();
    const htmlPath = path.join(__dirname, "withdraw_page.html");
    fs.writeFileSync(htmlPath, fullHtml, "utf8");
    console.log(`📄 [2/3] Đã lưu mã nguồn HTML: withdraw_page.html (${fullHtml.length.toLocaleString()} ký tự)`);
  } catch (err) {
    console.error(`[LỖI LƯU HTML] ${err.message}`);
  }

  // 3. Trích xuất cây DOM chi tiết
  try {
    const extractedData = await p.evaluate(() => {
      const data = {
        timestamp: new Date().toISOString(),
        title: document.title,
        url: window.location.href,
        summary: {
          totalInputs: 0,
          totalButtons: 0,
          totalSelects: 0,
          totalCards: 0
        },
        inputs: [],
        buttons: [],
        selectsAndDropdowns: [],
        bankCardsAndAccounts: [],
        formLabelsAndFields: [],
        instructionsAndTips: [],
        modalElements: []
      };

      // Inputs
      document.querySelectorAll("input, textarea").forEach((inp, idx) => {
        data.inputs.push({
          index: idx,
          tag: inp.tagName.toLowerCase(),
          type: inp.type,
          name: inp.name || null,
          id: inp.id || null,
          class: inp.className || null,
          placeholder: inp.placeholder || null,
          value: inp.value || null,
          disabled: inp.disabled,
          readOnly: inp.readOnly,
          autocomplete: inp.autocomplete || null,
          min: inp.min || null,
          max: inp.max || null
        });
      });

      // Buttons
      document.querySelectorAll("button, input[type='button'], input[type='submit'], [role='button'], a.btn, .submit-btn, .confirm-btn, .tab-item, .nav-item").forEach((btn, idx) => {
        const text = (btn.innerText || btn.textContent || "").trim();
        if (text || btn.id || btn.className) {
          data.buttons.push({
            index: idx,
            tag: btn.tagName.toLowerCase(),
            type: btn.type || null,
            id: btn.id || null,
            class: btn.className || null,
            text: text.slice(0, 100),
            disabled: btn.disabled || false
          });
        }
      });

      // Dropdown / Select
      document.querySelectorAll("select, .el-select, .van-dropdown-menu, [class*='select'], [class*='dropdown']").forEach((sel, idx) => {
        const options = Array.from(sel.querySelectorAll("option, li, [class*='item']")).map(o => (o.innerText || "").trim()).filter(Boolean);
        data.selectsAndDropdowns.push({
          index: idx,
          tag: sel.tagName.toLowerCase(),
          id: sel.id || null,
          class: sel.className || null,
          text: (sel.innerText || "").trim().slice(0, 100),
          options: options.slice(0, 20)
        });
      });

      // Ngân hàng / Thẻ đã thêm / Số tài khoản
      document.querySelectorAll("[class*='bank'], [class*='card'], [class*='account'], .bank-item, .card-item, .wallet-item").forEach((b, idx) => {
        const txt = (b.innerText || "").trim();
        if (txt && txt.length < 250) {
          data.bankCardsAndAccounts.push({
            index: idx,
            class: b.className || null,
            text: txt
          });
        }
      });

      // Form Labels & Fields
      document.querySelectorAll("label, .form-item, .form-group, .van-field__label, .el-form-item__label, .item-label, .field-label").forEach((lbl, idx) => {
        const txt = (lbl.innerText || "").trim();
        if (txt && txt.length < 150) {
          data.formLabelsAndFields.push({
            index: idx,
            class: lbl.className || null,
            text: txt
          });
        }
      });

      // Tips / Quy tắc rút tiền
      document.querySelectorAll("[class*='tip'], [class*='rule'], [class*='notice'], [class*='warning'], .prompt, .description").forEach((t, idx) => {
        const txt = (t.innerText || "").trim();
        if (txt && txt.length < 500) {
          data.instructionsAndTips.push({
            index: idx,
            class: t.className || null,
            text: txt
          });
        }
      });

      // Visible Modals/Popups
      document.querySelectorAll(".van-dialog, .el-dialog, .modal, [class*='dialog'], [class*='modal']").forEach((m, idx) => {
        if (m.offsetParent !== null) {
          data.modalElements.push({
            index: idx,
            class: m.className || null,
            text: (m.innerText || "").slice(0, 500)
          });
        }
      });

      data.summary.totalInputs = data.inputs.length;
      data.summary.totalButtons = data.buttons.length;
      data.summary.totalSelects = data.selectsAndDropdowns.length;
      data.summary.totalCards = data.bankCardsAndAccounts.length;

      return data;
    });

    const jsonPath = path.join(__dirname, "withdraw_elements.json");
    fs.writeFileSync(jsonPath, JSON.stringify(extractedData, null, 2), "utf8");
    console.log(`📊 [3/3] Đã lưu danh sách Element vào: withdraw_elements.json`);
    console.log(`   ├─ Ô nhập liệu (Inputs): ${extractedData.summary.totalInputs}`);
    console.log(`   ├─ Nút bấm (Buttons): ${extractedData.summary.totalButtons}`);
    console.log(`   ├─ Danh sách chọn (Selects): ${extractedData.summary.totalSelects}`);
    console.log(`   ├─ Thẻ/Tài khoản ngân hàng: ${extractedData.summary.totalCards}`);
    console.log(`   └─ Nhãn & Quy tắc (Labels/Tips): ${extractedData.instructionsAndTips.length}`);
    console.log(`==================================================\n`);
  } catch (err) {
    console.error(`[LỖI TRÍCH XUẤT DOM] ${err.message}`);
  }
}

async function main() {
  const chromeWinPaths = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    (process.env.LOCALAPPDATA || "") + "\\Google\\Chrome\\Application\\chrome.exe",
  ];
  const foundChrome = chromeWinPaths.find((p) => p && fs.existsSync(p));

  const userDataDir = path.join(
    process.env.LOCALAPPDATA || "C:\\temp",
    "SexyChromeProfile_NS1"
  );

  console.log(`[CHROME] Khởi động Google Chrome thật (Headed, GPU Native): ${foundChrome || "chrome"}`);
  console.log(`[PROFILE] ${userDataDir}`);

  const context = await chromium.launchPersistentContext(userDataDir, {
    executablePath: foundChrome,
    headless: false,
    viewport: null,
    args: [
      "--start-maximized",
      "--no-first-run",
      "--no-default-browser-check",
      "--ignore-gpu-blocklist",
      "--enable-gpu-rasterization",
      "--disable-blink-features=AutomationControlled",
    ],
    ignoreDefaultArgs: ["--enable-automation"],
    ignoreHTTPSErrors: true,
  });

  await context.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    window.chrome = { runtime: {} };
    const noop = () => {};
    window.console.clear = noop;
    window.console.table = noop;
    window.console.dir = noop;
    const originalReplace = window.location.replace;
    window.location.replace = function(url) {
      if (typeof url === "string" && url.includes("about:blank")) return;
      return originalReplace.apply(this, arguments);
    };
  }).catch(() => {});

  let page = context.pages().length > 0 ? context.pages()[0] : await context.newPage();
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(60000);

  console.log(`[NAVIGATE] Đang truy cập: ${DOMAIN}`);
  for (let g = 0; g < 3; g++) {
    try {
      await page.goto(DOMAIN, {
        waitUntil: "commit",
        timeout: 45000,
      });
      console.log(`[NAVIGATE] Kết nối thành công tới ${DOMAIN}!`);
      break;
    } catch (e) {
      console.log(`[GOTO] lần ${g + 1}/3: ${e.message}`);
      await helper.delay(2000);
    }
  }

  await page.bringToFront().catch(() => {});
  await helper.delay(2000);
  await dismissSitePopups(page);

  // 1. Kiểm tra trạng thái đăng nhập
  const isLoggedIn = await page.evaluate(() => {
    const txt = document.body ? document.body.innerText : "";
    const hasUser = document.querySelector(".user_info, .user-name, .header_user, .balance, .money, .account-info, .username_info");
    return hasUser !== null || txt.includes("bosdx22");
  });

  console.log(`[AUTH STATUS] Trạng thái đăng nhập: ${isLoggedIn ? "ĐÃ ĐĂNG NHẬP" : "CHƯA ĐĂNG NHẬP"}`);

  if (!isLoggedIn) {
    console.log(`[LOGIN] Bấm nút ĐĂNG NHẬP trên thanh header...`);
    // Click nút ĐĂNG NHẬP
    await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll("a, button, span, div"));
      const loginBtn = els.find(e => (e.innerText || "").trim().toUpperCase() === "ĐĂNG NHẬP" && e.offsetParent !== null);
      if (loginBtn) {
        loginBtn.click();
        return true;
      }
      return false;
    });

    await helper.delay(1500);

    const userInputSelector = ".username_input, input[placeholder*='Tên đăng nhập'], input[placeholder*='tài khoản'], input[name='username'], input[type='text']";
    const passInputSelector = ".password_input, input[placeholder*='Mật khẩu'], input[name='password'], input[type='password']";

    console.log(`[LOGIN] Điền tài khoản: ${USERNAME}`);
    await fillInputSafe(page, userInputSelector, USERNAME);
    await helper.delay(300);

    console.log(`[LOGIN] Điền mật khẩu...`);
    await fillInputSafe(page, passInputSelector, PASSWORD);
    await helper.delay(300);

    // Captcha
    const captchaInput = await page.$(".captcha_input, div.captcha_box img, input[placeholder*='Mã xác minh'], input[placeholder*='mã xác nhận']").catch(() => null);
    if (captchaInput) {
      console.log(`[CAPTCHA] Đang giải mã captcha...`);
      try {
        const codeCapcha = await imageCapcha.getCodeCapchaLogin("withdraw_log", page);
        if (codeCapcha) {
          console.log(`[CAPTCHA] Mã captcha: ${codeCapcha}`);
          await fillInputSafe(page, process.env.INPUT_CAPCHA_LOGIN || ".captcha_input, input[placeholder*='Mã xác minh'], input[placeholder*='mã xác nhận']", codeCapcha);
        }
      } catch (captchaErr) {
        console.log(`[CAPTCHA] ${captchaErr.message}`);
      }
    }

    // Submit
    console.log(`[LOGIN] Nhấn submit đăng nhập...`);
    await page.evaluate(() => {
      const submitBtn = document.querySelector('button[type="submit"].submit_btn, button.submit_btn, button.login_btn, .login_btn, .submit_btn');
      if (submitBtn) submitBtn.click();
      else {
        const allBtns = Array.from(document.querySelectorAll("button, span.submit_btn, div.submit_btn"));
        const b = allBtns.find(x => (x.innerText || "").includes("Đăng nhập") || (x.innerText || "").includes("ĐĂNG NHẬP"));
        if (b) b.click();
      }
    }).catch(() => {});

    await helper.delay(4000);
    await dismissSitePopups(page);
  }

  // 2. Vào mục Rút tiền
  console.log(`[NAVIGATE] Đang tìm và nhấn vào mục "Rút tiền"...`);
  await helper.delay(1000);
  await dismissSitePopups(page);

  let clickedWithdraw = await page.evaluate(() => {
    const allEls = Array.from(document.querySelectorAll("a, button, span, div, li, p, i"));
    const match = allEls.find((el) => {
      const t = (el.innerText || "").trim();
      const href = el.getAttribute("href") || "";
      const cls = el.className || "";
      return (
        (t === "Rút tiền" || t === "Rút Tiền" || t === "RÚT TIỀN" || href.includes("withdraw") || cls.includes("withdraw")) &&
        el.offsetParent !== null
      );
    });
    if (match) {
      match.click();
      return true;
    }
    return false;
  });

  if (!clickedWithdraw) {
    // Thử các selector thông dụng
    const selectors = [
      "a:has-text('Rút tiền')",
      "button:has-text('Rút tiền')",
      "span:has-text('Rút tiền')",
      "div:has-text('Rút tiền')",
      ".header_nav_withdraw",
      ".btn-withdraw",
      "a[href*='withdraw']",
      "a[href*='withdrawal']",
      "a[href*='rut-tien']"
    ];
    for (const s of selectors) {
      try {
        const el = await page.$(s);
        if (el && (await el.isVisible().catch(() => false))) {
          await el.click().catch(() => {});
          clickedWithdraw = true;
          break;
        }
      } catch (_) {}
    }
  }

  console.log(`[CLICK RÚT TIỀN] ${clickedWithdraw ? "Đã bấm thành công vào Rút tiền!" : "Chưa bấm tự động (bạn có thể click trực tiếp trên Chrome)"}`);

  await helper.delay(4000);
  await dismissSitePopups(page);

  // 3. Trích xuất toàn bộ DOM & Screenshot
  await dumpWithdrawData(page, "Initial Extraction");

  console.log(`\n======================================================================`);
  console.log(`👁️ TRÌNH DUYỆT ĐANG MỞ TRỰC TIẾP TRÊN MÀN HÌNH CỦA BẠN!`);
  console.log(`👉 Bạn có thể xem và bấm vào bất kỳ tab/menu rút tiền nào.`);
  console.log(`🔄 Hệ thống sẽ tự động bắt DOM và xuất lại dữ liệu mới nhất sau mỗi 5s.`);
  console.log(`======================================================================\n`);

  let count = 0;
  while (true) {
    await helper.delay(5000);
    count++;
    const pages = context.pages();
    const active = pages.find(p => p.url() && !p.url().includes("about:blank")) || page;
    await dumpWithdrawData(active, `Live Sync #${count}`);
  }
}

main().catch((err) => {
  console.error("[MAIN CRITICAL ERROR]", err);
});
