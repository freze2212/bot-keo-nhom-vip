/**
 * Lobby baccarat: parse mã bàn, list card, click đúng mã, random N mã unique.
 * Dùng chung cho session + scripts/local-click-table.cjs
 */

function normTableCode(c) {
  if (!c) return "";
  const u = String(c).toUpperCase().trim();
  const m = u.match(/C?0*(\d+)/);
  return m ? `C${m[1].padStart(2, "0")}` : u;
}

function parseTableCode(txt) {
  const t = String(txt || "");
  const m1 = t.match(/Baccarat\s+(C\d+)/i);
  if (m1) return normTableCode(m1[1]);
  const m2 = t.match(/BTCB(\d+)/i);
  if (m2) return normTableCode(`C${m2[1]}`);
  const m3 = t.match(/\b(C\d{1,3})\b/i);
  if (m3) return normTableCode(m3[1]);
  return null;
}

/** Chạy trong page/frame.evaluate — trả list { code, text } unique */
function listTablesInDocumentEval() {
  const parseCode = (txt) => {
    const t = String(txt || "");
    const m1 = t.match(/Baccarat\s+(C\d+)/i);
    if (m1) return m1[1].toUpperCase();
    const m2 = t.match(/BTCB(\d+)/i);
    if (m2) return `C${String(m2[1]).padStart(2, "0")}`;
    const m3 = t.match(/\b(C\d{1,3})\b/i);
    if (m3) return m3[1].toUpperCase();
    return null;
  };
  const norm = (c) => {
    if (!c) return "";
    const u = String(c).toUpperCase();
    const m = u.match(/C?0*(\d+)/);
    return m ? `C${m[1].padStart(2, "0")}` : u;
  };

  const cards = Array.from(
    document.querySelectorAll(
      ".vue-recycle-scroller__item-view, .table-item, div.relative.cursor-pointer, [class*='card']"
    )
  );
  const seen = new Map();
  for (const card of cards) {
    const raw = card.innerText || card.textContent || "";
    const code = norm(parseCode(raw));
    if (!code || !/^C\d+$/.test(code)) continue;
    if (!seen.has(code)) {
      seen.set(code, {
        code,
        text: raw.replace(/\s+/g, " ").trim().slice(0, 80),
      });
    }
  }

  // Fallback: scan text nodes nếu scroller chưa đủ card
  if (seen.size < 3) {
    for (const el of document.querySelectorAll("div, span, button, a")) {
      const raw = (el.innerText || el.textContent || "").trim();
      if (raw.length > 120) continue;
      const code = norm(parseCode(raw));
      if (!code || !/^C\d+$/.test(code)) continue;
      if (!seen.has(code)) {
        seen.set(code, { code, text: raw.replace(/\s+/g, " ").slice(0, 80) });
      }
    }
  }

  return Array.from(seen.values()).sort((a, b) => {
    const na = parseInt(a.code.replace(/\D/g, ""), 10);
    const nb = parseInt(b.code.replace(/\D/g, ""), 10);
    return na - nb;
  });
}

/** Click card/text khớp prefer. allowFallback=false → miss nếu không thấy. */
function clickTableByCodeEval({ prefer, allowFallback, doubleClick = false }) {
  const parseCode = (txt) => {
    const t = String(txt || "");
    const m1 = t.match(/Baccarat\s+(C\d+)/i);
    if (m1) return m1[1].toUpperCase();
    const m2 = t.match(/BTCB(\d+)/i);
    if (m2) return `C${String(m2[1]).padStart(2, "0")}`;
    const m3 = t.match(/\b(C\d{1,3})\b/i);
    if (m3) return m3[1].toUpperCase();
    return null;
  };
  const norm = (c) => {
    if (!c) return "";
    const u = String(c).toUpperCase();
    const m = u.match(/C?0*(\d+)/);
    return m ? `C${m[1].padStart(2, "0")}` : u;
  };
  const want = prefer ? norm(prefer) : null;

  const fireClick = (el) => {
    try {
      el.scrollIntoView({ block: "center", inline: "center" });
    } catch (_) {}
    const types = [
      "pointerover",
      "pointerenter",
      "mouseover",
      "mouseenter",
      "pointerdown",
      "mousedown",
      "mouseup",
      "pointerup",
      "click",
    ];
    const run = () => {
      for (const type of types) {
        el.dispatchEvent(
          new MouseEvent(type, { bubbles: true, cancelable: true, view: window })
        );
      }
      if (el.click) el.click();
    };
    run();
    if (doubleClick) run();
    return norm(parseCode(el.innerText || el.textContent || ""));
  };

  const pickClickTarget = (card) =>
    card.querySelector("div.relative.cursor-pointer canvas") ||
    card.querySelector("div.relative.cursor-pointer video") ||
    card.querySelector("div.relative.cursor-pointer img") ||
    card.querySelector("div.relative.cursor-pointer") ||
    card.querySelector(".table-item") ||
    card;

  const tableCards = Array.from(
    document.querySelectorAll(".vue-recycle-scroller__item-view, .table-item")
  );

  if (want) {
    for (const card of tableCards) {
      const code = norm(parseCode(card.innerText || card.textContent || ""));
      if (code !== want) continue;
      const target = pickClickTarget(card);
      fireClick(target);
      return {
        ok: true,
        table: code,
        via: doubleClick ? "eval_pointer_dblclick" : "eval_pointer_click",
        target: {
          tag: target.tagName,
          cls: String(target.className || "").slice(0, 80),
        },
      };
    }
    if (!allowFallback) {
      return { ok: false, table: null, via: "miss" };
    }
  }

  if (tableCards.length > 0) {
    const card = tableCards[0];
    const code = norm(parseCode(card.innerText || card.textContent || ""));
    fireClick(pickClickTarget(card));
    return { ok: true, table: code, via: "fallback_first" };
  }
  return { ok: false, table: null, via: "empty" };
}

