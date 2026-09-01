#!/usr/bin/env node

// postinstall:只做轻量检查与提示,绝不阻塞安装(见 package.json comment_postinstall)。
// 真正的 Python 运行时供给在首次 `iv start` 时进行,失败可随时重试。
const { detectPython, HOME_DIR } = require("../src/server");
const fs = require("fs");
const path = require("path");

try {
  const py = detectPython();
  if (py) {
    console.log(`[inspection-visualizer] 检测到 Python ${py.version},首次 iv start 时将自动创建运行时`);
  } else {
    console.warn("[inspection-visualizer] 未检测到 Python 3.8+,首次 iv start 前请先安装 Python(https://www.python.org/downloads/)");
  }

  // macOS/Linux:惰性安装托盘依赖 systray2(Windows 用 PowerShell 托盘,无需)
  if (process.platform !== "win32" && process.platform !== "linux") {
    // no-op for非 darwin 分支说明:linux 有 DISPLAY 时同样需要,统一处理
  }
  if (process.platform === "darwin" || (process.platform === "linux" && process.env.DISPLAY)) {
    const nmDir = path.join(HOME_DIR, "runtime", "node_modules");
    fs.mkdirSync(nmDir, { recursive: true });
    const { spawnSync } = require("child_process");
    const r = spawnSync("npm", ["install", "--prefix", nmDir, "systray2", "--no-audit", "--no-fund", "--loglevel", "error"], {
      stdio: "ignore", timeout: 120000
    });
    console.log(r.status === 0
      ? "[inspection-visualizer] 托盘依赖 systray2 就绪"
      : "[inspection-visualizer] systray2 暂未安装(不影响服务,仅影响 mac/Linux 托盘图标)");
  }
} catch (e) {
  console.warn(`[inspection-visualizer] postinstall 跳过: ${e.message}`);
}

process.exit(0);
