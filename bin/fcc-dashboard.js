#!/usr/bin/env node
/**
 * Global CLI entry point for fcc-dashboard. Install once with either
 * `npm link` or `npm install -g .` (run from the repo root), then
 * `fcc-dashboard` starts the single-process production server from any
 * working directory — it locates its own file on disk to find the repo
 * root and runs `uv run fcc-dashboard-server` from `backend/` there, so
 * it resolves the same DB/pricing/log paths and serves the same
 * `frontend/dist` build it would if run directly inside the repo.
 *
 * This does not build the frontend or sync backend dependencies for you
 * — run `uv sync` (in backend/) and `npm install && npm run build` (in
 * frontend/) at least once first, same as the manual quick start. This
 * command is purely a shortcut for the final "start the server" step.
 *
 * Usage: fcc-dashboard
 * Uninstall: npm uninstall -g fcc-dashboard
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const backendDir = join(repoRoot, "backend");

// shell: true is required on Windows, where uv itself is invoked via a
// shim — child_process.spawn can't exec it directly without going
// through a shell, same reasoning as sift's bin/sift-server.js.
const child = spawn("uv", ["run", "fcc-dashboard-server"], {
  cwd: backendDir,
  stdio: "inherit",
  shell: true,
});

child.on("exit", (code) => process.exit(code ?? 0));
