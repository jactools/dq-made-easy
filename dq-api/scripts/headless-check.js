const { chromium } = require("playwright");

(async () => {
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
    const resp = await page.goto("http://localhost:5173/", {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    console.log("[NAV]", resp && resp.status());
    const content = await page.content();
    console.log("[SNAPSHOT START]");
    console.log(content.slice(0, 16000));
    try {
      await page.waitForSelector("text=no-nulls", { timeout: 3000 });
      console.log("[CHECK] Found rule text: no-nulls");
    } catch (e) {
      console.log("[CHECK] no-nulls not found in rendered page");
    }
    console.log("[SNAPSHOT END]");
  } catch (e) {
    console.log("[ERROR]", e && e.stack ? e.stack : e);
  } finally {
    await browser.close();
  }
})();
