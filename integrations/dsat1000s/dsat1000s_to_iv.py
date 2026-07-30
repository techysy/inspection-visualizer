#!/usr/bin/env python3
"""
DS-AT1000S → Inspection Visualizer 自动巡检集成脚本

通过海康 ISAPI 协议采集 DS-AT1000S 智能分析存储服务器的硬件/存储/网络状态，
自动写入 Inspection Visualizer 的巡检记录系统。

用法:
    python dsat1000s_to_iv.py              # 正式写入 IV
    python dsat1000s_to_iv.py --dry-run    # 仅打印不写入
    python dsat1000s_to_iv.py --help       # 帮助

配置:
    1. 复制 .env.example 为 .env
    2. 填写 DEVICE_HOST / DEVICE_PASS / IV_URL 等参数
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def load_config():
    """从 .env 文件加载配置，支持命令行覆盖"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    os.environ.setdefault(k, v)

    return {
        "device_host": os.environ.get("DEVICE_HOST", "192.168.1.100"),
        "device_user": os.environ.get("DEVICE_USER", "admin"),
        "device_pass": os.environ.get("DEVICE_PASS", ""),
        "iv_url": os.environ.get("IV_URL", "http://127.0.0.1:5001"),
        "object_name": os.environ.get("IV_OBJECT_NAME", "DS-AT1000S 视频存储服务器"),
        "inspector_name": os.environ.get("IV_INSPECTOR_NAME", "Hermes 自动巡检"),
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
    }


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def setup_logging(level_name: str, dry_run: bool):
    prefix = "[DRY-RUN] " if dry_run else ""
    logger = logging.getLogger("dsat1000s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        f"{prefix}%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    return logger


# ---------------------------------------------------------------------------
# ISAPI 客户端
# ---------------------------------------------------------------------------

class ISAPIClient:
    """海康 ISAPI 协议 HTTP 客户端（Basic Auth）"""

    def __init__(self, host: str, user: str, password: str, logger: logging.Logger):
        self.base_url = f"http://{host}"
        auth_str = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {auth_str}",
            "Accept": "application/xml",
        }
        self.log = logger
        self.host = host

    def get(self, path: str) -> str | None:
        """GET ISAPI 接口，返回 XML 文本"""
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        req = Request(url, headers=self.headers)
        try:
            with urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                self.log.debug("ISAPI 200 %s (%d bytes)", url, len(body))
                return body
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            self.log.warning("ISAPI %d %s: %s", e.code, url, detail)
            return None
        except URLError as e:
            self.log.error("ISAPI 不可达 %s: %s", url, e.reason)
            return None
        except OSError as e:
            self.log.error("ISAPI 网络错误 %s: %s", url, e)
            return None

    def is_online(self) -> bool:
        """快速检测设备是否在线"""
        return self.get("/ISAPI/System/deviceInfo") is not None


class XMLParser:
    """安全提取 XML 字段"""

    @staticmethod
    def text(root: ET.Element | None, xpath: str, default: str = "N/A") -> str:
        if root is None:
            return default
        el = root.find(xpath)
        return el.text.strip() if el is not None and el.text else default

    @staticmethod
    def all_texts(root: ET.Element | None, xpath: str) -> list[str]:
        if root is None:
            return []
        return [el.text.strip() for el in root.findall(xpath) if el.text]


# ---------------------------------------------------------------------------
# 数据采集
# ---------------------------------------------------------------------------

def collect_device_info(client: ISAPIClient) -> dict:
    """采集设备基本信息"""
    xml = client.get("/ISAPI/System/deviceInfo")
    if not xml:
        return {}
    root = ET.fromstring(xml)
    return {
        "deviceName": XMLParser.text(root, "deviceName"),
        "model": XMLParser.text(root, "model"),
        "serialNumber": XMLParser.text(root, "serialNumber"),
        "firmwareVersion": XMLParser.text(root, "firmwareVersion"),
        "firmwareReleasedDate": XMLParser.text(root, "firmwareReleasedDate"),
    }


def collect_device_status(client: ISAPIClient) -> dict:
    """采集设备运行状态（CPU/内存）"""
    xml = client.get("/ISAPI/System/status")
    if not xml:
        return {}
    root = ET.fromstring(xml)
    st = root.find("status")
    if st is None:
        return {}
    return {
        "cpuUtilization": XMLParser.text(st, "cpuUtilization", "0"),
        "memoryUtilization": XMLParser.text(st, "memoryUtilization", "0"),
    }


