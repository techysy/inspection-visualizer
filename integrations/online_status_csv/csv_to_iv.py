#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在线状态 CSV -> Inspection Visualizer

把平台导出的「监控点在线状态」明细 CSV 按所在区域聚合成区域级巡检记录，
写入 Inspection Visualizer。

明细 CSV 一行代表一个监控点，直接导入会给每个球机建一条记录，
把趋势图打爆且没有任何数字指标。本脚本先做聚合，再走 /api/records/import。

依赖：仅标准库。
"""

import argparse
import csv
import http.cookiejar
import io
import json
import logging
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# CSV 表头别名，兼容不同平台导出的列名差异
HEADER_ALIASES = {
    "name": ["监控点名称", "设备名称", "通道名称", "点位名称"],
    "area": ["所在区域", "区域", "所属区域", "组织"],
    "ip": ["IP地址", "ip地址", "IP"],
    "status": ["在线状态", "状态", "设备状态"],
    "changed_at": ["状态变更时间", "变更时间"],
    "duration": ["状态持续时长", "持续时长"],
    "record": ["录制状态"],
    "checked_at": ["巡检时间", "采集时间", "统计时间"],
    "gb_code": ["国标编码", "国标ID"],
    "reason": ["离线原因", "异常原因", "原因"],
    "res_code": ["资源编码"],
    # 汇总表字段（一行即一个区域）
    "total": ["监控点总数", "总数", "设备总数"],
    "online": ["在线数", "在线数量"],
    "offline": ["离线数", "离线数量"],
    "undetected": ["未检测数", "未检测数量"],
    "whitelist": ["白名单数", "白名单数量"],
    "rate": ["在线率"],
}

ONLINE_WORDS = ("在线", "正常", "online")
OFFLINE_WORDS = ("离线", "掉线", "异常", "offline")

# 项目根目录的 global_vars.json（里面有 location_aliases）
GLOBAL_VARS_PATH = Path(__file__).parents[2] / "global_vars.json"


def load_global_aliases(logger):
    """加载全局位置别名。优先读项目 global_vars.json，失败返回空字典。"""
    if not GLOBAL_VARS_PATH.exists():
        return {}
    try:
        with open(GLOBAL_VARS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        aliases = data.get("location_aliases", {})
        if aliases:
            logger.info("已加载 %d 条位置别名", len(aliases))
        return aliases
    except Exception as e:
        logger.warning("读取 global_vars.json 失败，跳过位置别名: %s", e)
        return {}


def normalize_area(area, aliases):
    """应用位置别名。支持完整字符串匹配和层级路径中的分段匹配。

    例：
        中江县综合行政执法局         -> 城区
        中江县/中江县综合行政执法局   -> 中江县/城区
    """
    if not area or not aliases:
        return area
    # 1) 完整字符串直接命中
    if area in aliases:
        return aliases[area]
    # 2) 层级路径分段替换
    raw_parts = [p.strip() for p in re.split(r"[/／>＞\\]", area) if p.strip()]
    if not raw_parts:
        return area
    changed = False
    parts = []
    for p in raw_parts:
        np = aliases.get(p, p)
        if np != p:
            changed = True
        parts.append(np)
    return "/".join(parts) if changed else area


def load_config():
    """从同目录 .env 读取配置，环境变量优先"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

    return {
        "iv_url": os.environ.get("IV_URL", "http://127.0.0.1:5001"),
        "iv_username": os.environ.get("IV_USERNAME", ""),
        "iv_password": os.environ.get("IV_PASSWORD", ""),
        "inspector_name": os.environ.get("IV_INSPECTOR_NAME", "CSV 自动巡检"),
        "area_mode": os.environ.get("AREA_MODE", "leaf"),
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
    }


def setup_logging(level_name, dry_run):
    prefix = "[DRY-RUN] " if dry_run else ""
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format=f"%(asctime)s %(levelname)s {prefix}%(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger("csv_to_iv")


# ---------------------------------------------------------------------------
# CSV 读取
# ---------------------------------------------------------------------------

