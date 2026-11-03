#!/usr/bin/env node
// The scorecard starts every build's harness with Node. This build's harness is eval.py, so this file
// hands its arguments to Python 3.12 through uv, which keeps the environment outside the build folder.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const args = ["run", "-q", "--no-project", "--python", "3.12", "--with-requirements", "requirements.txt",
  "python", "eval.py", ...process.argv.slice(2)];
const run = spawnSync("uv", args, { cwd: root, stdio: "inherit" });
if (run.error) console.error(`could not start uv: ${run.error.message}`);
process.exit(run.status ?? 1);
