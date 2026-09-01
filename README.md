# 🔍 IT运维巡检数据可视化

基于 OCR 截图识别的 IT运维巡检记录管理工具。粘贴或上传巡检表单/仪表盘截图，自动提取位置、监控数据等信息，匹配巡检对象，记录巡检结果并展示趋势图表。

支持 🌙 深色 / ☀️ 浅色 / 🖥️ 跟随系统主题切换，按位置和类型双维度筛选巡检对象。

## ✨ 功能特点

- 📷 **截图识别**：支持 Ctrl+V 粘贴、拖拽、点击上传巡检表单截图
- 🔌 **Chrome 扩展**：浏览器插件框选页面区域截图并自动识别，无需切换页面
- 🖼️ **截图预览**：按日期分组展示备份截图，支持缩略图和 Lightbox 全屏浏览
- 🛡️ **智能截图备份**：仅在巡检记录成功保存后才备份截图，无效/重复数据自动跳过，避免冗余备份
- 🔬 **OCR 识别**：基于 RapidOCR 自动提取位置、监控点数据、在线率等信息
- 📊 **仪表盘解析**：支持自定义仪表盘类型，自动识别并提取结构化指标，支持分类管理
- ⚙️ **指标配置**：为每个巡检对象配置需要跟踪的指标（名称、单位），可单独开关是否参与图表可视化
- 📦 **对象管理**：管理巡检对象，支持分类关联仪表盘类型，支持一键复制，支持配置项目网址
- 🔗 **项目网址跳转**：为巡检对象配置项目网址，首页未巡检标签可直接点击跳转
- 📈 **趋势图表**：Chart.js 折线图展示巡检结果历史趋势（正常/异常/需关注三状态）+ 指标趋势
- 👥 **人员管理**：管理巡检人员/班组信息
- 🎨 **主题切换**：深色 / 浅色 / 跟随系统，偏好本地保存
- 🔎 **双维度筛选**：按位置 + 分类组合筛选巡检对象
- 📤 **数据导出**：下拉菜单导出为 JSON / 自包含 HTML 文件 / Excel 巡检报告（含在线率、离线自动计算）
- 🧮 **计算类别补全**：数据维护支持百分比、差值、求和、自定义公式计算新指标
- 📈 **增量计算**：独立开关，自动与上一条记录对比，按天数平滑（周末÷3），首条为0，支持历史回填
- 🧬 **虚拟指标**：仪表盘类型 `calc_config` 自动管理虚拟指标，不可删除仅可编辑阈值
- 🔍 **对象列表筛选**：对象管理页面输入名称/位置/分类实时筛选匹配的巡检对象
- 🗂️ **历史记录按周折叠**：详情页历史记录按本周/上周/更早分组，上周及更早自动收起
- 📥 **批量导入**：支持 Markdown 表格、CSV、JSON 格式，两步操作（识别预览 → 确认导入）
- 🔧 **全局变量**：可配置 OCR 位置提取时的跳过关键词
- 🚫 **位置匹配开关**：仪表盘类型可设置「不使用位置匹配」，仅通过类型分类匹配
- 🔐 **密码登录鉴权**：系统启动后需密码登录，密码配置在 `.env` 文件中
- ⏱️ **时间范围筛选**：对象详情页支持「仅显示最近两周」开关，按自然周筛选统计数据和趋势图

## 🛠️ 技术栈

- Python 3.8+
- ⚡ Flask — Web 框架
- 🗃️ SQLAlchemy — ORM，SQLite 持久化
- 🔤 RapidOCR (ONNX Runtime) — 图片文字识别
- 🖼️ Pillow — 图片处理
- 🎨 Bootstrap 5 + Chart.js — 前端
- 🔌 Chrome Extension (Manifest V3) — 浏览器插件

## 🚀 快速开始

### 📦 安装依赖

```powershell
# 建议使用虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### ▶️ 启动应用

```powershell
python app.py
```

浏览器访问 `http://127.0.0.1:5001`