def read_csv_rows(path):
    """读 CSV，自动探测编码和分隔符（逗号/制表符/分号），返回 (列名映射, 行字典列表)"""
    raw = Path(path).read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"无法解码 CSV 文件: {path}")

    # 探测分隔符；样本取前 4KB，避免大文件影响性能
    sample = text[:4096]
    dialect = None
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except Exception:
        pass

    reader = csv.reader(io.StringIO(text), dialect=dialect) if dialect else csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("CSV 为空")

    header = [c.strip().lstrip("\ufeff") for c in rows[0]]
    colmap = resolve_columns(header)
    records = []
    for r in rows[1:]:
        item = {}
        for field, idx in colmap.items():
            item[field] = r[idx].strip() if idx is not None and idx < len(r) else ""
        records.append(item)
    return header, colmap, records


def resolve_columns(header):
    """把表头解析成字段索引，精确匹配优先，避免「巡检时间」被「状态变更时间」抢走"""
    lower = [h.lower() for h in header]
    colmap = {}
    for field, aliases in HEADER_ALIASES.items():
        idx = None
        for alias in aliases:                      # 先走精确匹配
            al = alias.lower()
            if al in lower:
                idx = lower.index(al)
                break
        if idx is None:                            # 再退化到包含匹配
            for alias in aliases:
                al = alias.lower()
                hit = [i for i, h in enumerate(lower) if al in h]
                if hit:
                    idx = hit[0]
                    break
        colmap[field] = idx
    return colmap


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------

def split_area(area, mode):
    """区域字段拆分。'中江县/东江公园' -> leaf=东江公园, root=中江县, full=原串"""
    parts = [p.strip() for p in re.split(r"[/／>＞\\]", area or "") if p.strip()]
    if not parts:
        return []
    if mode == "root":
        return [parts[0]]
    if mode == "full":
        return ["/".join(parts)]
    if mode == "both":
        return [parts[-1]] if len(parts) == 1 else [parts[-1], parts[0]]
    return [parts[-1]]                             # leaf


def classify(status):
    s = (status or "").strip().lower()
    if not s or s in ("--", "-", "未知"):
        return "undetected"
    if any(w in s for w in OFFLINE_WORDS):
        return "offline"
    if any(w in s for w in ONLINE_WORDS):
        return "online"
    return "undetected"


def parse_int(v):
    """把带百分号/逗号的字符串转成整数"""
    if v is None:
        return 0
    s = str(v).strip().replace(",", "").replace("，", "")
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_rate(v):
    """解析在线率：84.60% -> 0.8460，空/无效返回 None"""
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s) / 100 if float(s) > 1 else float(s)
    except ValueError:
        return None


def is_aggregated_csv(colmap):
    """判断 CSV 是否已经是区域汇总表（有 总数/在线/离线/在线率）"""
    return (colmap.get("total") is not None and
            colmap.get("online") is not None and
            colmap.get("offline") is not None and
            colmap.get("rate") is not None)


def parse_aggregated(records, aliases, logger):
    """解析已按区域汇总的 CSV，每行直接对应一个区域"""
    buckets = OrderedDict()
    applied_aliases = {}
    for item in records:
        raw_area = (item.get("area") or "").strip()
        if not raw_area:
            continue
        norm_area = normalize_area(raw_area, aliases) if raw_area else raw_area
        if norm_area != raw_area:
            applied_aliases[raw_area] = norm_area
        area = norm_area
        total = parse_int(item.get("total"))
        online = parse_int(item.get("online"))
        offline = parse_int(item.get("offline"))
        undetected = parse_int(item.get("undetected"))
        whitelist = parse_int(item.get("whitelist"))
        rate = parse_rate(item.get("rate"))

        # 如果提供了在线率，优先信任；否则按在线/总数计算
        if rate is None and total > 0:
            rate = online / total

        buckets[area] = {
            "total": total,
            "online": online,
            "offline": offline,
            "undetected": undetected,
            "whitelist": whitelist,
            "rate": rate,
            "offline_names": [],
            "reasons": {},
        }

    if applied_aliases:
        for raw, norm in sorted(applied_aliases.items()):
            logger.info("位置别名: %s -> %s", raw, norm)
    return buckets


