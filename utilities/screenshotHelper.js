const fs = require("fs").promises;
const fsSync = require("fs");
const path = require("path");

const SCREENSHOT_DIR = path.join(__dirname, "../public/screenshots");
const MAX_AGE_MS = 3 * 24 * 60 * 60 * 1000; // 3 days

/**
 * Ensure screenshot directory exists
 */
function ensureDir() {
  if (!fsSync.existsSync(SCREENSHOT_DIR)) {
    fsSync.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

const MAX_FILES = 12;
const MIN_REAL_BYTES = 10000; // Ảnh trống dưới 10KB; ảnh bàn thật 20KB-2MB

async function fileLooksBlank(filepath) {
  try {
    const st = await fs.stat(filepath);
    return !st.size || st.size < MIN_REAL_BYTES;
  } catch (e) {
    return true;
  }
}

/**
 * Clean up screenshots: khi đủ 30 ảnh, làm lệnh xóa sạch TOÀN BỘ ảnh cũ để bắt đầu đợt ảnh mới
 */
async function cleanOldScreenshots(keepFilename = null) {
  try {
    ensureDir();
    const files = await fs.readdir(SCREENSHOT_DIR);
    const pngFiles = files.filter((f) => f.endsWith(".png"));

    if (pngFiles.length >= MAX_FILES) {
      console.log(`[SCREENSHOT CLEANUP] Đã đạt ${pngFiles.length} ảnh (>= ${MAX_FILES}). Đang xoá SẠCH toàn bộ ảnh cũ...`);
      for (const file of pngFiles) {
        if (file === keepFilename) continue;
        const filePath = path.join(SCREENSHOT_DIR, file);
        try {
          await fs.unlink(filePath);
        } catch (e) {}
      }
      console.log(`[SCREENSHOT CLEANUP] Đã xoá sạch ${pngFiles.length} ảnh cũ thành công! Bắt đầu đợt lưu mới.`);
    }
  } catch (err) {
    console.error("[SCREENSHOT CLEANUP ERROR]", err.message);
  }
}

/**
 * Clean up old screenshots specifically for the given table before saving a new one
 */
async function cleanOldScreenshotsForTable(tableName, keepFilename = null) {
  try {
    ensureDir();
    const cleanTable = String(tableName).trim().toUpperCase().replace(/[^A-Z0-9]/g, "") || "UNKNOWN";
    const prefix = `sexy_${cleanTable}_`;
    const files = await fs.readdir(SCREENSHOT_DIR);
    const matches = [];
    for (const file of files) {
      if (!file.startsWith(prefix) || !file.endsWith(".png")) continue;
      const filePath = path.join(SCREENSHOT_DIR, file);
      try {
        const st = await fs.stat(filePath);
        matches.push({ file, filePath, mtime: st.mtimeMs });
      } catch (e) {}
    }
    matches.sort((a, b) => b.mtime - a.mtime);
    const keep = new Set();
    if (keepFilename) keep.add(keepFilename);
    let keptPrev = 0;
    for (const m of matches) {
      if (keep.has(m.file)) continue;
      // Giữ 1 round cũ (ảnh mới nhì) để ảo/báo bàn bê sexy_* — không xóa sạch.
      if (keptPrev < 1) {
        keep.add(m.file);
        keptPrev += 1;
        continue;
      }
      try {
        await fs.unlink(m.filePath);
        if (process.env.SERVER_VERBOSE_LOG === "true") {
          console.log(`[SCREENSHOT CLEANUP] Xóa round cũ hơn bàn ${cleanTable}: ${m.file}`);
        }
      } catch (e) {}
    }
  } catch (err) {
    console.error(`[SCREENSHOT CLEANUP ERROR] Table ${tableName}:`, err.message);
  }
}

/**
 * Cắt viền đen letterbox (căn giữa) — chỉ xử lý file ảnh, không đụng CSS game.
 */
async function trimBlackBorders(filepath, threshold = 28, pad = 2, darkRatio = 0.9) {
  try {
    const sharp = require("sharp");
    const { data, info } = await sharp(filepath)
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const { width, height, channels } = info;
    const isDark = (i) =>
      data[i] <= threshold && data[i + 1] <= threshold && data[i + 2] <= threshold;

    const rowDark = (y) => {
      let d = 0;
      let n = 0;
      const step = width > 1200 ? 2 : 1;
      for (let x = 0; x < width; x += step) {
        if (isDark((y * width + x) * channels)) d++;
        n++;
      }
      return d / Math.max(1, n);
    };
    const colDark = (x, y0, y1) => {
      let d = 0;
      let n = 0;
      const step = height > 800 ? 2 : 1;
      for (let y = y0; y <= y1; y += step) {
        if (isDark((y * width + x) * channels)) d++;
        n++;
      }
      return d / Math.max(1, n);
    };

    let top = 0;
    let bottom = height - 1;
    let left = 0;
    let right = width - 1;
    while (top < height - 1 && rowDark(top) >= darkRatio) top++;
    while (bottom > top && rowDark(bottom) >= darkRatio) bottom--;
    while (left < width - 1 && colDark(left, top, bottom) >= darkRatio) left++;
    while (right > left && colDark(right, top, bottom) >= darkRatio) right--;

    top = Math.max(0, top - pad);
    left = Math.max(0, left - pad);
    bottom = Math.min(height - 1, bottom + pad);
    right = Math.min(width - 1, right + pad);

    const cropW = right - left + 1;
    const cropH = bottom - top + 1;
    const trimmed =
      top > 2 || left > 2 || height - 1 - bottom > 2 || width - 1 - right > 2;
    if (!trimmed || cropW < 200 || cropH < 150) return false;

    const ext = path.extname(filepath).toLowerCase();
    const tmpPath = filepath + ".crop.tmp" + (ext || ".png");
    let pipeline = sharp(filepath).extract({
      left,
      top,
      width: cropW,
      height: cropH,
    });
    if (ext === ".jpg" || ext === ".jpeg") {
      pipeline = pipeline.jpeg({
        quality: Math.min(100, Math.max(70, Number(process.env.CAPTURE_JPEG_QUALITY || 95) || 95)),
        mozjpeg: true,
      });
    } else {
      pipeline = pipeline.png();
    }
    await pipeline.toFile(tmpPath);
    await fs.unlink(filepath).catch(() => {});
    await fs.rename(tmpPath, filepath);
    console.log(
      `[SCREENSHOT CROP] center-trim → ${cropW}x${cropH} (was ${width}x${height})`
    );
    return true;
  } catch (e) {
    console.warn(`[SCREENSHOT CROP] skip: ${e.message}`);
    return false;
  }
}

/**
 * Màn hình bị đá phiên của Sexy được vẽ trên canvas nên DOM không có text.
 * Nhận diện trực tiếp ảnh: nền gần như tối hoàn toàn + cụm chữ hồng/đỏ lớn.
 */
async function isFatalSessionScreenshot(filepath) {
  try {
    const { Jimp } = require("jimp");
    const image = await Jimp.read(filepath);
    const { data, width, height } = image.bitmap;
    const pixels = Math.max(1, width * height);
    let dark = 0;
    let pink = 0;
    let redDark = 0;
    let centerPink = 0;
    const pinkByRow = new Array(height).fill(0);

    // Lấy mẫu toàn ảnh; bước 2 vẫn đủ chính xác và giảm CPU trên VPS.
    const step = pixels > 800000 ? 2 : 1;
    for (let p = 0; p < pixels; p += step) {
      const i = p * 4;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      if (r < 55 && g < 45 && b < 50) dark += 1;
      // Màn hết phiên mới có nền gradient đỏ sẫm, không đạt ngưỡng "đen" cũ.
      if (g < 55 && r > g * 1.15 && b > g * 1.05) redDark += 1;
      if (r > 95 && r > g * 1.35 && b > 55 && b > g * 1.1) {
        pink += 1;
        const y = Math.floor(p / width);
        const x = p % width;
        pinkByRow[y] += 1;
        if (
          x > width * 0.15 &&
          x < width * 0.9 &&
          y > height * 0.35 &&
          y < height * 0.65
        ) {
          centerPink += 1;
        }
      }
    }

    const sampled = Math.ceil(pixels / step);
    const darkRatio = dark / sampled;
    const pinkRatio = pink / sampled;
    const redDarkRatio = redDark / sampled;
    const centerPinkRatio = centerPink / sampled;
    const peakPinkRowRatio =
      Math.max(...pinkByRow) / Math.max(1, width / step);
    const fatal =
      (darkRatio >= 0.65 || redDarkRatio >= 0.8) &&
      pinkRatio >= 0.004 &&
      centerPinkRatio >= 0.003 &&
      peakPinkRowRatio >= 0.15;
    if (fatal) {
      console.error(
        `[SCREENSHOT FATAL UI] dark=${darkRatio.toFixed(3)} ` +
          `redDark=${redDarkRatio.toFixed(3)} pink=${pinkRatio.toFixed(3)} ` +
          `center=${centerPinkRatio.toFixed(3)} peak=${peakPinkRowRatio.toFixed(3)} ` +
          "— SESSION_EXPIRED"
      );
    }
    return fatal;
  } catch (error) {
    console.warn(`[SCREENSHOT FATAL UI] Không đọc được ảnh: ${error.message}`);
    return false;
  }
}

/**
 * Save screenshot from Playwright page or frame
 * @param {object} target - Playwright Page or Frame
 * @param {string} tableName - e.g. "C04"
 * @param {object} options - optional { roundNum, shoeNum, isFullPage }
 */
async function saveScreenshot(target, tableName = "UNKNOWN", options = {}) {
  try {
    ensureDir();

    const cleanTable = String(tableName).trim().toUpperCase().replace(/[^A-Z0-9]/g, "") || "UNKNOWN";
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const roundStr = options.roundNum ? `_R${options.roundNum}` : "";
    const winnerStr = options.resultWinner ? `_W${String(options.resultWinner).trim().toUpperCase()}` : "";
    const filename = `sexy_${cleanTable}${roundStr}${winnerStr}_${timestamp}.png`;
    const filepath = path.join(SCREENSHOT_DIR, filename);

    let saved = false;

    // Firefox thường treo ở ElementHandle.screenshot() vì chờ iframe "stable".
    // Chụp page theo bounding box iframe trước: không scroll, không chờ font/animation.
    // Chụp trực tiếp iframe game / page không làm giật khung hình
    if (options.pageObj && typeof options.pageObj.screenshot === "function") {
      const gameIframe = await options.pageObj
        .$("iframe#seamless-game, iframe[name='seamless-game']")
        .catch(() => null);
      const box = gameIframe
        ? await Promise.race([
            gameIframe.boundingBox().catch(() => null),
            new Promise((resolve) => setTimeout(() => resolve(null), 1500)),
          ])
        : null;
      if (box && box.width > 100 && box.height > 100) {
        try {
          await options.pageObj.screenshot({
            path: filepath,
            clip: {
              x: Math.max(0, box.x),
              y: Math.max(0, box.y),
              width: box.width,
              height: box.height,
            },
            timeout: 8000,
            type: "png",
          });
          console.log(`[SCREENSHOT SAVED CLIPPED GAME] ${filepath}`);
          saved = !(await fileLooksBlank(filepath));
          if (!saved) console.warn(`[SCREENSHOT] clip trống — thử fallback`);
        } catch (clipErr) {
          console.warn(
            `[SCREENSHOT WARNING] Chụp clip iframe thất bại (${clipErr.message})`
          );
        }
      }
    }

    // Chỉ dùng element/frame khi không có pageObj (tool gọi độc lập).
    if (
      !saved &&
      !options.pageObj &&
      target &&
      typeof target.screenshot === "function"
    ) {
      try {
        await target.screenshot({
          path: filepath,
          fullPage: false,
          timeout: 10000,
          type: "png",
        });
        console.log(`[SCREENSHOT SAVED ELEMENT/FRAME] ${filepath}`);
        saved = true;
        if (await fileLooksBlank(filepath)) {
          console.warn(
            `[SCREENSHOT] element/frame trống (${filepath}) — thử page fallback`
          );
          saved = false;
        }
      } catch (elemErr) {
        console.warn(`[SCREENSHOT WARNING] Chụp element thất bại (${elemErr.message}), cắt trực tiếp vùng iframe game...`);
      }
    }

    if (!saved && options.pageObj && typeof options.pageObj.screenshot === "function") {
      if (!saved) {
        await options.pageObj.screenshot({
          path: filepath,
          fullPage: false,
          timeout: 10000,
          type: "png",
        });
        console.log(`[SCREENSHOT SAVED PAGE FALLBACK] ${filepath}`);
        saved = true;
      }
    }

    if (!saved) throw new Error("Target does not support .screenshot()");
    if (await fileLooksBlank(filepath)) {
      const st = await fs.stat(filepath).catch(() => ({ size: 0 }));
      console.warn(`[SCREENSHOT REJECT] ${filename} trống ${st.size || 0}B`);
      await fs.unlink(filepath).catch(() => {});
      return { success: false, error: "BLANK_CAPTURE" };
    }

/**
 * Nhận diện màn hình bị "Tín hiệu bị mất" (vùng video ở giữa tối đen > 80%)
 */
async function isSignalLostScreenshot(filepath) {
  // Đã tắt kiểm tra tối màu pixel để tránh nhận nhầm bàn nền tối/dealer đổi bài là mất tín hiệu
  return false;
}

    const winnerNorm = String(options.resultWinner || "").trim().toUpperCase();
    const skipFatalUiCheck =
      options.skipFatalUiCheck === true ||
      winnerNorm === "B" ||
      winnerNorm === "P" ||
      winnerNorm === "T";

    // Không bao giờ lưu/gửi ảnh overlay kick. Xóa file ngay và báo session restart.
    if (!skipFatalUiCheck && (await isFatalSessionScreenshot(filepath))) {
      await fs.unlink(filepath).catch(() => {});
      return {
        success: false,
        fatalUi: "SESSION_EXPIRED",
        error: "SESSION_EXPIRED_CANVAS",
      };
    }

    // Chỉ crop file ảnh (viền đen 4 phía), không sửa CSS game
    if (options.trimBlack !== false) {
      await trimBlackBorders(filepath);
    }

    // Chỉ xóa ảnh cũ sau khi ảnh mới đã ghi xong; luôn giữ file vừa tạo.
    await cleanOldScreenshotsForTable(tableName, filename);

    return {
      success: true,
      filename,
      filepath,
      url: `/screenshots/${filename}`,
    };
  } catch (error) {
    console.error(`[SCREENSHOT ERROR] Table ${tableName}:`, error.message);
    return { success: false, error: error.message };
  }
}

module.exports = {
  saveScreenshot,
  cleanOldScreenshots,
  cleanOldScreenshotsForTable,
  trimBlackBorders,
  isFatalSessionScreenshot,
  SCREENSHOT_DIR,
};
