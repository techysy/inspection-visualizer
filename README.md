# IT运维巡检数据可视化

基于 OCR 截图识别的 IT运维巡检记录管理工具。粘贴或上传巡检表单/仪表盘截图，自动提取位置、监控数据等信息，匹配巡检对象，记录巡检结果并展示趋势图表。

支持 深色 / 浅色 / 跟随系统主题切换，按位置和类型双维度筛选巡检对象。

## 功能特点

- **截图识别**：支持 Ctrl+V 粘贴、拖拽、点击上传巡检表单截图
- **OCR 识别**：基于 RapidOCR 自动提取位置、监控点数据、在线率等信息
- **仪表盘解析**：自动识别监控系统仪表盘截图，提取在线/离线/在线率等结构化指标
- **指标配置**：为每个巡检对象配置需要跟踪的指标（名称、单位），可单独开关是否参与图表可视化
- **对象管理**：管理巡检对象，支持位置、类型分类
- **趋势图表**：Chart.js 折线图展示巡检结果历史趋势 + 指标趋势
- **人员管理**：管理巡检人员/班组信息
- **主题切换**：深色 / 浅色 / 跟随系统，偏好本地保存
- **双维度筛选**：按位置 + 类型组合筛选巡检对象
- **数据导出**：下拉菜单导出为 JSON / 自包含 HTML 文件

## 技术栈

- Python 3.8+
- Flask — Web 框架
- SQLAlchemy — ORM，SQLite 持久化
- RapidOCR (ONNX Runtime) — 图片文字识别
- Pillow — 图片处理
- Bootstrap 5 + Chart.js — 前端

## 快速开始

### 安装依赖

```powershell
# 建议使用虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 启动应用

```powershell
python app.py
```

浏览器访问 `http://127.0.0.1:5001`

### 方式二：PowerShell 脚本（推荐）

```powershell
.\start.ps1                  # 显示交互式菜单
.\start.ps1 -Action start    # 前台启动
.\start.ps1 -Action start-bg # 后台启动
.\start.ps1 -Action stop     # 停止服务
.\start.ps1 -Action status   # 查看状态
```

### 方式三：CMD 双击启动

双击 `start.bat`，自动创建虚拟环境、安装依赖并启动。

## 使用方法

### 截图识别

1. 在巡检表单或仪表盘页面截图（或复制截图到剪贴板）
2. 点击导航栏「截图识别」
3. 粘贴 (Ctrl+V)、拖拽或点击上传截图
4. 点击「开始识别」，系统自动提取位置、监控数据等信息
5. 系统自动按位置匹配巡检对象，匹配失败可手动选择
6. 确认无误后点击「确认保存」，数据写入数据库

### 对象管理

访问 `/objects` 管理巡检对象：

- 添加巡检对象（名称、位置、类型、描述）
- 编辑对象信息
- 删除对象（同时清除关联巡检记录）
- **配置指标**：为每个对象添加需要跟踪的指标（如在线率、在线数、离线数等）
  - 每个指标可设置名称、键名、单位
  - 每个指标有独立的「图表」开关，控制是否参与可视化

### 指标配置说明

在对象管理页面，点击对象卡片上的「指标」按钮展开配置面板：

| 操作 | 说明 |
|---|---|
| 添加指标 | 填写名称（如"在线率"）、键（如"onlinerate"）、单位（如"%"） |
| 图表开关 | 勾选/取消勾选决定该指标是否显示在详情页的趋势图表中 |
| 删除指标 | 点击 × 删除不需要的指标 |

常见指标配置示例：

| 名称 | 键 | 单位 |
|---|---|---|
| 在线率 | onlinerate | % |
| 在线 | online | |
| 离线 | offline | |
| 未检测 | undetected | |
| 监控点总数 | total | |

### 人员管理

访问 `/inspectors` 管理巡检人员：

- 添加人员（姓名、班组、联系方式）
- 编辑人员信息
- 删除人员

### 导出

首页或详情页点击导出下拉菜单：

- **JSON** — 结构化数据，包含点位信息和巡检记录
- **HTML** — 自包含单文件，内联 CSS + Chart.js，可部署到 GitHub Pages

## 项目结构

```
inspection-visualizer/
├── app.py                  # Flask 入口
├── app_factory.py          # Flask 工厂
├── app_routes.py           # 路由（首页/详情/点位管理/人员管理/截图OCR/指标API）
├── config.py               # 配置（DB URI, Secret Key）
├── requirements.txt        # Python 依赖
├── start.ps1               # PowerShell 启动脚本（交互式菜单）
├── start.bat               # CMD 启动脚本
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
│   ├── objects.html        # 对象管理（卡片式布局 + 指标配置面板）
│   ├── inspectors.html     # 人员管理（卡片式布局）
│   └── upload.html         # 截图识别（粘贴/拖拽/上传+对象匹配）
│
└── static/css/style.css    # 全局样式（深色/浅色双主题）
```

## 数据模型

SQLite 数据库 `inspection_data.db`，包含四张表：

