# 🔍 IT运维巡检数据可视化

基于 OCR 截图识别的 IT运维巡检记录管理工具。📸 粘贴或上传巡检表单截图，自动匹配巡检对象，记录巡检结果并展示趋势图表。

支持 🌙 深色 / ☀️ 浅色 / 🔄 跟随系统主题切换，按位置和类型双维度筛选巡检对象。

## ✨ 功能特点

- 📸 **截图识别**：支持 Ctrl+V 粘贴、拖拽、点击上传巡检表单截图
- 🔍 **OCR 识别**：基于 RapidOCR 自动提取巡检对象名称、巡检结果、巡检人员等信息
- 📍 **对象管理**：管理巡检对象，支持位置、类型分类
- 📊 **趋势图表**：Chart.js 折线图展示巡检结果历史趋势
- 👥 **人员管理**：管理巡检人员/班组信息
- 🎨 **主题切换**：深色 / 浅色 / 跟随系统，偏好本地保存
- 📁 **双维度筛选**：按位置 + 类型组合筛选巡检对象
- 📦 **数据导出**：下拉菜单导出为 JSON / 自包含 HTML 文件

## 🛠️ 技术栈

- 🐍 Python 3.8+
- 🌐 Flask — Web 框架
- 🗄️ SQLAlchemy — ORM，SQLite 持久化
- 🔤 RapidOCR (ONNX Runtime) — 图片文字识别
- 🖼️ Pillow — 图片处理
- 🎨 Bootstrap 5 + Chart.js — 前端

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

🌐 浏览器访问 `http://127.0.0.1:5001`

### 🔧 方式二：PowerShell 脚本（推荐）

```powershell
.\start.ps1                  # 显示交互式菜单
.\start.ps1 -Action start    # 前台启动
.\start.ps1 -Action start-bg # 后台启动
.\start.ps1 -Action stop     # 停止服务
.\start.ps1 -Action status   # 查看状态
```

菜单选项：

| 按键 | 功能 |
|---|---|
| `S` | ▶️ 前台启动 |
| `B` | 🔙 后台启动（不占用终端） |
| `T` | ⏹️ 停止服务 |
| `C` | 📋 查看状态 |
| `Q` | 🚪 退出 |

### 🖱️ 方式三：CMD 双击启动

双击 `start.bat`，自动创建虚拟环境、安装依赖并启动。

## 📖 使用方法

### 📸 截图识别

1. 在巡检表单或检查单页面截图（或复制截图到剪贴板）
2. 点击导航栏「截图识别」
3. 粘贴 (Ctrl+V)、拖拽或点击上传截图
4. 点击「开始识别」，系统自动提取点位名称、巡检结果、巡检人员等信息
5. 系统自动匹配数据库中的点位，匹配失败可手动选择
6. 确认无误后点击「确认保存」，数据写入数据库

### 📍 对象管理

访问 `/objects` 管理巡检对象：

- ➕ 添加巡检对象（名称、位置、类型、描述）
- ✏️ 编辑对象信息
- 🗑️ 删除对象（同时清除关联巡检记录）
- 🎨 按类型分色显示（服务器/网络设备/存储/UPS/空调等）

### 👥 人员管理

访问 `/inspectors` 管理巡检人员：

- ➕ 添加人员（姓名、班组、联系方式）
- ✏️ 编辑人员信息
- 🗑️ 删除人员

### 📦 导出

首页或详情页点击导出下拉菜单：

- 📄 **JSON** — 结构化数据，包含点位信息和巡检记录
- 🌐 **HTML** — 自包含单文件，内联 CSS + Chart.js，可部署到 GitHub Pages

## 📁 项目结构

```
inspection-visualizer/
├── 📄 app.py                  # Flask 入口
├── 🏭 app_factory.py          # Flask 工厂
├── 🛤️ app_routes.py           # 路由（首页/详情/点位管理/人员管理/截图OCR）
├── ⚙️ config.py               # 配置（DB URI, Secret Key）
├── 📋 requirements.txt        # Python 依赖
├── 🔵 start.ps1               # PowerShell 启动脚本（交互式菜单）
├── 🟢 start.bat               # CMD 启动脚本
│
├── 📂 models/
│   ├── __init__.py
│   └── 🔍 inspection.py       # ORM 模型：InspectionObject, InspectionRecord, Inspector
│
├── 📂 templates/
│   ├── 🏠 base.html           # 布局模板（导航栏、主题切换）
│   ├── 📋 index.html          # 首页（双维度筛选：位置+类型）
│   ├── 📊 object_detail.html  # 详情页（巡检结果趋势图表）
│   ├── 📦 export.html         # 导出模板（自包含单文件 HTML）
│   ├── 📍 objects.html        # 对象管理（卡片式布局）
│   ├── 👥 inspectors.html     # 人员管理（卡片式布局）
│   └── 📸 upload.html         # 截图识别（粘贴/拖拽/上传+对象匹配）
│
└── 🎨 static/css/style.css    # 全局样式（深色/浅色双主题）
```

## 💾 数据模型

SQLite 数据库 `inspection_data.db`，包含三张表：

