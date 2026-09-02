# @techysy/inspection-visualizer

巡检数据可视化(OCR 巡检记录管理)的 npm CLI 发行版:全局安装后以**系统托盘**方式管理服务,无需克隆仓库。

```bash
npm i -g @techysy/inspection-visualizer
iv          # 启动服务 + 托盘管理,自动打开浏览器
```

## 命令

| 命令 | 说明 |
|---|---|
| `iv` | 启动服务并进入托盘管理(默认) |
| `iv start [--proxy URL]` | 后台启动服务(detached,首次自动创建 Python 运行时) |
| `iv stop` / `iv restart` | 停止 / 重启服务 |
| `iv status` | 查看服务状态 |
| `iv open` | 浏览器打开巡检系统 |
| `iv autostart on\|off\|status` | 开机自启管理(托盘方式,登录自动运行) |

托盘菜单:打开巡检系统 / 重启服务 / 停止服务 / 开机自启开关 / 退出。

## 系统要求

- Node.js ≥ 18(npm 安装器本身)
- Python ≥ 3.8(首次 `iv start` 时自动创建 venv 并安装依赖到 `~/.inspection-visualizer/runtime`;Windows 下推荐官网安装包或 `winget install Python.Python.3.12`)
- 网络受限时:`iv start --proxy http://<代理>:<端口>`

## 数据目录

与桌面安装版共用同一布局:`%APPDATA%\InspectionVisualizer`(Windows)。SQLite 库、OCR 配置、截图备份、日志都在这里,升级/重装不影响数据。

## 首次登录

系统无预置账号:登录页**用户名留空**,密码填启动生成的默认密码(页面有提示)即可以管理员身份进入;登录后在「人员管理」创建常用账号。在数据目录 `.env` 设置 `APP_PASSWORD=你的密码` 可固定密码。

## 与桌面安装版(electron-builder 产物)的关系

两者是同一服务的两种发行形态,共用数据目录与服务端口(5001),不要同时运行;先停止其中一个再用另一个。