### inspection_objects（巡检对象）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(100) | 名称 |
| `location` | String(100) | 位置/机房/区域 |
| `device_type` | String(50) | 类型：服务器/网络设备/存储/UPS等 |
| `status` | String(20) | 状态：active/inactive/maintenance |
| `description` | String(255) | 描述/备注 |
| `created_at` | DateTime | 创建时间 |

### object_metrics（指标配置）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `object_id` | Integer(FK) | 关联巡检对象 |
| `key` | String(50) | 指标键名（如 onlinerate） |
| `name` | String(50) | 显示名称（如 在线率） |
| `unit` | String(20) | 单位（如 %） |
| `show_in_chart` | Boolean | 是否参与可视化图表 |
| `sort_order` | Integer | 排序 |

### inspection_records（巡检记录）

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

### inspectors（巡检人员）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 主键 |
| `name` | String(50) | 姓名 |
| `team` | String(50) | 所属班组/部门 |
| `contact` | String(100) | 联系方式（电话/邮箱） |
| `created_at` | DateTime | 创建时间 |

## 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 首页，巡检对象列表 |
| `/object/<id>` | GET | 对象详情 + 巡检图表 + 指标趋势图表 |
| `/objects` | GET | 对象管理页面 |
| `/objects/add` | POST | 添加对象 |
| `/objects/edit/<id>` | POST | 编辑对象 |
| `/objects/delete/<id>` | POST | 删除对象 |
| `/inspectors` | GET | 人员管理页面 |
| `/inspectors/add` | POST | 添加人员 |
| `/inspectors/edit/<id>` | POST | 编辑人员 |
| `/inspectors/delete/<id>` | POST | 删除人员 |
| `/upload` | GET | 截图识别页面 |
| `/import` | GET | 批量导入页面 |
| `/api/ocr` | POST | OCR 识别接口 |
| `/api/save` | POST | 保存识别结果 |
| `/api/objects/list` | GET | 对象列表 JSON |
| `/api/points/list` | GET | 巡检点列表（兼容接口） |
| `/api/objects/<id>/metrics` | GET | 获取对象指标配置 |
| `/api/objects/<id>/metrics` | POST | 添加指标配置 |
| `/api/objects/<id>/metrics/<mid>` | PUT | 更新指标配置 |
| `/api/objects/<id>/metrics/<mid>` | DELETE | 删除指标配置 |
| `/api/objects/import` | POST | 批量导入对象 |
| `/api/inspectors/list` | GET | 人员列表 JSON |
| `/api/inspectors/import` | POST | 批量导入人员 |
| `/api/records/import` | POST | 批量导入巡检记录 |
| `/api/inspection_history/<id>` | GET | 巡检历史 JSON API |
| `/api/inspection_history/delete/<id>` | POST | 删除巡检记录 |
| `/export/json` | GET | 导出全部数据 JSON |
| `/export/html` | GET | 导出全部数据 HTML |

## OCR 识别流程

截图 → OCR 提取文字 → 解析仪表盘/传统表单 → 提取位置和结构化指标 → 匹配数据库对象 → 保存到数据库

### 仪表盘截图识别

自动识别监控系统仪表盘截图，提取：
- 区域名称（从截图左上角提取，优先前5行）
- 监控点总数、在线数、离线数、未检测数、在线率
- 判断整体状态（正常/异常/需关注）

### 结构化指标存储

OCR 识别的指标自动解析为 JSON 存储，如：
```json
{
  "监控点总数": "677",
  "在线": "574",
  "离线": "103",
  "未检测": "0",
  "在线率": "84.79%"
}
```

配合对象的指标配置，可在详情页展示结构化数据和趋势图表。

## 更新日志

### v1.1.0 (2026-06-25)

**新增功能：**
- 仪表盘截图自动识别：支持监控系统仪表盘截图，自动提取位置、在线率等数据
- 指标配置系统：为每个巡检对象配置需要跟踪的指标（名称、单位），可独立开关是否参与图表可视化
- 指标趋势图表：详情页新增指标趋势折线图，展示配置的指标随时间变化
- 结构化指标存储：巡检记录支持 JSON 格式存储结构化指标值
- 指标配置管理 API：新增 `/api/objects/<id>/metrics` 系列接口

**修复与优化：**
- 修复「在线」正则误匹配「离线」导致在线数被覆盖的问题
- 修复保存巡检记录时 `point_id` NOT NULL 约束报错
- 修复前端 `/api/points/list` 接口缺失导致位置下拉框为空的问题
- 优化位置识别逻辑：放宽正则匹配，优先提取截图左上角文本
- 优化前端位置匹配：支持按 `location` 字段精确/包含匹配
- 保存时优先使用前端已选择的巡检对象，避免重复匹配

### v1.0.0

- 初始版本
- OCR 截图识别（支持粘贴、拖拽、点击上传）
- 巡检对象管理（增删改查）
- 巡检人员管理（增删改查）
- 巡检结果趋势图表
- 深色/浅色/跟随系统主题切换
- 按位置 + 类型双维度筛选
- 数据导出（JSON / HTML）

## 许可证

MIT License

---

**Made with ❤️ for IT运维巡检**