def collect_storage_info(client: ISAPIClient) -> dict:
    """采集存储信息（RAID/硬盘/存储池）"""
    xml = client.get("/ISAPI/ContentMgmt/Storage")
    if not xml:
        return {}
    root = ET.fromstring(xml)
    info = {}

    # 硬盘
    for hdd in root.findall(".//hardDisk"):
        hdd_id = XMLParser.text(hdd, "id", "?")
        status = XMLParser.text(hdd, "status", "?")
        cap = XMLParser.text(hdd, "capacity", "?")
        info[f"硬盘{hdd_id}"] = f"{status} - {cap}GB"

    # RAID
    raid_el = root.find(".//raidStatus")
    if raid_el is not None:
        info["RAID状态"] = raid_el.text.strip() if raid_el.text else "N/A"
    else:
        # 部分固件用 <raid> 标签
        raid_el2 = root.find(".//raid")
        if raid_el2 is not None:
            info["RAID状态"] = raid_el2.text.strip() if raid_el2.text else "N/A"

    # 存储池容量（递归查找 volume 下的容量字段）
    for volume in root.findall(".//volume"):
        total = XMLParser.text(volume, "totalCapacity", "")
        used = XMLParser.text(volume, "usedCapacity", "")
        if total:
            info["存储总容量"] = f"{total} GB"
        if used:
            info["存储已用"] = f"{used} GB"

    return info


def collect_network_info(client: ISAPIClient) -> dict:
    """采集网络接口状态"""
    xml = client.get("/ISAPI/System/Network/interfaces")
    if not xml:
        return {}
    root = ET.fromstring(xml)
    info = {}
    for i, iface in enumerate(root.findall("NetworkInterface"), 1):
        name = XMLParser.text(iface, "id", f"eth{i}")
        ip = XMLParser.text(iface, "IPAddress", "?")
        link = XMLParser.text(iface, "linkStatus", "?")
        info[f"网口{name}({ip})"] = link
    return info


# ---------------------------------------------------------------------------
# 数据整合
# ---------------------------------------------------------------------------

def build_status_detail(all_data: dict) -> str:
    """拼接为 IV 认可的 status_detail 格式: key: value; key2: value2"""
    parts = []

    di = all_data.get("device_info", {})
    if di.get("model"):
        parts.append(f"型号: {di['model']}")
    if di.get("firmwareVersion"):
        parts.append(f"固件: {di['firmwareVersion']}")

    ds = all_data.get("device_status", {})
    parts.append(f"CPU占用: {ds.get('cpuUtilization', '?')}%")
    parts.append(f"内存占用: {ds.get('memoryUtilization', '?')}%")

    si = all_data.get("storage_info", {})
    for k in sorted(si.keys()):
        parts.append(f"{k}: {si[k]}")

    ni = all_data.get("network_info", {})
    for k in sorted(ni.keys()):
        parts.append(f"{k}: {ni[k]}")

    return "; ".join(parts)


def determine_result(all_data: dict, logger: logging.Logger) -> str:
    """自动判定巡检结果"""
    si = all_data.get("storage_info", {})
    ds = all_data.get("device_status", {})

    # RAID 降级/故障 → 异常
    raid = si.get("RAID状态", "").lower()
    if any(kw in raid for kw in ("degrade", "failed", "降级", "故障", "error", "broken")):
        logger.warning("RAID 异常: %s", raid)
        return "异常"

    # 硬盘故障 → 异常
    for k, v in si.items():
        if k.startswith("硬盘"):
            vl = v.lower()
            if any(kw in vl for kw in ("fault", "failed", "error", "故障", "错误", "坏道")):
                logger.warning("硬盘异常: %s = %s", k, v)
                return "异常"
            if any(kw in vl for kw in ("warning", "warn", "警告")):
                logger.warning("硬盘需关注: %s = %s", k, v)
                return "需关注"

    # CPU/内存过高
    try:
        cpu = float(ds.get("cpuUtilization", "0"))
        mem = float(ds.get("memoryUtilization", "0"))
        if cpu > 90 or mem > 90:
            logger.warning("资源占用过高: CPU=%s%%, 内存=%s%%", cpu, mem)
            return "异常"
        if cpu > 80 or mem > 80:
            logger.info("资源占用偏高: CPU=%s%%, 内存=%s%%", cpu, mem)
            return "需关注"
    except ValueError:
        pass

    return "正常"


