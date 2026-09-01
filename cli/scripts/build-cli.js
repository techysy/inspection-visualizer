#!/usr/bin/env node

/**
 * build-cli:把仓库根目录的 Python 应用源码汇集到 cli/app/,随 npm 包发布。
 * 用法: npm run build (在 cli/ 目录)
 */
const fs = require("fs");
const path = require("path");

const pkgRoot = path.join(__dirname, "..");
const repoRoot = path.resolve(pkgRoot, "..");
const appDir = path.join(pkgRoot, "app");

const FILES = [
  "app.py", "app_factory.py", "app_routes.py", "config.py", "ocr.py", "run_server.py",
  "dashboard_types.json", "global_vars.json", "ocr_config.json", "requirements.txt",
  "README.md", "LICENSE",
];
const DIRS = ["models", "static", "templates"];
const SKIP = new Set(["__pycache__", ".pyc"]);

function copyFile(src, dest) {
  fs.copyFileSync(src, dest);
}

function copyTree(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    if (SKIP.has(name) || name.endsWith(".pyc")) continue;
    const s = path.join(src, name);
    const d = path.join(dest, name);
    if (fs.statSync(s).isDirectory()) copyTree(s, d);
    else copyFile(s, d);
  }
}

console.log(`[build-cli] 清理 ${appDir}`);
fs.rmSync(appDir, { recursive: true, force: true });
fs.mkdirSync(appDir, { recursive: true });

for (const f of FILES) {
  const src = path.join(repoRoot, f);
  if (!fs.existsSync(src)) {
    console.warn(`[build-cli] 跳过不存在的文件: ${f}`);
    continue;
  }
  copyFile(src, path.join(appDir, f));
}
for (const d of DIRS) {
  const src = path.join(repoRoot, d);
  if (!fs.existsSync(src)) {
    console.warn(`[build-cli] 跳过不存在的目录: ${d}`);
    continue;
  }
  copyTree(src, path.join(appDir, d));
}

const count = (function walk(p) {
  let n = 0;
  for (const name of fs.readdirSync(p)) {
    const full = path.join(p, name);
    if (fs.statSync(full).isDirectory()) n += walk(full);
    else n += 1;
  }
  return n;
})(appDir);

console.log(`[build-cli] 应用源码就绪: ${appDir} (${count} 个文件)`);