function pickRandomUnique(codes, count, exclude = []) {
  const ex = new Set((exclude || []).map(normTableCode).filter(Boolean));
  const pool = [...new Set((codes || []).map(normTableCode).filter(Boolean))].filter(
    (c) => !ex.has(c)
  );
  const n = Math.min(Math.max(0, count), pool.length);
  const shuffled = [...pool];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, n);
}

/**
 * Scroll lobby scroller vài lần rồi list bàn (Playwright frame).
 */
async function listTablesFromFrame(frame, { scrolls = 4 } = {}) {
  if (!frame) return [];
  const all = new Map();
  for (let i = 0; i < scrolls; i++) {
    const batch = await frame.evaluate(listTablesInDocumentEval).catch(() => []);
    for (const row of batch || []) {
      if (row?.code) all.set(normTableCode(row.code), row);
    }
    await frame
      .evaluate(() => {
        const scroller =
          document.querySelector(".vue-recycle-scroller") ||
          document.querySelector("[class*='recycle']") ||
          document.scrollingElement;
        if (scroller) scroller.scrollTop = (scroller.scrollTop || 0) + 400;
      })
      .catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
  }
  // scroll back top
  await frame
    .evaluate(() => {
      const scroller =
        document.querySelector(".vue-recycle-scroller") ||
        document.querySelector("[class*='recycle']") ||
        document.scrollingElement;
      if (scroller) scroller.scrollTop = 0;
    })
    .catch(() => {});

  return Array.from(all.values()).sort((a, b) => {
    const na = parseInt(a.code.replace(/\D/g, ""), 10);
    const nb = parseInt(b.code.replace(/\D/g, ""), 10);
    return na - nb;
  });
}