# ---------------------------------------------------------------------------
# Inspection Visualizer 客户端
# ---------------------------------------------------------------------------

def post_to_iv(
    iv_url: str,
    status_detail: str,
    result: str,
    object_name: str,
    inspector_name: str,
    logger: logging.Logger,
) -> bool:
    """写入 Inspection Visualizer"""
    payload = {
        "records": [
            {
                "point_name": object_name,
                "object_name": object_name,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "result": result,
                "status_detail": status_detail,
                "inspector_name": inspector_name,
            }
        ]
    }

    url = urljoin(iv_url.rstrip("/") + "/", "api/records/import")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            logger.info("IV 导入成功: imported=%s skipped=%s created=%s",
                        resp_data.get("imported"), resp_data.get("skipped"), resp_data.get("created"))
            return True
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        logger.error("IV 导入失败 [%d]: %s", e.code, detail)
        return False
    except URLError as e:
        logger.error("IV 不可达 %s: %s", url, e.reason)
        return False
    except Exception as e:
        logger.error("IV 导入异常: %s", e)
        return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DS-AT1000S → Inspection Visualizer 自动巡检",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="配置: 同目录下 .env 文件或环境变量",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印采集结果，不写入 IV")
    parser.add_argument("--debug", action="store_true",
                        help="启用 DEBUG 级别日志")
    args = parser.parse_args()

    # 加载配置
    cfg = load_config()
    log_level = "DEBUG" if args.debug else cfg["log_level"]
    logger = setup_logging(log_level, args.dry_run)
    dry_run = args.dry_run

    logger.info("=" * 50)
    logger.info("DS-AT1000S 自动巡检 开始")
    logger.info("目标设备: %s", cfg["device_host"])
    logger.info("IV 地址: %s", cfg["iv_url"])
    logger.info("巡检对象: %s", cfg["object_name"])
    if dry_run:
        logger.info("★ DRY-RUN 模式 — 不会写入 IV")
    logger.info("=" * 50)

    # 检查配置
    if not cfg["device_pass"]:
        logger.error("未配置 DEVICE_PASS，请在 .env 中填写 ISAPI 密码")
        sys.exit(1)

    # 连接设备
    client = ISAPIClient(cfg["device_host"], cfg["device_user"],
                         cfg["device_pass"], logger)

    if not client.is_online():
        logger.error("设备 %s 不可达，跳过本次巡检", cfg["device_host"])
        sys.exit(1)
    logger.info("设备在线 ✓")

    # 采集
    logger.info("采集设备信息...")
    di = collect_device_info(client)
    if di:
        logger.info("  型号: %s | 固件: %s", di.get("model", "?"), di.get("firmwareVersion", "?"))

    logger.info("采集运行状态...")
    ds = collect_device_status(client)

    logger.info("采集存储信息...")
    si = collect_storage_info(client)
    raid = si.get("RAID状态", "N/A")
    hdd_count = sum(1 for k in si if k.startswith("硬盘"))
    logger.info("  RAID: %s | 硬盘数: %d", raid, hdd_count)

    logger.info("采集网络状态...")
    ni = collect_network_info(client)

    # 整合
    all_data = {
        "device_info": di,
        "device_status": ds,
        "storage_info": si,
        "network_info": ni,
    }

    status_detail = build_status_detail(all_data)
    result = determine_result(all_data, logger)

    logger.info("-" * 50)
    logger.info("结果判定: %s", result)

    # 逐行打印状态详情（方便阅读）
    for part in status_detail.split("; "):
        logger.info("  %s", part)

    # 写入 IV
    if dry_run:
        logger.info("DRY-RUN: 跳过 IV 写入 ✓")
    else:
        ok = post_to_iv(
            cfg["iv_url"], status_detail, result,
            cfg["object_name"], cfg["inspector_name"],
            logger,
        )
        if ok:
            logger.info("✅ 巡检完成，记录已写入 IV")
        else:
            logger.error("❌ 巡检完成，但 IV 写入失败")
            sys.exit(1)

    logger.info("=" * 50)


if __name__ == "__main__":
    main()