首次启动会生成随机默认密码并打印在控制台。也可在 `.env` 文件中设置 `APP_PASSWORD=你的密码`。

### 💻 方式二：PowerShell 脚本（推荐）

```powershell
.\iv-start.ps1                  # 显示交互式菜单
.\iv-start.ps1 -Action start    # 前台启动
.\iv-start.ps1 -Action restart  # 重启服务
.\iv-start.ps1 -Action stop     # 停止服务
.\iv-start.ps1 -Action status   # 查看状态
```

> **注意**：首次运行可能遇到执行策略限制，需先执行：
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
> ```

### 🖱️ 方式三：CMD 双击启动

双击 `start.bat`，自动创建虚拟环境、安装依赖并启动。

### 🖥️ 方式四：桌面托盘版（Electron，推荐给非技术用户）

系统托盘常驻图标管理服务，双击安装包即可使用，无需 Python 环境：

- 托盘菜单：打开巡检系统 / 启动 / 停止 / 重启服务 / 开机自启（勾选即生效，无需任务计划程序）/ 打开数据目录 / 打开日志 / 退出
- 启动成功自动打开内嵌窗口，外链（项目网址跳转等）走系统默认浏览器；点窗口关闭只是最小化到托盘
- 数据目录独立于程序：`%APPDATA%\InspectionVisualizer`（SQLite 库、`global_vars.json`、`ocr_config.json`、截图备份、日志、`initial_password.txt`），卸载/升级程序不影响数据
- 未设置 `APP_PASSWORD` 时每次启动生成随机密码并写入数据目录 `initial_password.txt`，托盘会气泡提醒；在数据目录建 `.env` 写入 `APP_PASSWORD=你的密码` 可固定
- 服务监听 `0.0.0.0:5001`（waitress 生产服务器），局域网设备可直接访问；端口被占用时自动检测并直接打开已有服务

**开发运行**（使用仓库 venv 的 Python）：

```powershell
cd desktop
npm install          # 首次，建议 $env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
npm start
```

**打包**（产出 NSIS 安装包 + 便携版 exe）：

```powershell
cd desktop
.\build.ps1 -Proxy http://<代理地址>:<端口>   # 首次需下载 Embeddable Python 与依赖，约 200MB
# 产物在 desktop\dist\：InspectionVisualizer Setup x.x.x.exe / InspectionVisualizer-Portable-x.x.x.exe
```

> 打包脚本说明：`build-python-runtime.ps1` 构建 Windows Embeddable Python 运行时（含全部 pip 依赖，写入 `._pth` 使 `resources\python` 与 `resources\app` 同级布局可导入）；`build.ps1` 汇集应用源码并调用 electron-builder。打包时自动排除 `venv`、`integrations`、`film_price_tracker`、`.env`、`*.db`、日志与备份目录。

## ⚙️ 开机自启动

### 🪟 Windows

#### 方法一：任务计划程序（推荐）

1. 按 `Win+R`，输入 `taskschd.msc` 打开任务计划程序
2. 点击右侧「创建基本任务」
3. 名称填写 `InspectionTracker`，描述填写 `巡检数据可视化服务`
4. 触发器选择「当用户登录时」
5. 操作选择「启动程序」
6. 程序填写：
   ```
   C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
   ```
   参数填写：
   ```
   -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\inspection-visualizer\iv-start.ps1" -Action start
   ```
   > 将路径替换为实际项目路径
7. 勾选「完成后打开属性对话框」
8. 在「条件」选项卡中，取消勾选「只有在计算机使用交流电源时才启动此任务」
9. 点击确定完成

#### 方法二：启动文件夹快捷方式

1. 创建 `start.bat` 的快捷方式
2. 按 `Win+R`，输入 `shell:startup` 打开启动文件夹
3. 将快捷方式放入该文件夹
4. 重启电脑验证服务自动启动

#### 方法三：注册为 Windows 服务（高级）

使用 [NSSM](https://nssm.cc/) 将应用注册为系统服务：

```powershell
# 下载 NSSM
choco install nssm  # 或从 https://nssm.cc/download 手动下载

