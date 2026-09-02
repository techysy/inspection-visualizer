/**
 * Inspection Visualizer 桌面托盘版 (Electron)
 *
 * 职责:
 *  - 以子进程方式拉起/停止/重启 Python(Flask) 服务
 *  - 轮询 /api/health 判断服务就绪
 *  - 托盘图标 + 菜单(打开界面 / 启动 / 停止 / 重启 / 开机自启 / 退出)
 *  - 内嵌 BrowserWindow 展示 Web 界面,外链一律走系统默认浏览器
 *
 * 环境约定:
 *  - 打包版: resources/python/pythonw.exe + resources/app/(Python 源码)
 *  - 开发版: 仓库 venv 的 pythonw.exe(可用 IV_PYTHON 覆盖)
 *  - Python 数据目录由 IV_DATA_DIR 注入 app.getPath('userData')
 */
const { app, BrowserWindow, Tray, Menu, nativeImage, shell, dialog } = require('electron');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.env.IV_PORT || '5001', 10);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const IS_PACKAGED = app.isPackaged;
const ROOT = path.join(__dirname, '..');                     // 开发模式下的仓库根目录
const RESOURCES = IS_PACKAGED ? process.resourcesPath : path.join(__dirname, 'build');
const APP_DIR = IS_PACKAGED ? path.join(RESOURCES, 'app') : ROOT;
const DATA_DIR = app.getPath('userData');
const LOG_DIR = path.join(DATA_DIR, 'logs');
const PASSWORD_FILE = path.join(DATA_DIR, 'initial_password.txt');
const MAX_LOG_SIZE = 5 * 1024 * 1024;

app.setName('inspection-visualizer');

// ──────────────────────── 全局状态 ────────────────────────
/** @type {import('child_process').ChildProcess | null} */
let pyProc = null;
let state = 'stopped';          // stopped | starting | running | external
let quitting = false;
let tray = null;
let win = null;
let serverLogFd = null;

function log(msg) {
    const line = `[${new Date().toLocaleString('sv-SE')}] ${msg}\n`;
    try {
        fs.mkdirSync(LOG_DIR, { recursive: true });
        fs.appendFileSync(path.join(LOG_DIR, 'tray.log'), line);
    } catch { /* 日志失败不影响主流程 */ }
}

function resolvePython() {
    if (process.env.IV_PYTHON) return process.env.IV_PYTHON;
    if (IS_PACKAGED) {
        const pyw = path.join(RESOURCES, 'python', 'pythonw.exe');
        if (fs.existsSync(pyw)) return pyw;
        return path.join(RESOURCES, 'python', 'python.exe');
    }
    const venvPyw = path.join(ROOT, 'venv', 'Scripts', 'pythonw.exe');
    if (fs.existsSync(venvPyw)) return venvPyw;
    const venvPy = path.join(ROOT, 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPy)) return venvPy;
    return 'python';
}

// ──────────────────────── 健康检查 ────────────────────────
function checkHealth(timeoutMs = 2000) {
    return new Promise((resolve) => {
        const req = http.get({ host: '127.0.0.1', port: PORT, path: '/api/health', timeout: timeoutMs }, (res) => {
            res.resume();
            resolve(res.statusCode === 200);
        });
        req.on('error', () => resolve(false));
        req.on('timeout', () => { req.destroy(); resolve(false); });
    });
}

async function waitForHealth(deadlineMs) {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
        if (!pyProc && state !== 'external') return false;   // 进程已退出,停止等待
        if (await checkHealth()) return true;
        await new Promise(r => setTimeout(r, 1200));
    }
    return false;
}

// ──────────────────────── 服务管理 ────────────────────────
function openServerLogFd() {
    try {
        fs.mkdirSync(LOG_DIR, { recursive: true });
        const logFile = path.join(LOG_DIR, 'server.log');
        try {
            if (fs.statSync(logFile).size > MAX_LOG_SIZE) fs.truncateSync(logFile, 0);
        } catch { /* 文件不存在 */ }
        serverLogFd = fs.openSync(logFile, 'a');
    } catch {
        serverLogFd = null;
    }
}

function setState(next) {
    state = next;
    rebuildMenu();
}

