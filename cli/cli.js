#!/usr/bin/env node
/**
 * @techysy/inspection-visualizer — 巡检数据可视化 CLI
 *
 * 用法:
 *   iv                  启动服务并进入托盘管理(默认)
 *   iv start [--proxy URL]  后台启动服务(detached)
 *   iv stop             停止服务
 *   iv restart          重启服务
 *   iv status           查看服务状态
 *   iv open             在浏览器打开巡检系统
 *   iv autostart on|off|status  开机自启(托盘方式)
 *   iv --help / --version
 *
 * 环境变量: IV_PORT(默认5001) IV_HOST IV_DATA_DIR IV_PYTHON_CMD
 */
const fs = require("fs");
const path = require("path");
const {
  PORT, BASE_URL, dataDir, detectPython, ensureRuntime,
  isHealthy, startServer, stopServer, getStatus, openBrowser,
} = require("./src/server");
const { initTray, killTray, updateItem, MENU_INDEX, isTraySupported } = require("./src/tray/tray");
const autostart = require("./src/tray/autostart");

const VERSION = require("./package.json").version;
const TRAY_PID_FILE = path.join(require("./src/server").HOME_DIR, "tray.pid");

function argValue(flag) {
  const i = process.argv.indexOf(flag);
  return i !== -1 ? process.argv[i + 1] : undefined;
}

function alivePid(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; } catch { return false; }
}

/** 托盘单实例:已在运行则直接打开浏览器退出 */
function trayAlreadyRunning() {
  let pid = 0;
  try { pid = parseInt(fs.readFileSync(TRAY_PID_FILE, "utf8").trim(), 10); } catch { }
  if (alivePid(pid)) {
    openBrowser();
    console.log(`[iv] 托盘已在运行 (PID ${pid}),已为你打开 ${BASE_URL}`);
    return true;
  }
  try { fs.mkdirSync(require("./src/server").HOME_DIR, { recursive: true }); } catch { }
  fs.writeFileSync(TRAY_PID_FILE, String(process.pid));
  return false;
}

async function trayMode() {
  if (trayAlreadyRunning()) return;
  console.log(`[iv] 巡检数据可视化 v${VERSION} — 启动中...`);

  let startedHere = false;
  const status = await getStatus();
  if (!status.healthy) {
    try {
      const r = await startServer({ proxy: argValue("--proxy") });
      startedHere = !r.already;
    } catch (e) {
      console.error(`[iv] ${e.message}`);
      if (!isTraySupported()) process.exit(1);
      // 托盘平台仍保持图标,便于用户打开数据目录排查
    }
  } else {
    console.log(`[iv] 服务已在运行: ${BASE_URL}`);
  }
  openBrowser();

  const tray = initTray({
    port: PORT,
    onOpen: () => openBrowser(),
    onRestart: async () => {
      await stopServer({ log: () => { } });
      await new Promise(r => setTimeout(r, 800));
      startServer({ proxy: argValue("--proxy") })
        .then(() => console.log(`[iv] 已重启 ${BASE_URL}`))
        .catch(e => console.error(`[iv] 重启失败: ${e.message}`));
    },
    onStop: async () => {
      const r = await stopServer();
      console.log(`[iv] ${r.stopped ? "服务已停止" : r.reason}`);
    },
    onQuit: async () => {
      await stopServer({ log: () => { } });
    },
  });
  if (!tray) {
    console.log("[iv] 当前环境不支持托盘,服务将在后台持续运行(iv stop 可停止)");
    keepForeground();
    return;
  }

  // 每 5 秒刷新托盘状态行
  setInterval(async () => {
    const ok = await isHealthy();
    updateItem(MENU_INDEX.STATUS,
      ok ? `巡检服务 · 运行中 :${PORT}` : "巡检服务 · 未运行", false);
  }, 5000);

  const cleanup = async () => {
    try { fs.unlinkSync(TRAY_PID_FILE); } catch { }
  };
  process.on("SIGINT", async () => { await cleanup(); process.exit(0); });
  process.on("exit", () => { try { fs.unlinkSync(TRAY_PID_FILE); } catch { } });
  console.log(`[iv] 托盘已就绪,浏览器访问 ${BASE_URL}(Ctrl+C 退出,不影响后台服务)`);
}

