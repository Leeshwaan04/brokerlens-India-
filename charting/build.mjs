// Builds the charting engine to one static file and copies it, with the vendored
// renderer, into the paper app's public folder. The main site gets its copy when
// it migrates (see docs). `--check` builds to memory and fails if the output is
// over budget or the checked-in copy is stale.
import { build } from "esbuild";
import { gzipSync } from "node:zlib";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const check = process.argv.includes("--check");
const BUDGET_GZ = 30 * 1024; // the engine itself; the renderer (62 KB gz) is separate

const result = await build({
  entryPoints: [resolve(here, "src/index.ts")],
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "BrokerLensCharting",
  target: "es2020",
  legalComments: "none",
  write: false,
});
const code = result.outputFiles[0].text;
const gz = gzipSync(code).length;
console.log(`engine.js ${(code.length / 1024).toFixed(1)} KB raw, ${(gz / 1024).toFixed(1)} KB gzip (budget ${BUDGET_GZ / 1024} KB)`);
if (gz > BUDGET_GZ) {
  console.error("engine is over its size budget");
  process.exit(1);
}

const targets = [
  resolve(repo, "virtual-trading/public/charting/engine.js"),
  resolve(repo, "site/assets/js/charting/engine.js"),
];
if (check) {
  const stale = targets.filter((t) => !existsSync(t) || readFileSync(t, "utf8") !== code);
  if (stale.length) {
    console.error("stale build output (run: npm run build in charting/):\n" + stale.join("\n"));
    process.exit(1);
  }
  console.log("build output is current");
} else {
  for (const t of targets) {
    mkdirSync(dirname(t), { recursive: true });
    writeFileSync(t, code);
  }
  const lwcSrc = resolve(repo, "site/assets/js/vendor/lightweight-charts.standalone.production.js");
  const lwcDst = resolve(repo, "virtual-trading/public/charting/lightweight-charts.js");
  copyFileSync(lwcSrc, lwcDst);
  console.log("wrote", targets.join(", "), "and lightweight-charts.js");
}