async function startServer() {
    if (pyProc || state === 'running' || state === 'starting') return;

    // 端口已被占用且健康 → 视为外部已有服务在跑(比如手动 start.bat 启动的),直接打开界面
    if (await checkHealth()) {
        setState('external');
        notify('端口已被占用', `${PORT} 端口已有巡检服务在运行(可能由脚本启动),将直接打开界面`);
        createWindow();
        return;
    }

    const pythonExe = resolvePython();
    if (pythonExe !== 'python' && !fs.existsSync(pythonExe)) {
        dialog.showErrorBox('未找到 Python 运行环境', `未找到 ${pythonExe}\n请先运行 desktop\\build-python-runtime.ps1 或以开发模式运行。`);
        return;
    }

    openServerLogFd();
    const env = {
        ...process.env,
        IV_ELECTRON: '1',
        IV_HOST: '0.0.0.0',
        IV_PORT: String(PORT),
        IV_DATA_DIR: DATA_DIR,
        PYTHONUNBUFFERED: '1',
    };
    log(`start server: ${pythonExe} app.py (data=${DATA_DIR})`);
    const proc = spawn(pythonExe, ['app.py'], {
        cwd: APP_DIR,
        env,
        windowsHide: true,
        stdio: ['ignore', serverLogFd, serverLogFd],
    });
    pyProc = proc;
    setState('starting');

    proc.on('error', (err) => {
        log(`python spawn error: ${err.message}`);
        dialog.showErrorBox('启动失败', `Python 进程启动失败:\n${err.message}`);
    });
    proc.on('exit', (code) => {
        log(`python exited (code=${code})`);
        const wasRunning = state === 'running';
        if (serverLogFd !== null) { try { fs.closeSync(serverLogFd); } catch { } serverLogFd = null; }
        pyProc = null;
        if (!quitting) {
            setState('stopped');
            if (wasRunning) notify('服务已停止', 'Python 服务意外退出,可从托盘菜单重新启动');
        }
    });

    const ok = await waitForHealth(90 * 1000);
    if (!pyProc) return;                    // 启动过程中进程退出了
    if (ok) {
        setState('running');
        notify('巡检服务已启动', `${BASE_URL}\n局域网内其他设备可通过 http://<本机IP>:${PORT} 访问`);
        maybeNotifyPassword();
        if (!win || win.isDestroyed()) createWindow();      // 启动成功直接打开界面
        else win.loadURL(BASE_URL).catch(() => { });
    } else {
        setState('stopped');
        if (pyProc) { try { killProcTree(pyProc.pid); } catch { } }
        notify('启动超时', `服务在 90 秒内未就绪,日志见 ${path.join(LOG_DIR, 'server.log')}`);
    }
}

function killProcTree(pid) {
    // Flask/waitress 可能有子进程,用 taskkill 杀整棵树;被拒绝(权限)时 WMI 兜底
    const r = spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true });
    if (r.error) throw r.error;
    if (r.status !== 0) {
        spawnSync('wmic', ['process', 'where', `processid=${pid}`, 'delete'], { windowsHide: true });
    }
}

function stopServer() {
    return new Promise((resolve) => {
        if (!pyProc) return resolve();
        const proc = pyProc;
        log(`stop server pid=${proc.pid}`);
        try { killProcTree(proc.pid); } catch (e) { log(`taskkill failed: ${e.message}`); try { proc.kill(); } catch { } }
        const t = setTimeout(() => resolve(), 5000);
        proc.once('exit', () => { clearTimeout(t); resolve(); });
    });
}

async function restartServer() {
    notify('正在重启服务', '请稍候…');
    await stopServer();
    await new Promise(r => setTimeout(r, 800));
    await startServer();
}

