const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--no-sandbox"] });
  const p = await b.newPage();
  await p.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  const color = await p.evaluate(() => {
    const el = document.querySelector(".MuiAppBar-root");
    if (!el) return null;
    return window.getComputedStyle(el).backgroundColor;
  });
  console.log("AppBar background:", color);
  await b.close();
})();
