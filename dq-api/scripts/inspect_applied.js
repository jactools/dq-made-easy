const { chromium } = require("playwright");

(async () => {
  const url = process.env.UI_NGINX_LOCAL_URL || process.env.UI_VITE_LOCAL_URL || "http://localhost:5173";
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on("console", (m) => {
    try {
      console.log("PAGE:", m.type(), m.text());
    } catch (e) {}
  });
  await page.goto(url, { timeout: 30000 });
  await page.click('a[href="/applied"]');
  await page.waitForSelector('text="Applied Rules"');
  try {
    await page.waitForSelector("table tbody tr", { timeout: 3000 });
  } catch (e) {
    console.log("No table rows found");
  }
  const rows = await page.$$("table tbody tr");
  for (let i = 0; i < rows.length; i++) {
    const cells = await rows[i].$$("td");
    const rule = (await cells[1].innerText()).trim();
    const status = (await cells[2].innerText()).trim();
    console.log(i, rule, "->", JSON.stringify(status));
  }
  await browser.close();
  process.exit(0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