def aggregate(records, area_mode, logger, aliases=None):
    """按区域聚合，返回 OrderedDict[区域] = 统计字典"""
    aliases = aliases or {}
    buckets = OrderedDict()
    no_area = 0
    applied_aliases = {}  # raw -> normalized，用于日志
    for item in records:
        if not (item.get("name") or item.get("status")):
            continue
        raw_area = item.get("area", "")
        norm_area = normalize_area(raw_area, aliases) if raw_area else raw_area
        if norm_area != raw_area:
            applied_aliases[raw_area] = norm_area
        areas = split_area(norm_area, area_mode)
        if not areas:
            no_area += 1
            areas = ["未分配区域"]
        state = classify(item.get("status"))
        for area in areas:
            b = buckets.setdefault(area, {
                "total": 0, "online": 0, "offline": 0, "undetected": 0,
                "offline_names": [], "reasons": {},
            })
            b["total"] += 1
            b[state] += 1
            if state == "offline":
                if item.get("name"):
                    b["offline_names"].append(item["name"])
                reason = item.get("reason") or "未标注原因"
                b["reasons"][reason] = b["reasons"].get(reason, 0) + 1

    if applied_aliases:
        for raw, norm in sorted(applied_aliases.items()):
            logger.info("位置别名: %s -> %s", raw, norm)
    if no_area:
        logger.warning("%d 行缺少区域字段，已归入「未分配区域」", no_area)
    return buckets


def pick_timestamp(records, override, logger):
    """巡检时间：优先命令行，其次 CSV 巡检时间列最大值，最后当前时间"""
    if override:
        return override
    stamps = []
    for item in records:
        v = (item.get("checked_at") or "").strip()
        if not v:
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                stamps.append(datetime.strptime(v, fmt))
                break
            except ValueError:
                continue
    if stamps:
        return max(stamps).strftime("%Y-%m-%d %H:%M")
    logger.warning("CSV 未提供可解析的巡检时间，使用当前时间")
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def build_status_detail(stat):
    """拼成后端 _parse_status_to_metrics 认得的 'key: value; key: value'"""
    total = stat.get("total", 0)
    online = stat.get("online", 0)
    offline = stat.get("offline", 0)
    # 汇总 CSV 已提供在线率时直接采用，否则按在线/总数计算
    rate = stat.get("rate")
    if rate is None:
        rate = (online / total * 100) if total else 0.0
    elif rate <= 1.0:
        rate = rate * 100

    parts = [
        f"在线: {online}",
        f"离线: {offline}",
    ]
    if stat.get("undetected"):
        parts.append(f"未检测: {stat['undetected']}")
    if stat.get("whitelist"):
        parts.append(f"白名单: {stat['whitelist']}")
    parts.append(f"在线率: {rate:.2f}%")
    return "; ".join(parts), total, online, offline, rate


def build_notes(stat, max_names=5):
    if not stat["offline_names"]:
        return ""
    names = stat["offline_names"][:max_names]
    tail = f" 等 {len(stat['offline_names'])} 台" if len(stat["offline_names"]) > max_names else ""
    reason = "，".join(f"{k}×{v}" for k, v in sorted(
        stat["reasons"].items(), key=lambda x: -x[1])[:3])
    note = "离线: " + "、".join(names) + tail
    return f"{note}；原因: {reason}" if reason else note


def guess_result(rate, offline):
    """脚本侧初判，后端有阈值配置时会覆盖"""
    if rate < 90:
        return "异常"
    if offline > 0 or rate < 100:
        return "需关注"
    return "正常"


# ---------------------------------------------------------------------------
# 写入 IV
# ---------------------------------------------------------------------------