// ──────────────────────── 窗口 ────────────────────────
function createWindow() {
    if (win && !win.isDestroyed()) {
        win.show();
        win.focus();
        return;
    }
    win = new BrowserWindow({
        width: 1380,
        height: 880,
        title: '巡检数据可视化',
        autoHideMenuBar: true,
        icon: path.join(__dirname, 'icon.ico'),
        backgroundColor: '#f5f7fa',
        show: false,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    win.once('ready-to-show', () => win.show());
    win.webContents.setWindowOpenHandler(({ url }) => {
        if (/^https?:/i.test(url)) shell.openExternal(url);   // 项目网址跳转等外链走系统浏览器
        return { action: 'deny' };
    });
    win.webContents.on('will-navigate', (e, url) => {
        if (!url.startsWith(BASE_URL)) {
            e.preventDefault();
            if (/^https?:/i.test(url)) shell.openExternal(url);
        }
    });
    win.on('close', (e) => {
        if (!quitting) {          // 点关闭 = 最小化到托盘
            e.preventDefault();
            win.hide();
        }
    });
    win.loadURL(BASE_URL).catch(() => {
        win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
            `<body style="font-family:sans-serif;padding:40px"><h3>服务未就绪</h3><p>请从托盘图标菜单「启动服务」后重试。</p></body>`));
    });
}

// ──────────────────────── 托盘 ────────────────────────
function notify(title, content) {
    if (!tray) return;
    try {
        tray.displayBalloon({ iconType: 'info', title, content });
    } catch { /* 部分环境不支持气泡 */ }
    log(`notify: ${title}`);
}

function maybeNotifyPassword() {
    // 未在 .env 设置 APP_PASSWORD 时,Python 每次启动都会生成新密码并写入该文件
    try {
        if (fs.existsSync(PASSWORD_FILE)) {
            notify('默认登录密码已生成',
                `本次启动密码见:${PASSWORD_FILE}\n建议在数据目录 .env 中设置 APP_PASSWORD 固定密码`);
        }
    } catch { }
}

const STATE_LABEL = {
    stopped: '服务未运行',
    starting: '服务启动中…',
    running: '服务运行中',
    external: '外部服务运行中(端口占用)',
};

function rebuildMenu() {
    if (!tray) return;
    const canOpen = state === 'running' || state === 'external';
    const hasPwFile = fs.existsSync(PASSWORD_FILE);
    const menu = Menu.buildFromTemplate([
        { label: '打开巡检系统', enabled: canOpen, click: createWindow },
        { type: 'separator' },
        { label: STATE_LABEL[state], enabled: false },
        { label: '启动服务', enabled: state === 'stopped', click: () => startServer() },
        { label: '重启服务', enabled: state === 'running', click: () => restartServer() },
        { label: '停止服务', enabled: state === 'running' || state === 'starting', click: () => stopServer() },
        { type: 'separator' },
        {
            label: '开机自启',
            type: 'checkbox',
            checked: app.getLoginItemSettings().openAtLogin,
            enabled: IS_PACKAGED,          // 开发模式注册的是 electron.exe,不提供
            click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked, path: app.getPath('exe') }),
        },
        { type: 'separator' },
        { label: '打开数据目录', click: () => shell.openPath(DATA_DIR) },
        { label: '打开服务日志', click: () => shell.openPath(path.join(LOG_DIR, 'server.log')) },
        { label: '查看默认密码', enabled: hasPwFile, click: () => shell.openPath(PASSWORD_FILE) },
        { type: 'separator' },
        {
            label: '退出',
            click: () => { quitting = true; app.quit(); },
        },
    ]);
    tray.setContextMenu(menu);
    tray.setToolTip(`巡检数据可视化 — ${STATE_LABEL[state]}`);
}

function createTray() {
    let icon = nativeImage.createFromPath(path.join(__dirname, 'icon.ico'));
    if (icon.isEmpty()) icon = nativeImage.createFromPath(path.join(__dirname, 'icon.png'));
    tray = new Tray(icon);
    rebuildMenu();
    tray.on('click', () => {
        if (state === 'running' || state === 'external') createWindow();
        else if (state === 'stopped') startServer();
    });
}

// ──────────────────────── 生命周期 ────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (state === 'running' || state === 'external') createWindow();
    });

    app.whenReady().then(async () => {
        log(`app start (packaged=${IS_PACKAGED}, data=${DATA_DIR})`);
        createTray();
        await startServer();          // 启动即拉起服务
    });

    app.on('before-quit', () => { quitting = true; });

    app.on('will-quit', () => {
        if (pyProc) {
            try { killProcTree(pyProc.pid); } catch { try { pyProc.kill(); } catch { } }
        }
    });

    // 托盘应用:窗口全关也不退出
    app.on('window-all-closed', (e) => { /* no-op,阻止默认退出 */ });
}
