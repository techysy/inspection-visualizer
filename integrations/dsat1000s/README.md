# DS-AT1000S 自动巡检集成

通过海康 **ISAPI 协议** 自动采集 DS-AT1000S 智能分析存储服务器的运行状态，写入 Inspection Visualizer 的巡检记录系统。

## 功能

- 自动采集：设备硬件状态（CPU/内存）、存储信息（RAID/硬盘/存储池）、网络状态
- 智能判定：RAID 降级 → 异常、硬盘故障 → 异常、CPU/内存过高 → 需关注
- 自动写入：通过 `/api/records/import` 接口写入 Inspection Visualizer
- 增量记录：每次运行产生一条巡检记录，历史趋势自动呈现在 IV 图表中

## 采集数据项

| 数据源 | ISAPI 接口 | 采集内容 |
|--------|-----------|---------|
| 设备信息 | `GET /ISAPI/System/deviceInfo` | 型号、固件版本、序列号 |
| 运行状态 | `GET /ISAPI/System/status` | CPU 占用率、内存占用率 |
| 存储信息 | `GET /ISAPI/ContentMgmt/Storage` | RAID 状态、硬盘状态、存储池容量 |
| 网络接口 | `GET /ISAPI/System/Network/interfaces` | 网口状态、IP 地址 |

## 快速开始

### 1. 配置

复制 `.env.example` 为 `.env`，填入实际参数：

```bash
cp integrations/dsat1000s/.env.example integrations/dsat1000s/.env
```

编辑 `.env`：

```ini
# DS-AT1000S 设备
DEVICE_HOST=192.168.1.100     # DS-AT1000S 的 IP 地址
DEVICE_USER=admin              # ISAPI 用户名
DEVICE_PASS=your_password      # ISAPI 密码

# Inspection Visualizer
IV_URL=http://192.168.1.50:5001   # IV 服务地址
IV_OBJECT_NAME=DS-AT1000S 视频存储服务器  # IV 中显示的巡检对象名称
IV_INSPECTOR_NAME=Hermes 自动巡检    # IV 中的巡检人员

# 可选
LOG_LEVEL=INFO                 # DEBUG / INFO / WARNING
```

### 2. 手动运行测试

```bash
cd integrations/dsat1000s
pip install -r requirements.txt

# 测试模式（只打印不写入 IV）
python dsat1000s_to_iv.py --dry-run

# 正式运行
python dsat1000s_to_iv.py
```

### 3. 配置定时任务

#### Hermes cron（推荐）

```bash
hermes cron create \
  --schedule "0 */2 * * *" \
  --script integrations/dsat1000s/dsat1000s_to_iv.py \
  --no-agent \
  --name "DS-AT1000S 自动巡检" \
  --workdir /opt/inspection-visualizer
```

#### Linux crontab

```bash
# 每 2 小时执行一次
0 */2 * * * cd /opt/inspection-visualizer && python integrations/dsat1000s/dsat1000s_to_iv.py >> log/dsat1000s.log 2>&1
```

#### Windows 任务计划程序

```
程序: C:\path\to\venv\Scripts\python.exe
参数: integrations/dsat1000s/dsat1000s_to_iv.py
起始位置: C:\path\to\inspection-visualizer
触发器: 每 2 小时，每天
```

## ISAPI 协议说明

海康设备 ISAPI 接口基于 HTTP + Basic Auth 认证：

- 请求：`GET http://admin:password@device_ip/ISAPI/System/status`
- 响应：XML 格式
- 需要设备开启 ISAPI 服务（默认开启）

## 返回值格式

脚本将采集数据拼接为 IV 认可的 `status_detail` 格式：

```
型号: DS-AT1000S; 固件: V4.30.010; CPU占用: 45%; 内存占用: 60%; 硬盘1: NORMAL - 4000GB; RAID: Normal; 存储总容量: 24000 GB; 存储已用: 12000 GB; 网口eth1 (192.168.1.100): up
```

## 故障排除

| 问题 | 可能原因 | 解决 |
|------|---------|------|
| `ISAPI 请求失败 [401]` | 密码错误 | 检查 `.env` 中的 `DEVICE_PASS` |
| `ISAPI 请求失败 [404]` | 接口路径不对 | 不同固件版本 ISAPI 路径可能有差异，检查设备 Web 管理页 |
| `IV 导入失败` | IV 服务未运行或地址不对 | 确认 `IV_URL` 可访问 |
| 设备不可达 | 网络不通 | `ping DEVICE_HOST` 测试连通性 |
