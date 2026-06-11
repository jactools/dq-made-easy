const { chromium } = require("playwright");

(async () => {
  const url = process.env.UI_NGINX_LOCAL_URL || process.env.UI_VITE_LOCAL_URL || "http://localhost:5173";
  const out = process.env.OUT || "logs/ui_applied.png";
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  console.log("Opening", url);
  await page.goto(url, { timeout: 30000 });
  try {
    await page.waitForSelector('text="Total Rules"', { timeout: 5000 });
  } catch (e) {
    // continue
  }
  const link = await page.$('a[href="/applied"]');
  if (!link) {
    console.error("ERROR: link to /applied not found on Home page");
    await browser.close();
    process.exit(2);
  }
  console.log("Found /applied link; clicking...");
  await Promise.all([page.waitForNavigation({ timeout: 10000 }), link.click()]);
  console.log("Current URL:", page.url());
  const h = await page.$('text="Applied Rules"');
  if (!h) {
    console.error("ERROR: Applied Rules header not found after navigation");
    await page
      .screenshot({ path: out.replace(".png", ".fail.png"), fullPage: true })
      .catch(() => {});
    await browser.close();
    process.exit(3);
  }
  await page.screenshot({ path: out, fullPage: true });
  console.log("Screenshot saved to", out);
  await browser.close();
  process.exit(0);
})();
