const fs = require("fs");
const { PNG } = require("pngjs");

const path = __dirname + "/output/attributes.png";
if (!fs.existsSync(path)) {
  console.error("attributes.png not found at", path);
  process.exit(2);
}

fs.createReadStream(path)
  .pipe(new PNG())
  .on("parsed", function () {
    const w = this.width;
    const h = this.height;
    let blueCount = 0;
    let greyCount = 0;
    let total = 0;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = (w * y + x) << 2;
        const r = this.data[idx];
        const g = this.data[idx + 1];
        const b = this.data[idx + 2];
        const a = this.data[idx + 3];
        if (a < 200) continue; // ignore transparent
        total++;
        // grey-ish: r,g,b close to each other and relatively light
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        if (max - min < 16 && max > 180) {
          greyCount++;
          continue;
        }
        // blue-ish: blue significantly higher than red/green
        if (b > 120 && b > r + 30 && b > g + 30) {
          blueCount++;
          continue;
        }
      }
    }
    const blueRatio = blueCount / total;
    const greyRatio = greyCount / total;
    console.log("image size:", w, "x", h);
    console.log("pixels analyzed:", total);
    console.log(
      "blue pixels:",
      blueCount,
      "(",
      (blueRatio * 100).toFixed(3),
      "% )",
    );
    console.log(
      "light-grey pixels:",
      greyCount,
      "(",
      (greyRatio * 100).toFixed(3),
      "% )",
    );
    if (blueRatio > 0.005) {
      console.log("VERDICT: Button likely blue (not greyed-out)");
      process.exit(0);
    } else if (greyRatio > 0.002) {
      console.log(
        "VERDICT: Button likely greyed-out or page contains light greys",
      );
      process.exit(0);
    } else {
      console.log("VERDICT: Could not determine — low blue/grey presence");
      process.exit(0);
    }
  });