### 📍 inspection_objects（巡检对象）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(100) | 名称 |
| `location` | String(100) | 位置/机房/区域 |
| `device_type` | String(50) | 类型：服务器/网络设备/存储/UPS等 |
| `status` | String(20) | 状态：active/inactive/maintenance |
| `description` | String(255) | 描述/备注 |
| `created_at` | DateTime | 创建时间 |

### 📝 inspection_records（巡检记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `object_id` | Integer(FK) | 关联巡检对象 |
| `inspector_id` | Integer(FK) | 关联巡检人员 |
| `result` | String(20) | 巡检结果：正常/异常/需关注 |
| `status_detail` | Text | 状态详情：设备运行状态、温度、负载等 |
| `notes` | Text | 备注/问题描述 |
| `timestamp` | DateTime | 巡检时间 |

### 👥 inspectors（巡检人员）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(50) | 姓名 |
| `team` | String(50) | 所属班组/部门 |
| `contact` | String(100) | 联系方式（电话/邮箱） |
| `created_at` | DateTime | 创建时间 |

## 🎯 功能详情

### 🏠 首页

- 📍 巡检对象卡片列表，点击进入详情
- 📐 **位置筛选**：全部 / 机房A / 机房B / 数据中心 / 其他
- 🎞️ **类型筛选**：全部 / 服务器 / 网络设备 / 存储 / UPS / 空调
- 📦 导出下拉菜单（JSON / HTML）
- 🏷️ 显示最近巡检结果状态（正常/异常/需关注）

### 📊 详情页

- 📍 巡检对象基本信息（位置、类型、描述）
- 📈 统计卡片（巡检次数、正常次数、异常次数）
- 📉 Chart.js 折线图展示巡检结果历史趋势
- 📋 巡检历史记录列表（日期、结果、巡检人员、状态详情）
- 🗑️ 支持删除单条巡检记录
- 🎨 图表随主题切换实时更新

### 📸 截图识别 `/upload`

- 📋 支持 Ctrl+V 粘贴截图
- 🖱️ 支持拖拽上传图片
- 📁 支持点击选择文件
- 🔍 OCR 识别后自动匹配巡检对象
- 🎯 匹配成功显示绿色标签，失败显示手动选择下拉框
- ✏️ 支持编辑巡检对象名称、巡检结果
- 💾 保存后提示成功数量和跳过数量
- 🗑️ 支持逐条删除不需要的记录

### 📍 对象管理 `/objects`

- ➕ 添加巡检对象（名称、位置、类型、描述）
- ✏️ 编辑对象信息
- 🗑️ 删除对象（同时清除关联巡检记录）
- 🔗 点击「详情」跳转对象详情页

### 👥 人员管理 `/inspectors`

- ➕ 添加巡检人员（姓名 + 班组 + 联系方式）
- ✏️ 编辑人员信息
- 🗑️ 删除人员

### 🎨 主题切换

导航栏右侧按钮循环切换：

- 🌙 深色模式
- ☀️ 浅色模式
- 🔄 跟随系统（自动匹配 `prefers-color-scheme`）

💾 偏好保存在 localStorage，页面加载无闪烁。

## 🛤️ 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 🏠 首页，巡检对象列表 |
| `/object/<id>` | GET | 📊 对象详情 + 巡检图表 |
| `/objects` | GET | 📍 对象管理页面 |
| `/objects/add` | POST | ➕ 添加对象 |
| `/objects/edit/<id>` | POST | ✏️ 编辑对象 |
| `/objects/delete/<id>` | POST | 🗑️ 删除对象 |
| `/inspectors` | GET | 👥 人员管理页面 |
| `/inspectors/add` | POST | ➕ 添加人员 |
| `/inspectors/edit/<id>` | POST | ✏️ 编辑人员 |
| `/inspectors/delete/<id>` | POST | 🗑️ 删除人员 |
| `/upload` | GET | 📸 截图识别页面 |
| `/import` | GET | 📦 批量导入页面 |
| `/api/ocr` | POST | 🔤 OCR 识别接口 |
| `/api/save` | POST | 💾 保存识别结果 |
| `/api/objects/list` | GET | 📍 对象列表 JSON |
| `/api/objects/import` | POST | 📦 批量导入对象 |
| `/api/inspectors/list` | GET | 👥 人员列表 JSON |
| `/api/inspectors/import` | POST | 📦 批量导入人员 |
| `/api/records/import` | POST | 📦 批量导入巡检记录 |
| `/api/inspection_history/<object_id>` | GET | 📈 巡检历史 JSON API |
| `/api/inspection_history/delete/<id>` | POST | 🗑️ 删除巡检记录 |
| `/export/json` | GET | 📄 导出全部数据 JSON |
| `/export/html` | GET | 🌐 导出全部数据 HTML |

## 🔄 OCR 识别流程

📸 截图 → 🔤 OCR 提取文字 → 🔍 解析对象/结果/人员 → 🎯 匹配数据库对象 → 💾 保存到数据库

- 检测到巡检对象名称时自动匹配数据库对象
- 检测到巡检结果关键词（正常/异常/需关注）时自动标记
- 检测到时间格式时自动解析巡检时间
- 检测到姓名特征时自动匹配巡检人员

- 匹配成功：自动关联对象，显示绿色标签
- 匹配失败：手动从下拉框选择对象
- 未选择：自动跳过，提示跳过数量

## 📄 许可证

MIT License

---

**Made with ❤️ for IT运维巡检**