/** 无托盘环境下保持进程存活(仅轮询) */
function keepForeground() {
  setInterval(async () => {
    const ok = await isHealthy();
    console.log(`[iv] ${new Date().toLocaleTimeString()} ${ok ? "运行中" : "未响应"}`);
  }, 30000);
  process.on("SIGINT", () => process.exit(0));
}

function printHelp() {
  console.log(`
巡检数据可视化 CLI v${VERSION}

用法:
  iv                        启动服务并进入托盘管理(默认)
  iv start [--proxy URL]    后台启动服务(首次自动创建 Python 运行时)
  iv stop                   停止服务
  iv restart                重启服务
  iv status                 查看服务状态
  iv open                   浏览器打开巡检系统
  iv autostart on|off|status  开机自启管理
  iv --help                 本帮助

环境变量:
  IV_PORT=5001              服务端口
  IV_DATA_DIR=...           数据目录(默认 %APPDATA%\\InspectionVisualizer)
  IV_PYTHON_CMD="py -3.11"  指定 Python 命令

文档: https://github.com/techysy/inspection-visualizer`);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args.find(a => !a.startsWith("--"));

  if (args.includes("--version") || args.includes("-v")) {
    console.log(VERSION);
    return;
  }
  if (args.includes("--help") || args.includes("-h") || cmd === "help") {
    printHelp();
    return;
  }

  switch (cmd) {
    case undefined:
    case "tray":
      await trayMode();
      return;
    case "start": {
      try {
        const r = await startServer({ proxy: argValue("--proxy") });
        console.log(r.already
          ? `[iv] 服务已在运行: ${r.url}`
          : `[iv] 服务已启动: ${r.url} (PID ${r.pid})\n     日志: ${r.logFile}`);
      } catch (e) {
        console.error(`[iv] ${e.message}`);
        process.exit(1);
      }
      return;
    }
    case "stop": {
      const r = await stopServer();
      console.log(r.stopped ? `[iv] 服务已停止 (PID ${r.pid})` : `[iv] ${r.reason}`);
      return;
    }
    case "restart": {
      await stopServer();
      await new Promise(r => setTimeout(r, 800));
      try {
        const r = await startServer();
        console.log(`[iv] 已重启: ${r.url}`);
      } catch (e) {
        console.error(`[iv] ${e.message}`);
        process.exit(1);
      }
      return;
    }
    case "status": {
      const s = await getStatus();
      console.log(`[iv] 服务: ${s.healthy ? "运行中" : "未运行"}   地址: ${s.url}`);
      if (s.pid) console.log(`     PID: ${s.pid}`);
      console.log(`     数据目录: ${s.dataDir}`);
      console.log(`     Python 运行时: ${s.runtimeReady ? "就绪" : "未就绪(首次 start 时自动创建)"}`);
      const py = detectPython();
      if (!py && !s.runtimeReady) console.log("     ⚠ 未检测到系统 Python 3.8+");
      return;
    }
    case "open": {
      if (!(await isHealthy())) {
        console.log(`[iv] 服务未运行,先执行: iv start`);
        process.exit(1);
      }
      openBrowser();
      console.log(`[iv] 已在浏览器打开 ${BASE_URL}`);
      return;
    }
    case "autostart": {
      const sub = args[args.indexOf("autostart") + 1];
      if (sub === "on") {
        const ok = autostart.enableAutoStart();
        console.log(`[iv] 开机自启${ok ? "已开启" : "开启失败(当前平台可能不支持)"}`);
      } else if (sub === "off") {
        autostart.disableAutoStart();
        console.log("[iv] 开机自启已关闭");
      } else {
        console.log(`[iv] 开机自启: ${autostart.isAutoStartEnabled() ? "已开启" : "已关闭"}`);
      }
      return;
    }
    default:
      console.error(`[iv] 未知命令: ${cmd}(iv --help 查看用法)`);
      process.exit(1);
  }
}

main().catch((e) => {
  console.error(`[iv] ${e.message}`);
  process.exit(1);
});
