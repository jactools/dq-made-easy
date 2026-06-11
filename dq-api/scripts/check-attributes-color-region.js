const fs = require("fs");
const { PNG } = require("pngjs");
const path = __dirname + "/output/attributes.png";
if (!fs.existsSync(path)) {
  console.error("attributes.png not found");
  process.exit(2);
}
fs.createReadStream(path)
  .pipe(new PNG())
  .on("parsed", function () {
    const w = this.width;
    const h = this.height;
    const y0 = Math.max(0, Math.floor(h * 0.12)); // approx 12% down
    const y1 = Math.min(h, Math.floor(h * 0.28)); // approx 28% down
    let blue = 0,
      grey = 0,
      t = 0;
    for (let y = y0; y < y1; y++) {
      for (let x = 0; x < w; x++) {
        const idx = (w * y + x) << 2;
        const r = this.data[idx],
          g = this.data[idx + 1],
          b = this.data[idx + 2],
          a = this.data[idx + 3];
        if (a < 200) continue;
        t++;
        const max = Math.max(r, g, b),
          min = Math.min(r, g, b);
        if (max - min < 16 && max > 180) {
          grey++;
          continue;
        }
        if (b > 120 && b > r + 30 && b > g + 30) {
          blue++;
          continue;
        }
      }
    }
    console.log("region y0..y1:", y0, y1, "pixels:", t);
    console.log(
      "blue:",
      blue,
      "grey:",
      grey,
      "blue%",
      ((blue / t) * 100).toFixed(3),
      "grey%",
      ((grey / t) * 100).toFixed(3),
    );
    if (blue / (t || 1) > 0.01)
      console.log("VERDICT: blue pixels present in region");
    else console.log("VERDICT: little blue in region — likely greyed");
  });
