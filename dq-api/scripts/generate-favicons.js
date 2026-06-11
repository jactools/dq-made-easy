#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");
let pngToIco = require("png-to-ico");
if (pngToIco && pngToIco.default) pngToIco = pngToIco.default;

const root = path.resolve(__dirname, "..");
const publicDir = path.join(root, "public");
const svgPath = path.join(publicDir, "logo-creative.svg");

if (!fs.existsSync(svgPath)) {
  console.error("SVG not found:", svgPath);
  process.exit(1);
}

async function generate() {
  const sizes = [16, 32, 48, 180];
  const pngPaths = [];
  for (const s of sizes) {
    const out = path.join(publicDir, `favicon-${s}.png`);
    await sharp(svgPath).resize(s, s, { fit: "contain" }).png().toFile(out);
    pngPaths.push(out);
    console.log("Wrote", out);
  }

  // create favicon.ico from 16,32,48
  const icoPath = path.join(publicDir, "favicon.ico");
  const icoBuf = await pngToIco([
    path.join(publicDir, "favicon-16.png"),
    path.join(publicDir, "favicon-32.png"),
    path.join(publicDir, "favicon-48.png"),
  ]);
  fs.writeFileSync(icoPath, icoBuf);
  console.log("Wrote", icoPath);

  // also copy 180 -> apple-touch-icon.png
  fs.copyFileSync(
    path.join(publicDir, "favicon-180.png"),
    path.join(publicDir, "apple-touch-icon.png"),
  );
  console.log("Wrote", path.join(publicDir, "apple-touch-icon.png"));
}

generate().catch((err) => {
  console.error(err);
  process.exit(1);
});
