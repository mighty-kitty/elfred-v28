// Cross-platform replacement for the original bash wrappers (sites-env.sh,
// build-verified.sh, install-ci.sh, validate-artifact.sh). Those required
// bash, GNU `timeout` and `flock`, so `npm run build`/`lint` could not run on
// Windows at all. This keeps the same behaviour without the shell dependency.
//
//   node scripts/run-project.mjs dev   [--port 5190]
//   node scripts/run-project.mjs build
//   node scripts/run-project.mjs start
//   node scripts/run-project.mjs lint
//   node scripts/run-project.mjs typecheck
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import "./patch-vinext-windows.mjs";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const command = process.argv[2];
const forwardedArgs = process.argv.slice(3);

// Keep Wrangler/Miniflare state inside the project, matching the old
// sites-env.sh isolation, but under a Windows-friendly directory.
const runtimeRoot = process.env.SITES_RUNTIME_ROOT ?? path.join(projectRoot, ".sites-runtime");
const wranglerDirectory = path.join(projectRoot, ".wrangler");
await mkdir(path.join(runtimeRoot, "tmp"), { recursive: true });
await mkdir(path.join(runtimeRoot, "npm-cache"), { recursive: true });
await mkdir(wranglerDirectory, { recursive: true });

const environment = {
  ...process.env,
  WRANGLER_WRITE_LOGS: "false",
  WRANGLER_LOG_PATH: path.join(wranglerDirectory, "wrangler.log"),
  MINIFLARE_REGISTRY_PATH: path.join(wranglerDirectory, "registry"),
  npm_config_audit: "false",
  npm_config_fund: "false",
};

function run(entry, args = [], nodeArgs = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [...nodeArgs, path.join(projectRoot, entry), ...args], {
      cwd: projectRoot,
      env: environment,
      stdio: "inherit",
    });
    child.once("error", reject);
    child.once("exit", (code, signal) =>
      signal ? reject(new Error(`Command terminated by ${signal}`)) : resolve(code ?? 1),
    );
  });
}

let exitCode;
switch (command) {
  case "dev":
    // 本地有 .env.local 时走应用自己的入口：它会把 /api/elfred 也挂上。
    // 直接跑 vinext dev 只起界面，接口是 404，页面会退回演示数据（第二页/第四页踩过）。
    exitCode = existsSync(path.join(projectRoot, ".env.local"))
      ? await run("scripts/start-local.mjs", forwardedArgs, ["--env-file-if-exists=.env.local"])
      : await run("node_modules/vinext/dist/cli.js", ["dev", ...forwardedArgs]);
    break;
  case "build":
    exitCode = await run("node_modules/vinext/dist/cli.js", ["build", ...forwardedArgs]);
    break;
  case "start":
    exitCode = await run("node_modules/vinext/dist/cli.js", ["start", ...forwardedArgs]);
    break;
  case "lint":
    exitCode = await run("node_modules/eslint/bin/eslint.js", [
      ".",
      "--ignore-pattern",
      "dist",
      "--ignore-pattern",
      ".next",
      "--ignore-pattern",
      ".sites-runtime",
      "--ignore-pattern",
      ".vinext",
      ...forwardedArgs,
    ]);
    break;
  case "typecheck":
    exitCode = await run("node_modules/typescript/bin/tsc", [
      "--noEmit",
      ...forwardedArgs,
    ]);
    break;
  case "db:generate":
    exitCode = await run("node_modules/drizzle-kit/bin.cjs", ["generate", ...forwardedArgs]);
    break;
  default:
    throw new Error(`Unknown project command: ${command ?? "<missing>"}`);
}
process.exitCode = exitCode;