# 注册服务
nssm install InspectionTracker "C:\path\to\inspection-visualizer\venv\Scripts\python.exe" "app.py"
nssm set InspectionTracker AppDirectory "C:\path\to\inspection-visualizer"
nssm set InspectionTracker DisplayName "InspectionTracker - 巡检数据可视化"
nssm set InspectionTracker Description "IT运维巡检数据可视化服务"
nssm set InspectionTracker Start SERVICE_AUTO_START

# 启动服务
nssm start InspectionTracker

# 管理命令
nssm stop InspectionTracker
nssm restart InspectionTracker
nssm remove InspectionTracker confirm  # 卸载
```

### 🐧 Linux

#### 方法一：systemd 服务（推荐）

1. 创建服务文件：

```bash
sudo tee /etc/systemd/system/inspection-tracker.service << 'EOF'
[Unit]
Description=InspectionTracker - IT运维巡检数据可视化
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/inspection-visualizer
ExecStart=/opt/inspection-visualizer/venv/bin/python app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

# 安全加固
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/inspection-visualizer

[Install]
WantedBy=multi-user.target
EOF
```

2. 部署项目并安装依赖：

```bash
# 克隆项目
sudo mkdir -p /opt/inspection-visualizer
sudo git clone https://github.com/your-repo/inspection-visualizer.git /opt/inspection-visualizer

# 创建虚拟环境
cd /opt/inspection-visualizer
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 设置权限
sudo chown -R www-data:www-data /opt/inspection-visualizer
```

3. 配置环境变量：

```bash
sudo tee /opt/inspection-visualizer/.env << 'EOF'
APP_PASSWORD=your_password_here
SECRET_KEY=your_secret_key_here
EOF

sudo chown www-data:www-data /opt/inspection-visualizer/.env
sudo chmod 600 /opt/inspection-visualizer/.env
```

4. 启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable inspection-tracker
sudo systemctl start inspection-tracker

# 查看状态
sudo systemctl status inspection-tracker

# 查看日志
sudo journalctl -u inspection-tracker -f
```

#### 方法二：简单 Shell 脚本 + crontab

创建启动脚本：

```bash
#!/bin/bash
# /opt/inspection-visualizer/start.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/server.pid"
LOG_FILE="$SCRIPT_DIR/log/app.log"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

cd "$SCRIPT_DIR"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Server already running (PID: $OLD_PID)"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# 启动服务
mkdir -p log
nohup "$VENV_PYTHON" app.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Server started (PID: $!)"
```

设置开机自启：

```bash
chmod +x /opt/inspection-visualizer/start.sh

# 添加到 crontab
crontab -e
# 添加以下行（@reboot 在开机时执行）
@reboot /opt/inspection-visualizer/start.sh
```

#### 方法三：Supervisor 进程管理

```bash
# 安装 supervisor
sudo apt install supervisor

# 创建配置
sudo tee /etc/supervisor/conf.d/inspection-tracker.conf << 'EOF'
[program:inspection-tracker]
command=/opt/inspection-visualizer/venv/bin/python app.py
directory=/opt/inspection-visualizer
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/inspection-tracker.err.log
stdout_logfile=/var/log/inspection-tracker.out.log
environment=PYTHONUNBUFFERED="1"
EOF

# 启动
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start inspection-tracker

# 管理命令
sudo supervisorctl status inspection-tracker
sudo supervisorctl restart inspection-tracker
sudo supervisorctl stop inspection-tracker
```

### 🍓 树莓派 / 嵌入式 Linux

适用于树莓派等低功耗设备，使用 systemd 服务 + 轻量配置：

```bash
# 克隆项目
git clone https://github.com/your-repo/inspection-visualizer.git
cd inspection-visualizer

# 创建虚拟环境并安装依赖
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 创建服务
sudo tee /etc/systemd/system/inspection-tracker.service << EOF
[Unit]
Description=InspectionTracker
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable inspection-tracker
sudo systemctl start inspection-tracker
```

