/**
 * 服务端管理:Python 探测、运行时供给(venv + pip)、服务启停与健康检查
 *
 * 目录布局:
 *   ~/.inspection-visualizer/runtime/venv   Python 虚拟环境
 *   ~/.inspection-visualizer/runtime/node_modules  macOS/Linux 托盘依赖(systray2)
 *   数据目录:win → %APPDATA%\InspectionVisualizer(与桌面版一致);其他 → ~/.inspection-visualizer/data
 */
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const PORT = parseInt(process.env.IV_PORT || '5001', 10);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const HOME_DIR = path.join(os.homedir(), '.inspection-visualizer');
const RUNTIME_DIR = path.join(HOME_DIR, 'runtime');
const VENV_DIR = path.join(RUNTIME_DIR, 'venv');

// 包内打包的 Python 应用源码(npm files 包含 app/)
const APP_DIR = path.join(__dirname, '..', 'app');
const REQ_HASH = (() => {
    try {
        return crypto.createHash('sha1')
            .update(fs.readFileSync(path.join(APP_DIR, 'requirements.txt')))
            .digest('hex')
            .slice(0, 10);
    } catch { return 'unknown'; }
})();

function dataDir() {
    if (process.env.IV_DATA_DIR) return process.env.IV_DATA_DIR;
    if (process.platform === 'win32' && process.env.APPDATA) {
        return path.join(process.env.APPDATA, 'InspectionVisualizer');
    }
    return path.join(HOME_DIR, 'data');
}

function pidFile() { return path.join(dataDir(), 'server.pid'); }

function venvPython() {
    return process.platform === 'win32'
        ? path.join(VENV_DIR, 'Scripts', 'python.exe')
        : path.join(VENV_DIR, 'bin', 'python3');
}

function venvPythonw() {
    return process.platform === 'win32'
        ? path.join(VENV_DIR, 'Scripts', 'pythonw.exe')
        : venvPython();
}

// ──────────────────────── Python 探测 ────────────────────────

function detectPython() {
    // IV_PYTHON_CMD 优先,如 "py -3.11" 或 "/usr/bin/python3.11"
    if (process.env.IV_PYTHON_CMD) {
        const parts = process.env.IV_PYTHON_CMD.split(/\s+/).filter(Boolean);
        try {
            const out = spawnSync(parts[0], [...parts.slice(1), '--version'], { encoding: 'utf8', timeout: 8000 });
            if (out.status === 0) return { cmd: parts[0], args: parts.slice(1), version: 'custom' };
        } catch { /* 回落到自动探测 */ }
    }
    const candidates = process.platform === 'win32'
        ? [['py', ['-3']], ['python', []], ['python3', []]]
        : [['python3', []], ['python', []]];
    for (const [cmd, args] of candidates) {
        try {
            const out = spawnSync(cmd, [...args, '--version'], { encoding: 'utf8', timeout: 8000 });
            const text = `${out.stdout || ''}${out.stderr || ''}`;
            const m = text.match(/Python\s+(\d+)\.(\d+)/i);
            if (out.status === 0 && m) {
                const [major, minor] = [Number(m[1]), Number(m[2])];
                if (major > 3 || (major === 3 && minor >= 8)) {
                    return { cmd, args, version: `${major}.${minor}` };
                }
            }
        } catch { /* 下一个候选 */ }
    }
    return null;
}

// ──────────────────────── 运行时供给 ────────────────────────

function runtimeReady() {
    return fs.existsSync(venvPython()) &&
        fs.existsSync(path.join(RUNTIME_DIR, `.provisioned-${REQ_HASH}`));
}

/**
 * 确保 venv 与依赖就绪;首次运行会创建 venv 并 pip 安装(约 200MB,走 pip 缓存会快很多)
 * @param {object} opts { proxy, log }
 */
function ensureRuntime({ proxy, log = console.log } = {}) {
    if (runtimeReady()) return { python: venvPythonw(), fresh: false };

    const python = detectPython();
    if (!python) {
        throw new Error(
            '未找到 Python 3.8+。请安装 Python 后重试(https://www.python.org/downloads/),\n' +
            '  或通过 IV_PYTHON_CMD 环境变量指定,例如: set IV_PYTHON_CMD=py -3.11');
    }
    fs.mkdirSync(RUNTIME_DIR, { recursive: true });

    if (!fs.existsSync(venvPython())) {
        log(`[iv] 使用 Python ${python.version} 创建虚拟环境: ${VENV_DIR}`);
        const r = spawnSync(python.cmd, [...python.args, '-m', 'venv', VENV_DIR], { stdio: 'inherit' });
        if (r.status !== 0 || !fs.existsSync(venvPython())) {
            throw new Error('venv 创建失败,请检查 Python 安装');
        }
    }

    const pipArgs = ['-m', 'pip', 'install', '--disable-pip-version-check',
        '--no-warn-script-location', '-r', path.join(APP_DIR, 'requirements.txt')];
    if (proxy) pipArgs.push('--proxy', proxy);
    log('[iv] 安装依赖(首次较慢,可加 --proxy http://<代理>:<端口> 加速)...');
    const r = spawnSync(venvPython(), pipArgs, { stdio: 'inherit' });
    if (r.status !== 0) {
        throw new Error('依赖安装失败。网络受限时可指定代理重试: iv start --proxy http://<代理>:<端口>');
    }

    const check = spawnSync(venvPython(), ['-c', 'import flask, waitress, sqlalchemy, openpyxl'], { encoding: 'utf8' });
    if (check.status !== 0) throw new Error('运行时自检失败: ' + (check.stderr || '').slice(-400));

    fs.writeFileSync(path.join(RUNTIME_DIR, `.provisioned-${REQ_HASH}`), new Date().toISOString());
    log('[iv] 运行时就绪');
    return { python: venvPythonw(), fresh: true };
}

