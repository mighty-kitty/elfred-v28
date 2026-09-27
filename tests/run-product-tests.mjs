import { build } from "esbuild";
import { spawnSync } from "node:child_process";

await build({
  entryPoints: ["tests/product-flow.test.tsx", "tests/v277-flow.test.tsx", "tests/markdown-content.test.tsx"],
  bundle: true,
  platform: "node",
  format: "esm",
  packages: "external",
  outdir: ".sites-runtime/tests",
  jsx: "automatic",
});
const result=spawnSync(process.execPath,["--test",".sites-runtime/tests/product-flow.test.js",".sites-runtime/tests/v277-flow.test.js",".sites-runtime/tests/markdown-content.test.js"],{stdio:"inherit"});
process.exit(result.status ?? 1);