### 🔒 安全建议

无论使用哪种自启动方式，建议：

1. **不要以 root 运行**：创建专用用户（如 `www-data`）运行服务
2. **保护 `.env` 文件**：设置权限 `chmod 600 .env`
3. **配置防火墙**：仅允许内网访问 5001 端口
4. **使用反向代理**：生产环境建议 Nginx/Caddy 反向代理，启用 HTTPS
5. **定期备份数据库**：`inspection_data.db` 文件

### 🔌 Chrome 扩展安装

浏览器插件，支持在任意页面框选区域截图并自动 OCR 识别巡检数据。

1. 打开 Chrome，地址栏输入 `chrome://extensions`
2. 右上角开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择本项目的 `chrome-extension` 文件夹
5. 扩展图标出现在工具栏，建议点击 📌 固定

**快捷键**：`Ctrl+Shift+S` 快速启动框选截图（需在扩展管理页 → 快捷键 中确认未冲突）

> 详见 [chrome-extension/README.md](chrome-extension/README.md)

## 📖 使用方法

### 📷 截图识别

**方式一：系统内上传**

1. 在巡检表单或仪表盘页面截图（或复制截图到剪贴板）
2. 点击导航栏「截图识别」
3. 粘贴 (Ctrl+V)、拖拽或点击上传截图
4. 点击「开始识别」，系统自动提取位置、监控数据等信息
5. 系统自动按位置匹配巡检对象，匹配失败可手动选择
6. 确认无误后点击「确认保存」，数据写入数据库

**方式二：Chrome 扩展框选截图**

浏览器插件，直接在任意页面框选区域截图并自动识别，无需手动切换页面。

1. 安装：打开 `chrome://extensions` → 开启「开发者模式」→「加载已解压的扩展程序」→ 选择 `chrome-extension` 文件夹
2. 打开巡检表单或仪表盘页面
3. 点击工具栏扩展图标 → 点击「框选截图识别」
4. 在页面上拖拽框选需要识别的区域，松开后自动截图并 OCR 识别
5. 编辑识别到的数值 → 点击「保存到系统」
6. 快捷键 `Ctrl+Shift+S` 快速启动框选截图

> 详见 [chrome-extension/README.md](chrome-extension/README.md)

### 📦 对象管理

访问 `/objects` 管理巡检对象：

- ➕ 添加巡检对象（名称、位置、类型、描述）
- ✏️ 编辑对象信息
- 🔀 拖拽排序（组内卡片拖拽重排，自动保存排序顺序）
- 📋 复制对象（一键克隆，含指标配置，修改位置即可快速创建）
- 🗑️ 删除对象（同时清除关联巡检记录）
- ⚙️ **配置指标**：为每个对象添加需要跟踪的指标（如在线率、在线数、离线数等）
  - 每个指标可设置名称、键名、单位
  - 每个指标有独立的「图表」开关，控制是否参与可视化

### ⚙️ 指标配置说明

在对象管理页面，点击对象卡片上的「指标」按钮展开配置面板：

| 操作 | 说明 |
|---|---|
| ➕ 添加指标 | 填写名称（如"在线率"）、键（如"onlinerate"）、单位（如"%"） |
| 🔀 图表开关 | 勾选/取消勾选决定该指标是否显示在详情页的趋势图表中 |
| ❌ 删除指标 | 点击 × 删除不需要的指标 |

常见指标配置示例：

| 名称 | 键 | 单位 | 最大值 |
|---|---|---|---|
| 在线率 | onlinerate | % | 100 |
| 在线 | online | | 700 |
| 离线 | offline | | 700 |
| 未检测 | undetected | | 700 |
| 监控点总数 | total | | 700 |

### 👥 人员管理

访问 `/inspectors` 管理巡检人员：

- ➕ 添加人员（姓名、班组、联系方式）
- ✏️ 编辑人员信息
- 🗑️ 删除人员

### 📤 导出