// ──────────────────────── 健康检查 ────────────────────────

function isHealthy(timeoutMs = 1500) {
    return new Promise((resolve) => {
        const req = http.get({ host: '127.0.0.1', port: PORT, path: '/api/health', timeout: timeoutMs }, (res) => {
            res.resume();
            resolve(res.statusCode === 200);
        });
        req.on('error', () => resolve(false));
        req.on('timeout', () => { req.destroy(); resolve(false); });
    });
}

async function waitHealthy(deadlineMs, isAlive) {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
        if (await isHealthy()) return true;
        if (isAlive && !isAlive()) return false;
        await new Promise(r => setTimeout(r, 1200));
    }
    return false;
}

// ──────────────────────── 服务生命周期 ────────────────────────

function readPid() {
    try {
        const pid = parseInt(fs.readFileSync(pidFile(), 'utf8').trim(), 10);
        if (Number.isInteger(pid) && pid > 0) {
            try { process.kill(pid, 0); return pid; } catch { /* 进程已不在 */ }
        }
    } catch { /* 无 pid 文件 */ }
    return null;
}

function killPid(pid) {
    try {
        if (process.platform === 'win32') {
            spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true });
        } else {
            try { process.kill(-pid, 'SIGTERM'); } catch { try { process.kill(pid, 'SIGTERM'); } catch { } }
        }
    } catch { /* 尽力而为 */ }
}

function openBrowser(url = BASE_URL) {
    const { exec } = require('child_process');
    const cmd = process.platform === 'darwin' ? `open "${url}"`
        : process.platform === 'win32' ? `start "" "${url}"` : `xdg-open "${url}"`;
    try { exec(cmd); } catch { }
}

/**
 * 启动服务(若端口已有健康服务则直接返回 already)
 */
async function startServer({ proxy, log = console.log } = {}) {
    if (await isHealthy()) return { already: true, url: BASE_URL };

    // 残留 pid:先清理再启动,避免双实例
    const stale = readPid();
    if (stale) killPid(stale);

    ensureRuntime({ proxy, log });

    const dd = dataDir();
    const logDir = path.join(dd, 'logs');
    fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, 'server.log');
    try { if (fs.statSync(logFile).size > 5 * 1024 * 1024) fs.truncateSync(logFile, 0); } catch { }
    const logFd = fs.openSync(logFile, 'a');

    log(`[iv] 启动服务: ${BASE_URL} (数据目录 ${dd})`);
    const child = spawn(venvPythonw(), ['app.py'], {
        cwd: APP_DIR,
        env: {
            ...process.env,
            IV_ELECTRON: '1',
            IV_HOST: '0.0.0.0',
            IV_PORT: String(PORT),
            IV_DATA_DIR: dd,
            PYTHONUNBUFFERED: '1',
        },
        detached: true,
        windowsHide: true,
        stdio: ['ignore', logFd, logFd],
    });
    child.unref();
    fs.closeSync(logFd);
    fs.writeFileSync(pidFile(), String(child.pid));
    log(`[iv] PID ${child.pid},等待服务就绪...`);

    const ok = await waitHealthy(120 * 1000, () => {
        try { process.kill(child.pid, 0); return true; } catch { return false; }
    });
    if (!ok) throw new Error(`服务启动超时,日志见 ${logFile}`);
    return { already: false, url: BASE_URL, pid: child.pid, logFile };
}

async function stopServer({ log = console.log } = {}) {
    const pid = readPid();
    if (!pid) {
        if (await isHealthy()) {
            return { stopped: false, reason: `端口 ${PORT} 有服务在运行,但不是本工具启动的(无 pid 记录)` };
        }
        return { stopped: false, reason: '服务未在运行' };
    }
    log(`[iv] 停止服务 (PID ${pid})...`);
    killPid(pid);
    try { fs.unlinkSync(pidFile()); } catch { }
    const deadline = Date.now() + 8000;
    while (await isHealthy(800) && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 500));
    }
    return { stopped: true, pid };
}

async function getStatus() {
    const healthy = await isHealthy();
    return {
        healthy,
        pid: readPid(),
        port: PORT,
        url: BASE_URL,
        dataDir: dataDir(),
        runtimeReady: runtimeReady(),
    };
}

module.exports = {
    PORT, BASE_URL, HOME_DIR, RUNTIME_DIR, APP_DIR,
    dataDir, detectPython, ensureRuntime, runtimeReady,
    isHealthy, waitHealthy, startServer, stopServer, getStatus,
    readPid, openBrowser,
};
