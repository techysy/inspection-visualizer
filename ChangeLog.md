# 📋 更新日志

## 🚀 [2.0.0] - 2026-06-23

### 🔄 重构：胶卷价格追踪 → IT运维巡检数据可视化

基于 film-price-tracker 项目重构为 IT运维巡检记录管理工具。

### ⚠️ 重大变更

#### 🗄️ 数据模型重构
- `Film` → `InspectionObject`（巡检对象）
- `PriceHistory` → `InspectionRecord`（巡检记录）
- `TaobaoStore` → `Inspector`（巡检人员）
- 数据库表：`inspection_points` → `inspection_objects`
- 数据库文件：`film_prices.db` → `inspection_data.db`

#### 🛤️ 路由变更
- `/points` → `/objects`
- `/point/<id>` → `/object/<id>`
- `/points/add` → `/objects/add`
- `/points/edit/<id>` → `/objects/edit/<id>`
- `/points/delete/<id>` → `/objects/delete/<id>`

#### 📝 命名变更
| 原命名 | 新命名 |
|--------|--------|
| 点位 | 巡检对象 |
| 点位管理 | 对象管理 |
| 设备类型 | 类型 |

### ✨ 新增功能

- 📸 **截图识别**：OCR 自动提取巡检表单数据，支持 Ctrl+V 粘贴、拖拽上传
- 📦 **批量导入** `/import`：支持 Markdown 表格和 CSV 格式批量导入对象、人员、巡检记录
- 📍 **对象管理**：管理巡检对象，支持位置、类型分类
- 👥 **人员管理**：管理巡检人员/班组信息
- 📊 **趋势图表**：Chart.js 折线图展示巡检结果历史趋势
- 🎨 **主题切换**：深色/浅色/跟随系统三档切换
- 🔍 **双维度筛选**：按位置 + 类型组合筛选巡检对象
- 💾 **数据导出**：JSON 和自包含 HTML 两种格式

### 🛠️ 技术栈

- 🐍 Python 3.8+
- 🌐 Flask + SQLAlchemy + SQLite
- 🔤 RapidOCR (ONNX Runtime) - 图片文字识别
- 🎨 Bootstrap 5 + Chart.js - 前端