首页或详情页点击导出下拉菜单：

- 📄 **JSON** — 结构化数据，包含点位信息和巡检记录
- 🌐 **HTML** — 自包含单文件，内联 CSS + Chart.js，可部署到 GitHub Pages

## 📁 项目结构

```
inspection-visualizer/
├── app.py                  # Flask 入口
├── app_factory.py          # Flask 工厂
├── app_routes.py           # 路由（首页/详情/点位管理/人员管理/截图OCR/指标API）
├── config.py               # 配置（DB URI, Secret Key）
├── requirements.txt        # Python 依赖
├── start.bat               # CMD 启动脚本
├── iv-start.ps1            # PowerShell 启动脚本（交互式菜单）
├── iv-start.ps1            # PowerShell 启动脚本（交互式菜单）
├── dashboard_types.json    # 仪表盘类型配置（关键词/标签映射/结果规则）
├── ocr_config.json         # OCR 引擎参数配置
├── global_vars.json        # 全局变量配置（跳过关键词等）
│
├── log/                    # 运行日志（按日轮转，保留 30 天）
│   └── app.log
│
├── models/
│   ├── __init__.py
│   └── inspection.py       # ORM 模型：InspectionObject, InspectionRecord, Inspector, ObjectMetric
│
├── templates/
│   ├── base.html           # 布局模板（导航栏、主题切换）
│   ├── index.html          # 首页（双维度筛选：位置+类型）
│   ├── object_detail.html  # 详情页（巡检结果趋势 + 指标趋势图表）
│   ├── export.html         # 导出模板（自包含单文件 HTML）
│   ├── objects.html        # 对象管理（卡片式布局 + 指标配置面板 + 分组显示）
│   ├── inspectors.html     # 人员管理（卡片式布局）
│   ├── upload.html         # 截图识别（粘贴/拖拽/上传+对象匹配+快速创建）
│   ├── ocr_admin.html      # OCR管理（仪表盘类型/全局变量/识别参数/测试识别）
│   └── bulk_import.html    # 批量导入（Markdown/CSV/JSON，两步识别预览）
│
├── static/css/style.css    # 全局样式（深色/浅色双主题）
│
└── chrome-extension/        # 🔌 Chrome 扩展（框选截图OCR识别）
    ├── manifest.json
    ├── popup.html/js         # 弹出窗口 UI
    ├── content.js/css        # 页面框选覆盖层
    ├── background.js         # 后台消息中转
    └── icons/                # 扩展图标
```

## 🗄️ 数据模型

SQLite 数据库 `inspection_data.db`，包含四张表：

### 📋 inspection_objects（巡检对象）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(100) | 名称 |
| `location` | String(100) | 位置/机房/区域 |
| `device_type` | String(50) | 类型：服务器/网络设备/存储/UPS等 |
| `status` | String(20) | 状态：active/inactive/maintenance |
| `description` | String(255) | 描述/备注 |
| `sort_order` | Integer | 排序序号（拖拽排序存储） |
| `created_at` | DateTime | 创建时间 |

### 📊 object_metrics（指标配置）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `object_id` | Integer(FK) | 关联巡检对象 |
| `key` | String(50) | 指标键名（如 onlinerate） |
| `name` | String(50) | 显示名称（如 在线率） |
| `unit` | String(20) | 单位（如 %） |
| `max_value` | Float | 图表Y轴最大值（百分比默认100） |
| `show_in_chart` | Boolean | 是否参与可视化图表 |
| `sort_order` | Integer | 排序 |
| `warn_threshold` | Float | 关注阈值 |
| `error_threshold` | Float | 异常阈值 |
| `threshold_direction` | String(5) | 阈值方向：lt(小于)/gt(大于) |

### 📝 inspection_records（巡检记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `point_id` | Integer | 兼容旧数据库 |
| `object_id` | Integer(FK) | 关联巡检对象 |
| `inspector_id` | Integer(FK) | 关联巡检人员 |
| `result` | String(20) | 巡检结果：正常/异常/需关注 |
| `status_detail` | Text | 状态详情（原始文本） |
| `metrics` | Text | 结构化指标值（JSON） |
| `notes` | Text | 备注/问题描述 |
| `timestamp` | DateTime | 巡检时间 |

