const { chromium } = require("playwright");

(async () => {
  const url = process.env.UI_NGINX_LOCAL_URL || process.env.UI_VITE_LOCAL_URL || "http://localhost:5173";
  const out = process.env.OUT || "logs/ui_settings.png";
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  console.log("Opening", url);
  await page.goto(url, { timeout: 30000 });
  try {
    // wait briefly for UI to render
    await page.waitForSelector("text=Preferences", { timeout: 8000 });
  } catch (e) {
    console.error("Preferences not found in left menu");
  }

  const pref = await page.$("text=Preferences");
  const settings = await page.$("text=Settings");

  if (!pref) {
    console.error("ERROR: Preferences link not visible");
    await page
      .screenshot({
        path: out.replace(".png", ".prefs.fail.png"),
        fullPage: true,
      })
      .catch(() => {});
    await browser.close();
    process.exit(2);
  }
  if (!settings) {
    console.error("ERROR: Settings not visible");
    await page
      .screenshot({
        path: out.replace(".png", ".settings.fail.png"),
        fullPage: true,
      })
      .catch(() => {});
    await browser.close();
    process.exit(3);
  }

  console.log("Found Preferences and Settings; saving screenshot to", out);
  await page.screenshot({ path: out, fullPage: true });
  await browser.close();
  process.exit(0);
})();
