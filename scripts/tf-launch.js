#!/usr/bin/env node
// Cross-platform launcher for tf.py. Claude Code runs hook commands through cmd.exe on Windows
// and sh elsewhere, so hooks call `node tf-launch.js <cmd>` and this finds a Python 3.
// Order: $TF_PYTHON, python3, python, py -3. The Windows Store "python3" stub is rejected by the probe.
// Never blocks the user: any failure exits 0 with no output.
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const tfPy = path.join(__dirname, "tf.py");
const cacheFile = path.join(os.tmpdir(), "tokenforward-python.json");

function probe(cand) {
  const r = spawnSync(cand[0], [...cand.slice(1), "-c", "import sys;print(sys.version_info[0])"],
    { encoding: "utf8", timeout: 5000, windowsHide: true });
  return r.status === 0 && (r.stdout || "").trim() === "3";
}

function findPython() {
  if (process.env.TF_PYTHON) return [process.env.TF_PYTHON];
  try {
    const c = JSON.parse(fs.readFileSync(cacheFile, "utf8"));
    if (Array.isArray(c) && probe(c)) return c;
  } catch (_) {}
  for (const cand of [["python3"], ["python"], ["py", "-3"]]) {
    if (probe(cand)) {
      try { fs.writeFileSync(cacheFile, JSON.stringify(cand)); } catch (_) {}
      return cand;
    }
  }
  return null;
}

let input = "";
const isHook = (process.argv[2] || "").startsWith("hook-") || process.argv[2] === "statusline";
if (isHook || process.argv.includes("-")) {
  try { input = fs.readFileSync(0, "utf8"); } catch (_) {}
}
const py = findPython();
if (!py) {
  process.stderr.write("tokenforward: no Python 3 found (set TF_PYTHON)\n");
  process.exit(0);
}
const r = spawnSync(py[0], [...py.slice(1), tfPy, ...process.argv.slice(2)],
  { input, encoding: "utf8", timeout: process.argv[2] && process.argv[2].startsWith("hook-") ? 9000 : 300000, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
if (r.stdout) process.stdout.write(r.stdout);
if (r.stderr) process.stderr.write(r.stderr);
process.exit(0);