### 👤 inspectors（巡检人员）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(50) | 姓名 |
| `team` | String(50) | 所属班组/部门 |
| `contact` | String(100) | 联系方式（电话/邮箱） |
| `created_at` | DateTime | 创建时间 |

## 🛣️ 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 🏠 首页，巡检对象列表 |
| `/object/<id>` | GET | 📊 对象详情 + 巡检图表 + 指标趋势图表 |
| `/objects` | GET | 📦 对象管理页面 |
| `/objects/add` | POST | ➕ 添加对象 |
| `/objects/edit/<id>` | POST | ✏️ 编辑对象 |
| `/objects/delete/<id>` | POST | 🗑️ 删除对象 |
| `/objects/clone/<id>` | POST | 📋 复制对象（含指标配置） |
| `/inspectors` | GET | 👥 人员管理页面 |
| `/inspectors/add` | POST | ➕ 添加人员 |
| `/inspectors/edit/<id>` | POST | ✏️ 编辑人员 |
| `/inspectors/delete/<id>` | POST | 🗑️ 删除人员 |
| `/upload` | GET | 📷 截图识别页面 |
| `/import` | GET | 📥 批量导入页面 |
| `/api/ocr` | POST | 🔍 OCR 识别接口 |
| `/api/save` | POST | 💾 保存识别结果 |
| `/api/objects/list` | GET | 📋 对象列表 JSON |
| `/api/objects/suggestions` | GET | 🔍 获取对象建议（自动补全，参数：`q` 查询词, `field` 字段：name/location/device_type） |
| `/api/points/list` | GET | 📍 巡检点列表（兼容接口） |
| `/api/objects/<id>/metrics` | GET | 📊 获取对象指标配置 |
| `/api/objects/<id>/metrics` | POST | ➕ 添加指标配置 |
| `/api/objects/<id>/metrics/<mid>` | PUT | ✏️ 更新指标配置 |
| `/api/objects/<id>/metrics/<mid>` | DELETE | 🗑️ 删除指标配置 |
| `/api/objects/quick-create` | POST | ⚡ 快速创建巡检对象（JSON API） |
| `/api/objects/sort` | POST | 🔄 保存巡检对象拖拽排序（`{order: [{id:1}, ...]}`） |
| `/api/objects/<id>/sync-metrics` | POST | 🔄 从仪表盘类型同步指标配置 |
| `/api/dashboard-types` | GET | 📋 获取所有仪表盘类型 |
| `/api/dashboard-types` | POST | ➕ 添加仪表盘类型 |
| `/api/dashboard-types/<id>` | PUT | ✏️ 更新仪表盘类型 |
| `/api/dashboard-types/<id>` | DELETE | 🗑️ 删除仪表盘类型 |
| `/api/dashboard-types/categories` | GET | 📂 获取所有仪表盘分类 |
| `/api/dashboard-types/calc-configs` | GET | 🧮 获取所有仪表盘类型的计算配置 |
| `/api/dashboard-types/sync` | POST | 🔄 从巡检对象批量同步指标 |
| `/api/dashboard-types/<id>/sync` | POST | 🔄 从巡检对象同步指标到指定类型 |
| `/api/global-vars` | GET | 🔧 获取全局变量配置 |
| `/api/global-vars` | POST | 🔧 保存全局变量配置 |
| `/api/objects/import` | POST | 📥 批量导入对象 |
| `/api/inspectors/list` | GET | 👥 人员列表 JSON |
| `/api/inspectors/import` | POST | 📥 批量导入人员 |
| `/api/records/import` | POST | 📥 批量导入巡检记录 |
| `/api/inspection_history/<id>` | GET | 📜 巡检历史 JSON API |
| `/api/inspection_history/delete/<id>` | POST | 🗑️ 删除巡检记录 |
| `/api/records/backfill` | POST | 🔄 回填历史记录（补全缺失的总数/离线） |
| `/api/records/backfill-increment` | POST | 📈 回填增量指标（按天数平滑，首条为0） |
| `/api/backup/gallery` | GET | 🖼️ 获取备份截图列表（按日期分组） |
| `/api/records/cleanup` | POST | 🧹 清理错误的总数/离线字段 |
| `/api/records/compute` | POST | 🧮 计算补全指标（求和/百分比/差值/自定义公式） |
| `/api/export/excel` | GET/POST | 📤 导出巡检报告 Excel（含在线率、离线计算） |
| `/export/json` | GET | 📤 导出全部数据 JSON |
| `/export/html` | GET | 🌐 导出全部数据 HTML |

