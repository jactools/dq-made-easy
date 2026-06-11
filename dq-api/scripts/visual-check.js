const { chromium } = require("playwright");
const fs = require("fs");

(async () => {
  const outDir = __dirname + "/output";
  try {
    fs.mkdirSync(outDir, { recursive: true });
  } catch (e) {}

  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage();

  page.on("console", (msg) => {
    console.log("[PAGE CONSOLE]", msg.type(), msg.text());
  });

  page.on("pageerror", (err) => {
    console.log("[PAGE ERROR]", err && err.stack ? err.stack : err);
  });

  page.on("requestfailed", (req) => {
    console.log(
      "[REQUEST FAILED]",
      req.url(),
      req.failure() && req.failure().errorText,
    );
  });

  try {
    console.log("[NAV] -> /");
    await page.goto("http://localhost:5173/", {
      waitUntil: "networkidle",
      timeout: 20000,
    });
    await page.waitForTimeout(500); // let MSW messages settle
    await page.screenshot({ path: outDir + "/home.png", fullPage: true });
    console.log("[SCREENSHOT] home ->", outDir + "/home.png");

    console.log("[NAV] -> /rules");
    await page.goto("http://localhost:5173/rules", {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page
      .waitForSelector("text=no-nulls, text=No nulls", { timeout: 5000 })
      .catch(() => {});
    await page.screenshot({ path: outDir + "/rules.png", fullPage: true });
    console.log("[SCREENSHOT] rules ->", outDir + "/rules.png");

    // capture attributes page
    try {
      console.log("[NAV] -> /attributes");
      await page.goto("http://localhost:5173/attributes", {
        waitUntil: "networkidle",
        timeout: 15000,
      });
      await page.waitForTimeout(500);
      await page.screenshot({
        path: outDir + "/attributes.png",
        fullPage: true,
      });
      console.log("[SCREENSHOT] attributes ->", outDir + "/attributes.png");
    } catch (e) {
      console.log(
        "[WARN] failed to capture /attributes",
        e && e.message ? e.message : e,
      );
    }

    // capture applied rules page
    try {
      console.log("[NAV] -> /applied");
      await page.goto("http://localhost:5173/applied", {
        waitUntil: "networkidle",
        timeout: 15000,
      });
      await page.waitForTimeout(500);
      await page.screenshot({ path: outDir + "/applied.png", fullPage: true });
      console.log("[SCREENSHOT] applied ->", outDir + "/applied.png");
    } catch (e) {
      console.log(
        "[WARN] failed to capture /applied",
        e && e.message ? e.message : e,
      );
    }

    // open first rule detail
    const firstLink = await page.$('a[href^="/rules/"]');
    if (firstLink) {
      await firstLink.click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
      await page.screenshot({
        path: outDir + "/rule-detail.png",
        fullPage: true,
      });
      console.log("[SCREENSHOT] rule-detail ->", outDir + "/rule-detail.png");
    }

    // perform login as admin via page fetch so MSW picks it up
    console.log("[ACTION] login as admin");
    await page.evaluate(async () => {
      await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "admin" }),
      });
    });
    await page.waitForTimeout(500);

    // open edit page for first rule
    const ruleId = await page.evaluate(() => {
      const a = document.querySelector('a[href^="/rules/"]');
      if (!a) return null;
      const href = a.getAttribute("href");
      const m = href.match(/\/rules\/(\d+)/);
      return m ? m[1] : null;
    });

    if (ruleId) {
      console.log("[NAV] -> /rules/" + ruleId + "/edit");
      await page.goto("http://localhost:5173/rules/" + ruleId + "/edit", {
        waitUntil: "networkidle",
      });
      await page.waitForSelector("form", { timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(300);
      await page.screenshot({
        path: outDir + "/rule-edit.png",
        fullPage: true,
      });
      console.log("[SCREENSHOT] rule-edit ->", outDir + "/rule-edit.png");
    } else {
      console.log("[WARN] could not determine ruleId for edit");
    }

    // open users page (admin only)
    console.log("[NAV] -> /users");
    await page.goto("http://localhost:5173/users", {
      waitUntil: "networkidle",
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: outDir + "/users.png", fullPage: true });
    console.log("[SCREENSHOT] users ->", outDir + "/users.png");

    console.log("[RESULT] screenshots saved to", outDir);
  } catch (e) {
    console.error("[ERROR]", e && e.stack ? e.stack : e);
  } finally {
    await browser.close();
  }
})();