class IVClient:
    def __init__(self, base_url, username, password, logger):
        self.base = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.logger = logger
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _request(self, path, payload=None, method=None):
        url = urljoin(self.base, path)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, method=method or ("POST" if data else "GET"),
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
        with self.opener.open(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def login(self):
        if not self.password:
            self.logger.warning("未配置 IV_PASSWORD，若系统已开启登录会返回 401")
            return False
        body = {"password": self.password}
        if self.username:
            body["username"] = self.username
        try:
            self._request("api/login", body)
            self.logger.info("登录成功")
            return True
        except HTTPError as e:
            self.logger.error("登录失败 [%d]: %s", e.code, e.read().decode("utf-8", "replace")[:200])
            return False
        except URLError as e:
            self.logger.error("IV 不可达 %s: %s", self.base, e.reason)
            return False

    def list_objects(self):
        try:
            data = self._request("api/objects/list")
            return data if isinstance(data, list) else data.get("objects", [])
        except Exception as e:
            self.logger.warning("获取对象列表失败（不影响导入）: %s", e)
            return []

    def import_records(self, records):
        payload = {"records": records}
        if self.password:
            payload["password"] = self.password
            if self.username:
                payload["username"] = self.username
        return self._request("api/records/import", payload)

    def get_global_vars(self):
        try:
            return self._request("api/global-vars")
        except Exception as e:
            self.logger.warning("通过 API 获取全局变量失败: %s", e)
            return {}


def match_existing(area, objects):
    """本地预判会命中哪个巡检对象，逻辑对齐后端 _match_object_by_location。
    得分 > 0 才算命中；否则返回 None（该区域在 IV 中不存在）。"""
    best, best_score = None, 0
    for obj in objects:
        loc = (obj.get("location") or "").lower()
        a = area.lower()
        score = 0
        if loc and loc == a:
            score = 30
        elif loc and a in loc:
            score = 20
        elif loc and loc in a:
            score = 15
        if score > best_score:
            best, best_score = obj, score
    return best if best_score > 0 else None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    cfg = load_config()
    p = argparse.ArgumentParser(
        description="把监控点在线状态 CSV（明细或已汇总）导入 Inspection Visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python csv_to_iv.py -f 在线状态_明细.csv --dry-run
  python csv_to_iv.py -f 在线状态_明细.csv --area-mode both
  python csv_to_iv.py -f 在线状态_汇总.csv --dry-run
  python csv_to_iv.py -f 在线状态.csv --timestamp "2026-08-07 10:30"
""")
    p.add_argument("-f", "--csv", required=True, help="CSV 文件路径")
    p.add_argument("--iv-url", default=cfg["iv_url"], help="IV 地址")
    p.add_argument("--password", default=cfg["iv_password"], help="登录密码")
    p.add_argument("--username", default=cfg["iv_username"], help="登录用户名（留空用 APP_PASSWORD）")
    p.add_argument("--inspector", default=cfg["inspector_name"], help="巡检人名称")
    p.add_argument("--area-mode", default=cfg["area_mode"],
                   choices=["leaf", "root", "full", "both"],
                   help="区域聚合粒度：leaf=末级(默认) root=顶级 full=完整路径 both=末级+顶级")
    p.add_argument("--timestamp", default="", help="覆盖巡检时间，格式 YYYY-MM-DD HH:MM")
    p.add_argument("--min-total", type=int, default=1, help="区域设备数低于该值则跳过")
    p.add_argument("--allow-create", action="store_true",
                   help="允许为 CSV 中 IV 没有对应对象的区域自动新建巡检对象。"
                        "（默认关闭：仅匹配已有区域，未匹配的区域直接跳过）")
    p.add_argument("--dry-run", action="store_true", help="只预览聚合结果，不写库")
    p.add_argument("--log-level", default=cfg["log_level"])
    args = p.parse_args()

    logger = setup_logging(args.log_level, args.dry_run)

    header, colmap, rows = read_csv_rows(args.csv)
    logger.info("读取 %s，共 %d 行", args.csv, len(rows))

    # 判断是明细 CSV 还是已汇总 CSV
    aggregated = is_aggregated_csv(colmap)
    if aggregated:
        logger.info("检测到已汇总 CSV：一行即一个区域，直接透传指标")
        missing = [k for k in ("area", "total", "online", "offline", "rate") if colmap.get(k) is None]
        if missing:
            logger.error("汇总 CSV 缺少必要列: %s（现有表头: %s）", missing, header)
            return 1
    else:
        missing = [k for k in ("area", "status") if colmap.get(k) is None]
        if missing:
            logger.error("明细 CSV 缺少必要列: %s（现有表头: %s）", missing, header)
            return 1
    if colmap.get("checked_at") is None:
        logger.warning("未找到「巡检时间」列，将使用当前时间")

    # 先登录并拉取对象列表 + 服务端全局变量（位置别名）
    client = IVClient(args.iv_url, args.username, args.password, logger)
    objects = []
    if not args.dry_run or args.password:
        if client.login():
            objects = client.list_objects()

    # 加载位置别名：文件兜底；若能从 API 拿到则优先用服务端配置
    aliases = load_global_aliases(logger)
    if objects:
        api_vars = client.get_global_vars()
        api_aliases = api_vars.get("location_aliases", {})
        if api_aliases:
            logger.info("使用服务端 location_aliases（%d 条）", len(api_aliases))
            aliases = api_aliases

    stamp = pick_timestamp(rows, args.timestamp, logger)
    if aggregated:
        buckets = parse_aggregated(rows, aliases, logger)
    else:
        buckets = aggregate(rows, args.area_mode, logger, aliases)
    if not buckets:
        logger.error("没有聚合出任何区域数据")
        return 1

    # 明细 CSV 才需要警告「仅导出离线设备」；汇总 CSV 自带在线数
    if not aggregated:
        total_online = sum(b["online"] for b in buckets.values())
        if total_online == 0:
            logger.warning("CSV 中没有任何「在线」行，可能是仅导出离线设备。"
                           "此时在线率会算成 0%%，建议导出全量后再跑。")

    records, preview, skipped = [], [], []
    # 仅匹配已有区域：若拿不到 IV 对象列表，则无法匹配，给出提示后按跳过处理
    if not objects and not args.allow_create:
        logger.warning("未获取到 IV 对象列表，仅匹配模式下所有区域都将被跳过；"
                       "如需为未匹配区域新建对象请加 --allow-create")

    for area, stat in buckets.items():
        if stat["total"] < args.min_total:
            continue
        hit = match_existing(area, objects) if objects else None
        if hit is None and not args.allow_create:
            skipped.append(area)
            logger.warning("跳过区域「%s」：IV 中无匹配对象（如需新建请加 --allow-create）", area)
            continue
        detail, total, online, offline, rate = build_status_detail(stat)
        preview.append((area, total, online, offline, rate,
                        hit.get("location") if hit else "将新建"))
        records.append({
            "point_name": area,
            "object_name": area,
            "location": area,
            "timestamp": stamp,
            "result": guess_result(rate, offline),
            "status_detail": detail,
            "inspector_name": args.inspector,
            "notes": build_notes(stat),
        })

    mode_tag = "仅匹配已有区域" if not args.allow_create else "允许新建未匹配区域"
    agg_tag = "已汇总" if aggregated else f"聚合粒度: {args.area_mode}"
    print(f"\n巡检时间: {stamp}   {agg_tag}   匹配: {len(records)}  "
          f"跳过: {len(skipped)}   [{mode_tag}]")
    print("-" * 78)
    print(f"{'区域':<16}{'总数':>7}{'在线':>7}{'离线':>7}{'在线率':>10}  匹配对象")
    print("-" * 78)
    for area, total, online, offline, rate, hit in preview:
        print(f"{area:<16}{total:>7}{online:>7}{offline:>7}{rate:>9.2f}%  {hit}")
    if skipped:
        print("-" * 78)
        print("跳过(无匹配): " + "、".join(skipped))
    print("-" * 78)

    if args.dry_run:
        logger.info("dry-run 结束，未写入数据库")
        return 0

    try:
        resp = client.import_records(records)
    except HTTPError as e:
        logger.error("导入失败 [%d]: %s", e.code, e.read().decode("utf-8", "replace")[:300])
        return 1
    except URLError as e:
        logger.error("IV 不可达: %s", e.reason)
        return 1

    if resp.get("error"):
        logger.error("导入失败: %s", resp["error"])
        return 1
    logger.info("导入完成: imported=%s created=%s skipped=%s",
                resp.get("imported"), resp.get("created"), resp.get("skipped"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