## 🔍 OCR 识别流程

📷 截图 → 🔤 OCR 提取文字 → 📊 解析仪表盘/传统表单 → 📍 提取位置和结构化指标 → 🔄 匹配数据库对象 → 💾 保存到数据库

### 📊 仪表盘截图识别

支持自定义仪表盘类型（`/ocr-admin` 管理），每种类型配置：

| 配置项 | 说明 |
|---|---|
| 类型名称 | 如"智慧城管平台"、"环卫车辆管理" |
| 分类 | 用于巡检对象关联匹配（如监控、车辆、工牌） |
| 识别关键词 | 包含任一即命中该类型 |
| 标签映射 | OCR 文本 → 结构化指标（如 在线→online） |
| 结果规则 | 状态判定阈值（如 offline>0→异常、online_rate<90→异常） |
| 数字前置格式 | 支持 "209 关注" 格式 |
| 不使用位置匹配 | 启用后仅通过类型分类匹配，忽略位置 |

巡检对象创建时自动从关联的仪表盘类型同步指标配置。

### 📊 结构化指标存储

OCR 识别的指标自动解析为 JSON 存储，如：
```json
{
  "监控点总数": "100",
  "在线": "84",
  "离线": "16",
  "未检测": "0",
  "在线率": "84%"
}
```

配合对象的指标配置，可在详情页展示结构化数据和趋势图表。

## 🤖 自动数据采集

除了手动截图 OCR，Inspection Visualizer 还支持通过 API 接收第三方系统自动推送的巡检数据。内置集成脚本可直接对接设备 ISAPI 接口，实现无人值守的自动巡检。

### 已支持的集成

| 集成 | 目标设备 | 协议 | 文档 |
|------|---------|------|------|
| [DS-AT1000S](integrations/dsat1000s/) | 海康智能分析存储服务器 | ISAPI (HTTP) | [📖 文档](integrations/dsat1000s/README.md) |

### 工作原理

```
设备 ISAPI 接口
      │
      ▼
集成脚本 (integrations/<设备>/)
  采集硬件/存储/网络状态
  自动判定正常/异常/需关注
      │
      ▼
POST /api/records/import
      │
      ▼
Inspection Visualizer 数据库
      │
      ▼
Web 端趋势图表 + 历史记录
```

### 添加新集成

集成目录统一放在 `integrations/<设备名>/`，遵循以下约定：

- `README.md` — 安装配置文档
- `.env.example` — 配置模板
- `<设备名>_to_iv.py` — 采集脚本（标准库依赖，无额外 pip 包）
- `requirements.txt` — 额外依赖说明（如有）

采集脚本通过 POST `/api/records/import` 接口写入巡检记录，接口接受的字段见 [批量导入 API](#-批量导入)。

欢迎贡献新的设备集成！

## 📝 更新日志

详见 [ChangeLog.md](ChangeLog.md)

## 🔗 相关项目

- 🎞️ [film-price-tracker](https://github.com/techysy/film-price-tracker) — 基于 OCR 截图识别的胶卷价格追踪工具，粘贴淘宝购物车截图自动识别价格

## 📄 许可证

MIT License

---

**Made ❤️ for IT运维巡检**
