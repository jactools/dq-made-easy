const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--no-sandbox"] });
  const p = await b.newPage();
  await p.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  const found = await p.evaluate(() => {
    const hrefs = Array.from(
      document.querySelectorAll('link[rel="stylesheet"]'),
    ).map((l) => l.href);
    const hasLocal = hrefs.some((h) => h.includes("/src/themes.css"));
    const rulesCount = Array.from(document.styleSheets)
      .filter((s) => s.href && s.href.includes("/src/themes.css"))
      .map((s) => (s.cssRules ? s.cssRules.length : 0));
    return { hrefs, hasLocal, rulesCount };
  });
  console.log(JSON.stringify(found, null, 2));
  await b.close();
})();