async function clickTableByCode(frame, tableCode, { allowFallback = false, doubleClick = false } = {}) {
  if (!frame) return { ok: false, table: null, via: "no_frame" };
  const want = normTableCode(tableCode);

  const firePointerClick = async (loc, via) => {
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    if (doubleClick) {
      await loc.dblclick({ timeout: 5000 });
    } else {
      await loc.click({ timeout: 5000 });
    }
    return { ok: true, table: want, via };
  };

  // Playwright trusted click — ưu tiên trước evaluate (synthetic click không mở bàn)
  try {
    const card = frame
      .locator(".vue-recycle-scroller__item-view, .table-item")
      .filter({ hasText: new RegExp(`Baccarat\\s+${want}\\b`, "i") })
      .first();
    if ((await card.count().catch(() => 0)) > 0) {
      const pointer = card.locator("div.relative.cursor-pointer").first();
      if ((await pointer.count().catch(() => 0)) > 0) {
        return firePointerClick(
          pointer,
          doubleClick ? "card_pointer_dblclick" : "card_pointer_click"
        );
      }
      return firePointerClick(
        card,
        doubleClick ? "card_wrapper_dblclick" : "card_wrapper_click"
      );
    }
  } catch (_) {}

  const findCardHandle = async () => {
    const handle = await frame.evaluateHandle((prefer) => {
      const parseCode = (txt) => {
        const t = String(txt || "");
        const m1 = t.match(/Baccarat\s+(C\d+)/i);
        if (m1) return m1[1].toUpperCase();
        const m2 = t.match(/BTCB(\d+)/i);
        if (m2) return `C${String(m2[1]).padStart(2, "0")}`;
        const m3 = t.match(/\b(C\d{1,3})\b/i);
        if (m3) return m3[1].toUpperCase();
        return null;
      };
      const norm = (c) => {
        if (!c) return "";
        const u = String(c).toUpperCase();
        const m = u.match(/C?0*(\d+)/);
        return m ? `C${m[1].padStart(2, "0")}` : u;
      };
      const wantCode = norm(prefer);
      const cards = Array.from(
        document.querySelectorAll(
          ".vue-recycle-scroller__item-view, .table-item, div.relative.cursor-pointer, [class*='card']"
        )
      );
      const matching = cards.filter(
        (card) =>
          norm(parseCode(card.innerText || card.textContent || "")) === wantCode
      );
      // Vue recycle item chỉ là wrapper; click wrapper trả OK nhưng không mở bàn.
      // Ưu tiên node tương tác sâu nhất mang đúng mã bàn.
      matching.sort((a, b) => {
        const depth = (el) => {
          let n = 0;
          for (let p = el; p && p !== document.body; p = p.parentElement) n += 1;
          return n;
        };
        return depth(a) - depth(b);
      });
      for (const card of matching) {
        const clickTarget =
          card.querySelector("div.relative.cursor-pointer") ||
          (card.matches(
            "div.relative.cursor-pointer, .table-item, button, a, [role='button'], [onclick]"
          )
            ? card
            : card.querySelector(
                "div.relative.cursor-pointer, .table-item, button, a, [role='button'], [onclick]"
              )) ||
          card;
        if (clickTarget) {
          try {
            clickTarget.scrollIntoView({ block: "center", inline: "center" });
          } catch (_) {}
          return clickTarget;
        }
      }
      return null;
    }, want);
    const el = handle && handle.asElement && handle.asElement();
    if (!el) {
      if (handle && handle.dispose) await handle.dispose().catch(() => {});
      return null;
    }
    return el;
  };

  const scrollLobby = async (delta) => {
    await frame
      .evaluate((d) => {
        const scroller =
          document.querySelector(".vue-recycle-scroller") ||
          document.querySelector("[class*='recycle']") ||
          document.scrollingElement;
        if (scroller) scroller.scrollTop = Math.max(0, (scroller.scrollTop || 0) + d);
      }, delta)
      .catch(() => {});
  };

  for (let i = 0; i < 10; i++) {
    const el = await findCardHandle();
    if (el) {
      try {
        const info = await el
          .evaluate((node) => ({
            tag: node.tagName,
            cls: String(node.className || "").slice(0, 120),
            text: String(node.innerText || node.textContent || "")
              .replace(/\s+/g, " ")
              .trim()
              .slice(0, 80),
          }))
          .catch(() => null);
        const box = await el.boundingBox().catch(() => null);
        const pg = typeof frame.page === "function" ? frame.page() : null;
        if (box && pg && box.width > 40 && box.height > 40) {
          const cx = box.x + box.width / 2;
          const cy = box.y + box.height / 2;
          await pg.mouse.move(cx, cy);
          await pg.mouse.click(cx, cy, { clickCount: doubleClick ? 2 : 1, delay: 120 });
          if (doubleClick) {
            await new Promise((r) => setTimeout(r, 200));
            await pg.mouse.click(cx, cy, { clickCount: 1 });
          }
          await el.dispose().catch(() => {});
          return {
            ok: true,
            table: want,
            via: doubleClick ? "mouse_dblclick" : "mouse_click",
            target: info,
          };
        }
        await el.click({ force: true, timeout: 2000, clickCount: doubleClick ? 2 : 1 });
        await el.dispose().catch(() => {});
        return { ok: true, table: want, via: doubleClick ? "pw_dblclick" : "pw_click", target: info };
      } catch (_) {
        try {
          await el.evaluate((node, dbl) => {
            const events = dbl
              ? ["pointerdown", "mousedown", "mouseup", "click", "dblclick"]
              : ["pointerdown", "mousedown", "mouseup", "click"];
            for (const type of events) {
              node.dispatchEvent(
                new MouseEvent(type, { bubbles: true, cancelable: true, view: window })
              );
            }
            if (node.click) node.click();
          }, doubleClick);
          await el.dispose().catch(() => {});
          return { ok: true, table: want, via: "el_click" };
        } catch (e2) {
          await el.dispose().catch(() => {});
        }
      }
    }
    await scrollLobby(i === 9 ? -9999 : 380);
    await new Promise((r) => setTimeout(r, 180));
  }

  return frame.evaluate(clickTableByCodeEval, {
    prefer: want,
    allowFallback,
    doubleClick,
  });
}

module.exports = {
  normTableCode,
  parseTableCode,
  listTablesInDocumentEval,
  clickTableByCodeEval,
  pickRandomUnique,
  listTablesFromFrame,
  clickTableByCode,
};
