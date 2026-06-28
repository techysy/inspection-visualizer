import io
import re
import base64
import tempfile
from datetime import datetime
from pathlib import Path
import json
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, Response
from PIL import Image
from models.inspection import SessionLocal, InspectionObject, InspectionRecord, Inspector, ObjectMetric

OCR_CONFIG_PATH = Path(__file__).parent / 'ocr_config.json'
DASHBOARD_TYPES_PATH = Path(__file__).parent / 'dashboard_types.json'

_default_ocr_config = {
    "text_score": 0.5,
    "use_det": True,
    "use_cls": True,
    "use_rec": True,
    "min_height": 30,
    "max_side_len": 2000,
    "ignore_top": 0,
    "ignore_bottom": 0,
}


def _load_ocr_config():
    if OCR_CONFIG_PATH.exists():
        try:
            with open(OCR_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return _default_ocr_config.copy()


def _build_ocr_engine(config=None):
    if config is None:
        config = _load_ocr_config()
    try:
        from rapidocr_onnxruntime import RapidOCR
        kwargs = {}
        if 'text_score' in config:
            kwargs['text_score'] = config['text_score']
        if 'use_det' in config:
            kwargs['use_det'] = config['use_det']
        if 'use_cls' in config:
            kwargs['use_cls'] = config['use_cls']
        if 'use_rec' in config:
            kwargs['use_rec'] = config['use_rec']
        return RapidOCR(**kwargs)
    except ImportError:
        return None


ocr_engine = _build_ocr_engine()


def _load_dashboard_types():
    if DASHBOARD_TYPES_PATH.exists():
        try:
            with open(DASHBOARD_TYPES_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('types', [])
        except Exception:
            pass
    return []


def _save_dashboard_types(types_list):
    with open(DASHBOARD_TYPES_PATH, 'w', encoding='utf-8') as f:
        json.dump({'types': types_list}, f, ensure_ascii=False, indent=2)


def _sync_dashboard_type_from_object(obj, metrics):
    """根据巡检对象及其指标自动创建/更新仪表盘类型"""
    types_list = _load_dashboard_types()
    type_id = f'obj_{obj.id}'

    existing = next((t for t in types_list if t['id'] == type_id), None)

    labels = {}
    for m in metrics:
        labels[m.name] = m.key

    type_data = {
        'id': type_id,
        'name': obj.name,
        'description': obj.description or f'{obj.name} 仪表盘',
        'detect_keywords': [obj.name],
        'labels': labels,
        'extra_labels': [],
        'result_rules': {},
        'number_before_label': False,
    }

    if existing:
        existing.update(type_data)
    else:
        types_list.append(type_data)

    _save_dashboard_types(types_list)
    return type_data


main = Blueprint('main', __name__)

# 设备类型关键词
DEVICE_TYPES = {
    '服务器': ['服务器', 'server', 'srv', '主机'],
    '网络设备': ['交换机', '路由器', '防火墙', 'switch', 'router', 'firewall', '网络设备'],
    '存储': ['存储', 'storage', '磁盘阵列', 'nas', 'san'],
    'UPS': ['ups', '不间断电源', '电源'],
    '空调': ['空调', '精密空调', '制冷'],
    '监控': ['监控', '摄像头', 'camera', 'cctv'],
}

# 巡检结果关键词
RESULT_KEYWORDS = {
    '正常': ['正常', '良好', 'ok', 'good', '合格', 'pass'],
    '异常': ['异常', '故障', 'error', 'fail', '不合格', '告警', '报警'],
    '需关注': ['需关注', '注意', 'warning', 'warn', '待处理'],
}


def _parse_status_to_metrics(status_detail):
    """将 status_detail 字符串解析为结构化指标 dict"""
    metrics = {}
    if not status_detail:
        return metrics
    for part in re.split(r'[;；]\s*', status_detail):
        m = re.match(r'^(.+?):\s*(.+)$', part.strip())
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            metrics[key] = val
    return metrics


def _check_metrics_thresholds(metrics, object_id, session):
    """根据指标阈值配置判断巡检结果"""
    metric_configs = session.query(ObjectMetric).filter_by(object_id=object_id).all()
    if not metric_configs:
        return None
    
    worst_result = '正常'
    has_threshold = False
    for mc in metric_configs:
        if mc.error_threshold is None and mc.warn_threshold is None:
            continue
        
        has_threshold = True
        
        # 从 metrics dict 中查找值（按 name 或 key）
        val_str = metrics.get(mc.name) or metrics.get(mc.key)
        if val_str is None:
            continue
        
        # 提取数值
        val_match = re.search(r'([\d.]+)', str(val_str))
        if not val_match:
            continue
        val = float(val_match.group(1))
        
        is_gt = mc.threshold_direction == 'gt'
        
        if mc.error_threshold is not None:
            if (is_gt and val > mc.error_threshold) or (not is_gt and val < mc.error_threshold):
                return '异常'
        
        if mc.warn_threshold is not None:
            if (is_gt and val > mc.warn_threshold) or (not is_gt and val < mc.warn_threshold):
                worst_result = '需关注'
    
    return worst_result if has_threshold else None


def _extract_location_from_lines(lines):
    """从行列表中提取位置信息"""
    skip_words = ['监控点总数', '在线', '离线', '未检测', '监控点在线率', '默认区域设置', 'admin',
                  '车辆总数', '在线车辆', '今日上线', '报警车辆', '全部车辆', '全部状态',
                  '工牌', '全部', '未用', '请输入']
    
    # 优先从前面的行中提取位置（左上角区域）
    for i, line in enumerate(lines[:5]):  # 只检查前5行
        line = line.strip()
        if not line or len(line) < 2:
            continue
        if any(sw in line for sw in skip_words):
            continue
        if re.match(r'^\d+$', line):  # 纯数字
            continue
        if re.match(r'^\d{1,3}\.\d{1,2}%$', line):  # 百分比
            continue
        # 可能是区域名称（放宽正则，允许空格和常见标点）
        if re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_\s,，。、]{2,30}$', line):
            return line
    
    # 如果前面没有找到，尝试所有行
    for line in lines:
        line = line.strip()
        if not line or len(line) < 2:
            continue
        if any(sw in line for sw in skip_words):
            continue
        if re.match(r'^\d+$', line):  # 纯数字
            continue
        if re.match(r'^\d{1,3}\.\d{1,2}%$', line):  # 百分比
            continue
        # 可能是区域名称（放宽正则）
        if re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_\s,，。、]{2,30}$', line):
            return line
    
    return ''


# 位置名称映射（OCR识别结果 → 标准名称）
LOCATION_ALIAS = {
    '中江县综合行政执法局': '城区',
    '中江县': '城区',
}


def normalize_location(name):
    """标准化位置名称"""
    if not name:
        return name
    for alias, standard in LOCATION_ALIAS.items():
        if alias in name:
            return standard
    return name


def parse_inspection_form(ocr_result):
    """解析巡检表单/仪表盘 OCR 结果"""
    if not ocr_result:
        return []

    lines = []
    for item in ocr_result:
        if item and len(item) >= 2:
            text = item[1]
            lines.append(text)

    all_text = '\n'.join(lines)

    # OCR 原始输出日志
    print('=== OCR LINES ===')
    for i, line in enumerate(lines):
        print(f'  [{i}] {repr(line)}')
    print('=== END ===')

    # 尝试解析仪表盘格式（监控系统截图）
    dashboard_result = parse_dashboard_screenshot(all_text, lines)
    if dashboard_result:
        return [dashboard_result]

    # 传统表单格式解析
    return parse_traditional_form(lines)


def parse_dashboard_screenshot(all_text, lines):
    """解析仪表盘截图（使用可配置的仪表盘类型规则）"""
    print(f'  PARSE: all_text={repr(all_text)}')

    dashboard_types = _load_dashboard_types()
    matched_type = None

    for dtype in dashboard_types:
        keywords = dtype.get('detect_keywords', [])
        if any(kw in all_text for kw in keywords):
            matched_type = dtype
            print(f'  PARSE: 检测到{dtype["name"]}仪表盘 (关键词: {keywords})')
            break

    if not matched_type:
        print('  PARSE: 未匹配到任何仪表盘类型')
        return None

    label_map = matched_type.get('labels', {})
    number_before_label = matched_type.get('number_before_label', False)
    region_name = ''
    online_rate = ''
    metrics = {}

    # 逐行匹配（使用队列处理连续标签无数字的情况）
    name_from_first_line = matched_type.get('name_from_first_line', False)
    pending_labels = []
    unmatched_lines = [] if name_from_first_line else None
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 1) 纯整数行 → 归给第一个等待数字的标签
        if pending_labels and re.match(r'^\d+$', line):
            num = int(line)
            label = pending_labels.pop(0)
            metrics[label] = num
            print(f'  PARSE: 纯数字 {num} -> {label}')
            continue

        # 2) 匹配 "位置名（在线/总数）" 格式
        m = re.match(r'^(.+?)\s*[（(]\s*(\d+)\s*/\s*(\d+)\s*[）)]$', line)
        if m:
            region_name = m.group(1).strip()
            online_val = int(m.group(2))
            total_val = int(m.group(3))
            metrics['online'] = online_val
            metrics['total'] = total_val
            print(f'  PARSE: 位置格式 {region_name} 在线={online_val} 总数={total_val}')
            pending_labels = []
            continue

        # 3) 匹配标签行（在行内查找所有出现的标签-数值对）
        sorted_labels = sorted(label_map.keys(), key=len, reverse=True)
        line_matched = False
        for label in sorted_labels:
            # 构建搜索模式：标签后跟可选分隔符 + 数值 + 可选单位
            search_pattern = rf'{re.escape(label)}\s*[·.:：]?\s*([\d.]+)\s*([万亿]?)'
            if number_before_label:
                search_pattern = rf'([\d.]+)\s*([万亿]?)\s*[·.:：]?\s*{re.escape(label)}'
            for m in re.finditer(search_pattern, line):
                matched_label = label_map[label]
                raw = m.group(1)
                unit = m.group(2) if len(m.groups()) >= 2 else ''
                if unit == '万':
                    matched_val = int(float(raw) * 10000)
                elif unit == '亿':
                    matched_val = int(float(raw) * 100000000)
                else:
                    matched_val = int(float(raw))
                metrics[matched_label] = matched_val
                line_matched = True
                print(f'  PARSE: {matched_label}={matched_val}')

        if line_matched:
            pending_labels = []
            continue

        pending_labels = []
        if unmatched_lines is not None and len(line) >= 2 and not re.match(r'^\d+$', line):
            unmatched_lines.append(line)

    # 识别在线率百分比（如果有 extra_labels 包含"在线率"）
    extra_labels = matched_type.get('extra_labels', [])
    if '在线率' in extra_labels:
        rate_match = re.search(r'(\d{1,3}\.\d{1,2})%', all_text)
        if rate_match:
            online_rate = rate_match.group(0)

    # 交叉校验：用在线率修正OCR错位的数值
    if online_rate:
        rate_val = float(online_rate.replace('%', ''))
        known_total = metrics.get('total', 0)
        known_online = metrics.get('online', 0)
        known_offline = metrics.get('offline', 0)
        known_undetected = metrics.get('undetected', 0)
        if known_total > 0:
            expected_online = round(known_total * rate_val / 100)
            expected_offline = max(0, known_total - expected_online - known_undetected)
            print(f'  PARSE: 交叉校验 online {known_online}->{expected_online}, offline {known_offline}->{expected_offline}')
            metrics['online'] = expected_online
            metrics['offline'] = expected_offline
        elif known_online > 0 and rate_val == 100.0 and known_offline > 0:
            print(f'  PARSE: 在线率100%, 修正 offline {known_offline}->0')
            metrics['offline'] = 0

    # 识别区域名称
    if not region_name:
        region_name = _extract_location_from_lines(lines)
    region_name = normalize_location(region_name)

    # 从OCR文本中提取截图日期
    screenshot_date = None
    time_patterns = [
        r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
    ]
    for tp in time_patterns:
        tm = re.search(tp, all_text)
        if tm:
            try:
                y, mo, d = int(tm.group(1)), int(tm.group(2)), int(tm.group(3))
                if 2020 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                    screenshot_date = f'{y}-{mo:02d}-{d:02d}'
                    print(f'  PARSE: 识别到截图日期 {screenshot_date}')
                    break
            except (ValueError, IndexError):
                pass

    if not metrics:
        return None

    # 构建状态详情
    reverse_label_map = {v: k for k, v in label_map.items()}
    status_detail_parts = []
    for key, val in metrics.items():
        label_name = reverse_label_map.get(key, key)
        status_detail_parts.append(f'{label_name}: {val}')
    if online_rate:
        status_detail_parts.append(f'在线率: {online_rate}')

    # 根据 result_rules 判断整体状态
    result = '正常'
    result_rules = matched_type.get('result_rules', {})
    for rule, outcome in result_rules.items():
        m = re.match(r'^(\w+)([><=]+)([\d.]+)$', rule)
        if not m:
            continue
        metric_key, op, threshold = m.group(1), m.group(2), float(m.group(3))
        val = metrics.get(metric_key, 0)
        if op == '>' and val > threshold:
            result = outcome
            break
        elif op == '<' and val < threshold:
            result = outcome
            break
        elif op == '>=' and val >= threshold:
            result = outcome
            break
        elif op == '<=' and val <= threshold:
            result = outcome
            break

    # 在线率特殊处理
    if online_rate and 'online_rate' in str(result_rules):
        rate_value = float(online_rate.replace('%', ''))
        for rule, outcome in result_rules.items():
            m = re.match(r'^online_rate([><=]+)([\d.]+)$', rule)
            if not m:
                continue
            op, threshold = m.group(1), float(m.group(2))
            if op == '<' and rate_value < threshold:
                result = outcome
                break
            elif op == '<=' and rate_value <= threshold:
                result = outcome
                break

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    timestamp = f'{screenshot_date} {now.split(" ")[1]}' if screenshot_date else now

    point_name = ''
    if name_from_first_line and unmatched_lines:
        point_name = unmatched_lines[0]
        print(f'  PARSE: 从首行提取名称: {point_name}')

    return {
        'point_name': point_name,
        'location': region_name,
        'result': result,
        'status_detail': '; '.join(status_detail_parts),
        'notes': '',
        'inspector': '',
        'timestamp': timestamp,
        'is_dashboard': True,
        'dashboard_type': matched_type['id'],
        'dashboard_type_name': matched_type['name'],
        'dashboard_category': matched_type.get('category', matched_type['name']),
    }


def parse_traditional_form(lines):
    """解析传统表单格式（兼容原有逻辑）"""
    results = []
    pending_object = ''
    pending_result = ''
    pending_status = ''
    pending_inspector = ''
    pending_time = None

    SKIP_PATTERNS = ['巡检表', '检查表', '签字', '日期', '备注', '说明', '注意事项']

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if any(kw in line for kw in SKIP_PATTERNS) and len(line) < 10:
            continue

        # 尝试识别时间
        time_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})[\sT]*(\d{1,2}:\d{1,2})?', line)
        if time_match:
            date_str = time_match.group(1)
            time_str = time_match.group(2) or '00:00'
            try:
                pending_time = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
            except ValueError:
                try:
                    pending_time = datetime.strptime(f'{date_str} {time_str}', '%Y/%m/%d %H:%M')
                except ValueError:
                    pass

        # 尝试识别巡检结果
        for result, keywords in RESULT_KEYWORDS.items():
            if any(kw in line.lower() for kw in keywords):
                pending_result = result
                break

        # 尝试识别设备类型
        device_type = None
        for dtype, keywords in DEVICE_TYPES.items():
            if any(kw in line.lower() for kw in keywords):
                device_type = dtype
                break

        # 尝试识别巡检对象名称（包含设备类型关键词或编号）
        has_object_keyword = any(kw in line.lower() for kw in ['服务器', '交换机', '路由器', 'ups', '空调', '监控', '机柜', '设备', 'server', 'switch', 'router'])
        has_number = re.search(r'[A-Za-z]*-\d+|\d+号|\d+号机柜', line)

        if has_object_keyword or has_number:
            pending_object = line

        # 尝试识别巡检人员（包含姓名特征）
        name_match = re.search(r'巡检人[：:]*\s*([^\s]+)', line)
        if name_match:
            pending_inspector = name_match.group(1)
        elif re.match(r'^[\u4e00-\u9fa5]{2,4}$', line) and not pending_inspector:
            # 可能是人名（2-4个汉字）
            pending_inspector = line

        # 状态详情（温度、负载、运行状态等）
        status_keywords = ['温度', '负载', '运行', '状态', 'cpu', '内存', '磁盘', '网络', '功率']
        if any(kw in line.lower() for kw in status_keywords):
            pending_status = line

        # 当收集到完整信息时，保存记录
        if pending_object and pending_result:
            results.append({
                'point_name': pending_object,
                'result': pending_result,
                'status_detail': pending_status,
                'inspector': pending_inspector,
                'timestamp': pending_time or datetime.now(),
            })
            pending_object = ''
            pending_result = ''
            pending_status = ''

    return results


@main.route('/')
def index():
    """首页：巡检对象列表"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).filter_by(status='active').all()
        # 获取每个对象的最近巡检记录
        object_data = []
        for obj in objects:
            latest_record = (
                session.query(InspectionRecord)
                .filter_by(object_id=obj.id)
                .order_by(InspectionRecord.timestamp.desc())
                .first()
            )
            object_data.append({
                'object': obj,
                'latest_record': latest_record,
            })
        return render_template('index.html', object_data=object_data)
    finally:
        session.close()


@main.route('/object/<int:object_id>')
def object_detail(object_id):
    """巡检对象详情页"""
    session = SessionLocal()
    try:
        obj = session.query(InspectionObject).filter_by(id=object_id).first()
        if not obj:
            return "巡检对象不存在", 404

        records = (
            session.query(InspectionRecord)
            .filter_by(object_id=object_id)
            .order_by(InspectionRecord.timestamp.desc())
            .all()
        )

        all_inspectors = session.query(Inspector).all()
        default_inspector = all_inspectors[0] if all_inspectors else None

        # 统计数据
        total_records = len(records)
        normal_count = sum(1 for r in records if r.result == '正常')
        abnormal_count = sum(1 for r in records if r.result == '异常')

        # 按结果分组，用于图表（同时间的记录加偏移避免重叠）
        result_timeline = {}
        ts_counter = {}
        for record in records:
            result_key = record.result
            if result_key not in result_timeline:
                result_timeline[result_key] = []
            ts_ms = int(record.timestamp.timestamp() * 1000)
            offset = ts_counter.get(ts_ms, 0)
            ts_counter[ts_ms] = offset + 1
            result_timeline[result_key].append({
                'x': ts_ms + offset * 60000,
                'y': 1 if record.result == '正常' else 0,
                'result': record.result,
                'inspector': record.inspector.name if record.inspector else (default_inspector.name if default_inspector else '未知'),
            })

        # 获取指标配置
        object_metrics = session.query(ObjectMetric).filter_by(object_id=object_id).order_by(ObjectMetric.sort_order).all()
        metrics_config = [
            {
                'id': m.id, 'key': m.key, 'name': m.name, 'unit': m.unit,
                'max_value': m.max_value, 'show_in_chart': m.show_in_chart,
                'warn_threshold': m.warn_threshold, 'error_threshold': m.error_threshold,
                'threshold_direction': m.threshold_direction
            }
            for m in object_metrics
        ]

        return render_template(
            'object_detail.html',
            object=obj,
            records=records,
            total_records=total_records,
            normal_count=normal_count,
            abnormal_count=abnormal_count,
            result_timeline=result_timeline,
            metrics_config=metrics_config
        )
    finally:
        session.close()


@main.route('/api/inspection_history/<int:object_id>')
def api_inspection_history(object_id):
    """巡检历史 API"""
    session = SessionLocal()
    try:
        records = (
            session.query(InspectionRecord)
            .filter_by(object_id=object_id)
            .order_by(InspectionRecord.timestamp.desc())
            .all()
        )

        all_inspectors = session.query(Inspector).all()

        data = [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'result': r.result,
                'status_detail': r.status_detail,
                'metrics': json.loads(r.metrics) if r.metrics else {},
                'notes': r.notes,
                'inspector': r.inspector.name if r.inspector else (all_inspectors[0].name if all_inspectors else '未知'),
            }
            for r in records
        ]

        return jsonify(data)
    finally:
        session.close()


@main.route('/api/inspection_history/delete/<int:record_id>', methods=['POST'])
def api_inspection_history_delete(record_id):
    """删除巡检记录"""
    session = SessionLocal()
    try:
        record = session.query(InspectionRecord).get(record_id)
        if not record:
            return jsonify({'error': '记录不存在'}), 404
        object_id = record.object_id
        session.delete(record)
        session.commit()
        return jsonify({'ok': True, 'object_id': object_id})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@main.route('/objects')
def objects():
    """巡检对象管理页面"""
    session = SessionLocal()
    try:
        object_list = session.query(InspectionObject).order_by(InspectionObject.location, InspectionObject.name).all()
        from datetime import timedelta
        for obj in object_list:
            if obj.created_at:
                obj.created_at = obj.created_at + timedelta(hours=8)
        return render_template('objects.html', objects=object_list)
    finally:
        session.close()


@main.route('/objects/add', methods=['POST'])
def object_add():
    """添加巡检对象"""
    name = request.form.get('name', '').strip()
    location = request.form.get('location', '').strip() or None
    device_type = request.form.get('device_type', '').strip() or None
    description = request.form.get('description', '').strip() or None

    if not name:
        flash('名称不能为空', 'danger')
        return redirect(url_for('main.objects'))

    session = SessionLocal()
    try:
        obj = InspectionObject(name=name, location=location, device_type=device_type, description=description)
        session.add(obj)
        session.commit()
        flash(f'巡检对象 "{name}" 添加成功', 'success')
    except Exception as e:
        session.rollback()
        flash(f'添加失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.objects'))


@main.route('/objects/edit/<int:object_id>', methods=['POST'])
def object_edit(object_id):
    """编辑巡检对象"""
    session = SessionLocal()
    try:
        obj = session.query(InspectionObject).get(object_id)
        if not obj:
            flash('巡检对象不存在', 'danger')
            return redirect(url_for('main.objects'))

        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip() or None
        device_type = request.form.get('device_type', '').strip() or None
        status = request.form.get('status', '').strip() or 'active'
        description = request.form.get('description', '').strip() or None

        if name:
            obj.name = name
        obj.location = location
        obj.device_type = device_type
        obj.status = status
        obj.description = description

        session.commit()
        flash(f'巡检对象 "{obj.name}" 已更新', 'success')
    except Exception as e:
        session.rollback()
        flash(f'更新失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.objects'))


@main.route('/objects/delete/<int:object_id>', methods=['POST'])
def object_delete(object_id):
    """删除巡检对象"""
    session = SessionLocal()
    try:
        obj = session.query(InspectionObject).get(object_id)
        if not obj:
            flash('巡检对象不存在', 'danger')
            return redirect(url_for('main.objects'))

        name = obj.name
        # 删除关联的巡检记录
        session.query(InspectionRecord).filter_by(object_id=obj.id).delete()
        session.delete(obj)
        session.commit()
        flash(f'巡检对象 "{name}" 已删除', 'success')
    except Exception as e:
        session.rollback()
        flash(f'删除失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.objects'))


@main.route('/objects/clone/<int:object_id>', methods=['POST'])
def object_clone(object_id):
    """复制巡检对象"""
    session = SessionLocal()
    try:
        src = session.query(InspectionObject).get(object_id)
        if not src:
            flash('巡检对象不存在', 'danger')
            return redirect(url_for('main.objects'))

        new_obj = InspectionObject(
            name=src.name,
            location='',
            device_type=src.device_type,
            description=src.description,
            status=src.status
        )
        session.add(new_obj)
        session.flush()

        # 复制指标配置
        src_metrics = session.query(ObjectMetric).filter_by(object_id=src.id).all()
        for m in src_metrics:
            new_m = ObjectMetric(
                object_id=new_obj.id,
                key=m.key,
                name=m.name,
                unit=m.unit,
                max_value=m.max_value,
                sort_order=m.sort_order,
                show_in_chart=m.show_in_chart,
                warn_threshold=m.warn_threshold,
                error_threshold=m.error_threshold,
                threshold_direction=m.threshold_direction
            )
            session.add(new_m)

        session.commit()
        flash(f'已复制 "{src.name}"，请修改位置', 'success')
    except Exception as e:
        session.rollback()
        flash(f'复制失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.objects'))


@main.route('/api/objects/list')
def api_objects_list():
    """巡检对象列表 API"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).filter_by(status='active').all()
        return jsonify([
            {
                'id': o.id,
                'name': o.name,
                'location': o.location,
                'device_type': o.device_type,
                'description': o.description
            }
            for o in objects
        ])
    finally:
        session.close()


@main.route('/api/points/list')
def api_points_list():
    """巡检点列表 API（兼容前端旧接口，实际返回巡检对象）"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).filter_by(status='active').all()
        return jsonify([
            {
                'id': o.id,
                'name': o.name,
                'location': o.location,
                'device_type': o.device_type,
                'description': o.description
            }
            for o in objects
        ])
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/metrics', methods=['GET'])
def api_object_metrics_list(object_id):
    """获取巡检对象的指标配置"""
    session = SessionLocal()
    try:
        metrics = session.query(ObjectMetric).filter_by(object_id=object_id).order_by(ObjectMetric.sort_order).all()
        return jsonify([
            {
                'id': m.id,
                'key': m.key,
                'name': m.name,
                'unit': m.unit,
                'max_value': m.max_value,
                'show_in_chart': m.show_in_chart,
                'sort_order': m.sort_order,
                'warn_threshold': m.warn_threshold,
                'error_threshold': m.error_threshold,
                'threshold_direction': m.threshold_direction,
            }
            for m in metrics
        ])
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/metrics', methods=['POST'])
def api_object_metrics_add(object_id):
    """添加指标配置"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效数据'}), 400
    key = data.get('key', '').strip()
    name = data.get('name', '').strip()
    unit = data.get('unit', '').strip()
    show_in_chart = data.get('show_in_chart', True)
    sort_order = data.get('sort_order', 0)
    max_value = data.get('max_value', 100)
    warn_threshold = data.get('warn_threshold')
    error_threshold = data.get('error_threshold')
    threshold_direction = data.get('threshold_direction', 'lt')
    if not key or not name:
        return jsonify({'error': 'key 和 name 不能为空'}), 400
    session = SessionLocal()
    try:
        metric = ObjectMetric(
            object_id=object_id, key=key, name=name,
            unit=unit, max_value=max_value, show_in_chart=show_in_chart, sort_order=sort_order,
            warn_threshold=warn_threshold, error_threshold=error_threshold, threshold_direction=threshold_direction
        )
        session.add(metric)
        session.commit()
        return jsonify({'id': metric.id, 'key': metric.key, 'name': metric.name,
                        'unit': metric.unit, 'max_value': metric.max_value, 'show_in_chart': metric.show_in_chart,
                        'warn_threshold': metric.warn_threshold, 'error_threshold': metric.error_threshold,
                        'threshold_direction': metric.threshold_direction})
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/metrics/<int:metric_id>', methods=['PUT'])
def api_object_metrics_update(object_id, metric_id):
    """更新指标配置"""
    data = request.get_json()
    session = SessionLocal()
    try:
        metric = session.query(ObjectMetric).filter_by(id=metric_id, object_id=object_id).first()
        if not metric:
            return jsonify({'error': '指标不存在'}), 404
        if 'key' in data:
            metric.key = data['key']
        if 'name' in data:
            metric.name = data['name']
        if 'unit' in data:
            metric.unit = data['unit']
        if 'show_in_chart' in data:
            metric.show_in_chart = data['show_in_chart']
        if 'max_value' in data:
            metric.max_value = data['max_value']
        if 'sort_order' in data:
            metric.sort_order = data['sort_order']
        if 'warn_threshold' in data:
            metric.warn_threshold = data['warn_threshold']
        if 'error_threshold' in data:
            metric.error_threshold = data['error_threshold']
        if 'threshold_direction' in data:
            metric.threshold_direction = data['threshold_direction']
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/metrics/<int:metric_id>', methods=['DELETE'])
def api_object_metrics_delete(object_id, metric_id):
    """删除指标配置"""
    session = SessionLocal()
    try:
        metric = session.query(ObjectMetric).filter_by(id=metric_id, object_id=object_id).first()
        if not metric:
            return jsonify({'error': '指标不存在'}), 404
        session.delete(metric)
        session.commit()
        return jsonify({'ok': True})
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/re-evaluate', methods=['POST'])
def api_re_evaluate_records(object_id):
    """根据当前阈值配置重新评估该对象所有巡检记录的异常状态"""
    session = SessionLocal()
    try:
        records = session.query(InspectionRecord).filter_by(object_id=object_id).all()
        if not records:
            return jsonify({'updated': 0})
        updated = 0
        for record in records:
            parsed_metrics = _parse_status_to_metrics(record.status_detail or '')
            if record.metrics:
                try:
                    stored = json.loads(record.metrics) if isinstance(record.metrics, str) else record.metrics
                    parsed_metrics.update(stored)
                except Exception:
                    pass
            threshold_result = _check_metrics_thresholds(parsed_metrics, object_id, session)
            if threshold_result is not None and record.result != threshold_result:
                record.result = threshold_result
                updated += 1
        session.commit()
        return jsonify({'updated': updated})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@main.route('/inspectors')
def inspectors():
    """巡检人员管理页面"""
    session = SessionLocal()
    try:
        inspector_list = session.query(Inspector).order_by(Inspector.team, Inspector.name).all()
        return render_template('inspectors.html', inspectors=inspector_list)
    finally:
        session.close()


@main.route('/inspectors/add', methods=['POST'])
def inspector_add():
    """添加巡检人员"""
    name = request.form.get('name', '').strip()
    team = request.form.get('team', '').strip() or None
    contact = request.form.get('contact', '').strip() or None

    if not name:
        flash('姓名不能为空', 'danger')
        return redirect(url_for('main.inspectors'))

    session = SessionLocal()
    try:
        inspector = Inspector(name=name, team=team, contact=contact)
        session.add(inspector)
        session.commit()
        flash(f'巡检人员 "{name}" 添加成功', 'success')
    except Exception as e:
        session.rollback()
        flash(f'添加失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.inspectors'))


@main.route('/inspectors/edit/<int:inspector_id>', methods=['POST'])
def inspector_edit(inspector_id):
    """编辑巡检人员"""
    session = SessionLocal()
    try:
        inspector = session.query(Inspector).get(inspector_id)
        if not inspector:
            flash('巡检人员不存在', 'danger')
            return redirect(url_for('main.inspectors'))

        name = request.form.get('name', '').strip()
        team = request.form.get('team', '').strip() or None
        contact = request.form.get('contact', '').strip() or None

        if name:
            inspector.name = name
        inspector.team = team
        inspector.contact = contact

        session.commit()
        flash(f'巡检人员 "{inspector.name}" 已更新', 'success')
    except Exception as e:
        session.rollback()
        flash(f'更新失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.inspectors'))


@main.route('/inspectors/delete/<int:inspector_id>', methods=['POST'])
def inspector_delete(inspector_id):
    """删除巡检人员"""
    session = SessionLocal()
    try:
        inspector = session.query(Inspector).get(inspector_id)
        if not inspector:
            flash('巡检人员不存在', 'danger')
            return redirect(url_for('main.inspectors'))

        name = inspector.name
        session.delete(inspector)
        session.commit()
        flash(f'巡检人员 "{name}" 已删除', 'success')
    except Exception as e:
        session.rollback()
        flash(f'删除失败: {e}', 'danger')
    finally:
        session.close()
    return redirect(url_for('main.inspectors'))


@main.route('/api/inspectors/list')
def api_inspectors_list():
    """巡检人员列表 API"""
    session = SessionLocal()
    try:
        inspectors = session.query(Inspector).all()
        return jsonify([
            {'id': i.id, 'name': i.name, 'team': i.team, 'contact': i.contact}
            for i in inspectors
        ])
    finally:
        session.close()


@main.route('/upload')
def upload():
    """OCR 截图识别页面"""
    return render_template('upload.html')


@main.route('/import')
def bulk_import():
    """批量导入页面"""
    return render_template('bulk_import.html')


@main.route('/api/objects/import', methods=['POST'])
def api_objects_import():
    """批量导入巡检对象"""
    data = request.get_json()
    if not data or 'objects' not in data:
        return jsonify({'error': '没有要导入的数据'}), 400

    objects = data['objects']
    session = SessionLocal()
    imported = 0
    try:
        for item in objects:
            name = item.get('name', '').strip()
            location = item.get('location', '').strip() or None
            device_type = item.get('device_type', '').strip() or None
            description = item.get('description', '').strip() or None

            if not name:
                continue

            # 检查是否已存在同名对象
            existing = session.query(InspectionObject).filter_by(name=name).first()
            if existing:
                continue

            obj = InspectionObject(name=name, location=location, device_type=device_type, description=description)
            session.add(obj)
            imported += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'导入失败: {str(e)}'}), 500
    finally:
        session.close()

    return jsonify({'imported': imported})


@main.route('/api/inspectors/import', methods=['POST'])
def api_inspectors_import():
    """批量导入人员"""
    data = request.get_json()
    if not data or 'inspectors' not in data:
        return jsonify({'error': '没有要导入的数据'}), 400

    inspectors = data['inspectors']
    session = SessionLocal()
    imported = 0
    try:
        for item in inspectors:
            name = item.get('name', '').strip()
            team = item.get('team', '').strip() or None
            contact = item.get('contact', '').strip() or None

            if not name:
                continue

            # 检查是否已存在同名人员
            existing = session.query(Inspector).filter_by(name=name).first()
            if existing:
                continue

            inspector = Inspector(name=name, team=team, contact=contact)
            session.add(inspector)
            imported += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'导入失败: {str(e)}'}), 500
    finally:
        session.close()

    return jsonify({'imported': imported})


@main.route('/api/records/import', methods=['POST'])
def api_records_import():
    """批量导入巡检记录"""
    data = request.get_json()
    if not data or 'records' not in data:
        return jsonify({'error': '没有要导入的数据'}), 400

    records = data['records']
    session = SessionLocal()
    imported = 0
    skipped = 0
    created = 0
    try:
        all_objects = session.query(InspectionObject).filter_by(status='active').all()
        all_inspectors = session.query(Inspector).all()

        for item in records:
            object_name = item.get('point_name', '').strip() or item.get('object_name', '').strip()
            timestamp_str = item.get('timestamp', '').strip()
            result = item.get('result', '正常').strip()
            inspector_name = item.get('inspector_name', '').strip()
            status_detail = item.get('status_detail', '').strip() or None
            notes = item.get('notes', '').strip() or None

            if not object_name:
                skipped += 1
                continue

            # 匹配巡检对象
            obj = _match_object(object_name, all_objects)
            if not obj:
                # 自动创建新巡检对象
                obj = InspectionObject(
                    name=object_name,
                    location=object_name,
                    device_type='监控',
                    description=f'批量导入 - {status_detail or ""}',
                    status='active'
                )
                session.add(obj)
                session.flush()
                all_objects.append(obj)
                created += 1

            # 匹配巡检人员
            inspector = None
            if inspector_name:
                inspector = _match_inspector(inspector_name, all_inspectors)
            if not inspector and all_inspectors:
                inspector = all_inspectors[0]

            # 解析时间
            timestamp = None
            if timestamp_str:
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
                    except ValueError:
                        timestamp = datetime.now()
            else:
                timestamp = datetime.now()

            # 根据指标阈值重新判断结果
            parsed_metrics = _parse_status_to_metrics(status_detail or '')
            threshold_result = _check_metrics_thresholds(parsed_metrics, obj.id, session)
            if threshold_result:
                result = threshold_result

            record = InspectionRecord(
                point_id=obj.id,
                object_id=obj.id,
                inspector_id=inspector.id if inspector else None,
                result=result,
                status_detail=status_detail,
                metrics=json.dumps(_parse_status_to_metrics(status_detail), ensure_ascii=False),
                notes=notes,
                timestamp=timestamp
            )
            session.add(record)
            imported += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'导入失败: {str(e)}'}), 500
    finally:
        session.close()

    return jsonify({'imported': imported, 'skipped': skipped, 'created': created})


@main.route('/api/ocr', methods=['POST'])
def api_ocr():
    """OCR 识别 API"""
    if not ocr_engine:
        return jsonify({'error': 'OCR 引擎未安装，请运行: pip install rapidocr-onnxruntime'}), 500

    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'error': '请提供图片数据'}), 400

    image_data = data['image']
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    config = _load_ocr_config()
    ignore_top = config.get('ignore_top', 0)
    ignore_bottom = config.get('ignore_bottom', 0)

    try:
        image_bytes = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(image_bytes))
        img_height = img.height
        top_cutoff = int(img_height * ignore_top / 100) if ignore_top > 0 else 0
        bottom_cutoff = img_height - int(img_height * ignore_bottom / 100) if ignore_bottom > 0 else img_height

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            tmp_path = tmp.name
        result, _ = ocr_engine(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        return jsonify({'error': f'图片处理失败: {str(e)}'}), 400

    filtered_result = []
    for item in (result or []):
        if item and len(item) >= 2:
            bbox = item[0]
            if bbox and len(bbox) >= 4:
                y_center = (bbox[0][1] + bbox[2][1]) / 2
                if y_center < top_cutoff or y_center > bottom_cutoff:
                    continue
            filtered_result.append(item)

    items = parse_inspection_form(filtered_result)
    return jsonify({'items': items, 'raw_lines': [item[1] for item in filtered_result if item]})


@main.route('/ocr-admin')
def ocr_admin():
    """OCR 管理页面（隐藏）"""
    config = _load_ocr_config()
    engine_status = 'running' if ocr_engine else 'not_installed'
    return render_template('ocr_admin.html', config=config, engine_status=engine_status)


@main.route('/api/ocr-config', methods=['GET'])
def api_ocr_config_get():
    """获取当前 OCR 配置"""
    return jsonify(_load_ocr_config())


@main.route('/api/ocr-config', methods=['POST'])
def api_ocr_config_apply():
    """实时应用 OCR 配置（不持久化）"""
    global ocr_engine
    data = request.get_json()
    if not data:
        return jsonify({'error': '请提供配置数据'}), 400

    config = _load_ocr_config()
    config.update(data)

    new_engine = _build_ocr_engine(config)
    if new_engine is None:
        return jsonify({'error': 'OCR 引擎未安装，请运行: pip install rapidocr-onnxruntime'}), 500

    ocr_engine = new_engine
    return jsonify({'ok': True, 'config': config})


@main.route('/api/ocr-config/save', methods=['POST'])
def api_ocr_config_save():
    """保存 OCR 配置到文件"""
    global ocr_engine
    data = request.get_json()
    if not data:
        return jsonify({'error': '请提供配置数据'}), 400

    config = _load_ocr_config()
    config.update(data)

    try:
        with open(OCR_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({'error': f'保存失败: {str(e)}'}), 500

    new_engine = _build_ocr_engine(config)
    if new_engine is not None:
        ocr_engine = new_engine

    return jsonify({'ok': True, 'config': config})


@main.route('/api/dashboard-types', methods=['GET'])
def api_dashboard_types_list():
    """获取所有仪表盘类型"""
    return jsonify(_load_dashboard_types())


@main.route('/api/dashboard-types/categories', methods=['GET'])
def api_dashboard_types_categories():
    """获取所有仪表盘分类"""
    types_list = _load_dashboard_types()
    categories = sorted(set(t.get('category', '') for t in types_list if t.get('category', '').strip()))
    return jsonify(categories)


@main.route('/api/dashboard-types', methods=['POST'])
def api_dashboard_types_add():
    """添加仪表盘类型"""
    data = request.get_json()
    if not data or not data.get('name', '').strip():
        return jsonify({'error': '类型名称不能为空'}), 400

    types_list = _load_dashboard_types()
    new_id = data.get('id', '').strip() or re.sub(r'[^a-z0-9_]', '', data['name'].lower().replace(' ', '_')) or f'type_{int(__import__("time").time() * 1000)}'

    if not new_id:
        return jsonify({'error': '类型ID不能为空'}), 400

    if any(t['id'] == new_id for t in types_list):
        return jsonify({'error': f'ID "{new_id}" 已存在'}), 409

    new_type = {
        'id': new_id,
        'name': data['name'].strip(),
        'category': data.get('category', '').strip(),
        'description': data.get('description', '').strip(),
        'detect_keywords': data.get('detect_keywords', []),
        'labels': data.get('labels', {}),
        'extra_labels': data.get('extra_labels', []),
        'result_rules': data.get('result_rules', {}),
    }
    types_list.append(new_type)
    _save_dashboard_types(types_list)
    return jsonify({'ok': True, 'type': new_type})


@main.route('/api/dashboard-types/<type_id>', methods=['PUT'])
def api_dashboard_types_update(type_id):
    """更新仪表盘类型"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请提供数据'}), 400

    types_list = _load_dashboard_types()
    for i, t in enumerate(types_list):
        if t['id'] == type_id:
            types_list[i].update({
                'name': data.get('name', t['name']),
                'category': data.get('category', t.get('category', '')),
                'description': data.get('description', t['description']),
                'detect_keywords': data.get('detect_keywords', t['detect_keywords']),
                'labels': data.get('labels', t['labels']),
                'extra_labels': data.get('extra_labels', t.get('extra_labels', [])),
                'result_rules': data.get('result_rules', t.get('result_rules', {})),
                'number_before_label': data.get('number_before_label', t.get('number_before_label', False)),
            })
            _save_dashboard_types(types_list)
            return jsonify({'ok': True, 'type': types_list[i]})

    return jsonify({'error': f'类型 "{type_id}" 不存在'}), 404


@main.route('/api/dashboard-types/<type_id>', methods=['DELETE'])
def api_dashboard_types_delete(type_id):
    """删除仪表盘类型"""
    types_list = _load_dashboard_types()
    new_list = [t for t in types_list if t['id'] != type_id]
    if len(new_list) == len(types_list):
        return jsonify({'error': f'类型 "{type_id}" 不存在'}), 404
    _save_dashboard_types(new_list)
    return jsonify({'ok': True})


@main.route('/api/dashboard-types/sync', methods=['POST'])
def api_dashboard_types_sync():
    """从巡检对象同步指标到仪表盘类型"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).filter_by(status='active').all()
        types_list = _load_dashboard_types()
        updated = 0
        created = 0

        for obj in objects:
            metrics = session.query(ObjectMetric).filter_by(object_id=obj.id).all()
            if not metrics:
                continue

            labels = {}
            for m in metrics:
                labels[m.name] = m.key

            # 查找已存在的仪表盘类型（按 obj_X id 或 名称匹配）
            type_id = f'obj_{obj.id}'
            existing = next((t for t in types_list if t['id'] == type_id), None)
            if not existing:
                existing = next((t for t in types_list if t['name'] == obj.name), None)

            if existing:
                if existing.get('labels') != labels:
                    existing['labels'] = labels
                    existing['detect_keywords'] = list(set(existing.get('detect_keywords', []) + [obj.name]))
                    updated += 1
            else:
                types_list.append({
                    'id': type_id,
                    'name': obj.name,
                    'description': obj.description or f'{obj.name} 仪表盘',
                    'detect_keywords': [obj.name],
                    'labels': labels,
                    'extra_labels': [],
                    'result_rules': {},
                    'number_before_label': False,
                })
                created += 1

        _save_dashboard_types(types_list)
        return jsonify({'ok': True, 'created': created, 'updated': updated, 'total_objects': len(objects)})
    finally:
        session.close()


@main.route('/api/dashboard-types/<type_id>/sync', methods=['POST'])
def api_dashboard_type_sync_single(type_id):
    """从巡检对象同步指标到指定仪表盘类型"""
    session = SessionLocal()
    try:
        types_list = _load_dashboard_types()
        target = next((t for t in types_list if t['id'] == type_id), None)
        if not target:
            return jsonify({'error': f'类型 "{type_id}" 不存在'}), 404

        # 通过 id (obj_X) 或名称匹配巡检对象
        obj = None
        if type_id.startswith('obj_'):
            try:
                obj_id = int(type_id[4:])
                obj = session.query(InspectionObject).filter_by(id=obj_id, status='active').first()
            except (ValueError, IndexError):
                pass
        if not obj:
            obj = session.query(InspectionObject).filter_by(name=target['name'], status='active').first()
        if not obj:
            return jsonify({'error': '未找到对应的巡检对象，请先在对象管理中创建'}), 404

        metrics = session.query(ObjectMetric).filter_by(object_id=obj.id).all()
        if not metrics:
            return jsonify({'error': f'巡检对象 "{obj.name}" 没有配置指标'}), 400

        labels = {m.name: m.key for m in metrics}
        target['labels'] = labels
        target['detect_keywords'] = list(set(target.get('detect_keywords', []) + [obj.name]))
        _save_dashboard_types(types_list)
        return jsonify({'ok': True, 'updated_labels': labels})
    finally:
        session.close()


@main.route('/api/ocr/model-info', methods=['GET'])
def api_ocr_model_info():
    """获取当前 OCR 模型信息"""
    info = {
        'installed': ocr_engine is not None,
        'engine': 'RapidOCR (ONNX Runtime)',
        'version': None,
        'models': {},
    }
    if ocr_engine is not None:
        try:
            import rapidocr_onnxruntime
            info['version'] = getattr(rapidocr_onnxruntime, '__version__', None)
        except Exception:
            pass
        try:
            det_cls_rec = getattr(ocr_engine, 'det_cls_rec', None)
            if det_cls_rec:
                det_model, cls_model, rec_model = det_cls_rec
                info['models'] = {
                    'detection': getattr(det_model, 'model_path', None) or str(getattr(det_model, 'model', '')),
                    'classification': getattr(cls_model, 'model_path', None) or str(getattr(cls_model, 'model', '')),
                    'recognition': getattr(rec_model, 'model_path', None) or str(getattr(rec_model, 'model', '')),
                }
        except Exception:
            pass
        try:
            textdet = getattr(ocr_engine, 'textdet', None)
            if textdet:
                info['models']['detection'] = getattr(getattr(textdet, 'model', None), 'model_path', None) or info['models'].get('detection', '')
            textrec = getattr(ocr_engine, 'textrec', None)
            if textrec:
                info['models']['recognition'] = getattr(getattr(textrec, 'model', None), 'model_path', None) or info['models'].get('recognition', '')
        except Exception:
            pass
    return jsonify(info)


@main.route('/api/objects/quick-create', methods=['POST'])
def api_quick_create_object():
    """快速创建巡检对象（JSON API）"""
    data = request.get_json()
    if not data or not data.get('name', '').strip():
        return jsonify({'error': '名称不能为空'}), 400

    name = data['name'].strip()
    location = data.get('location', '').strip() or None
    device_type = data.get('device_type', '').strip() or None
    description = data.get('description', '').strip() or None

    session = SessionLocal()
    try:
        query = session.query(InspectionObject).filter_by(name=name, status='active')
        if location:
            query = query.filter_by(location=location)
        existing = query.first()
        if existing:
            msg = f'对象 "{name}" 已存在'
            if location:
                msg += f'（位置: {location}）'
            return jsonify({'error': msg, 'id': existing.id}), 409

        obj = InspectionObject(name=name, location=location, device_type=device_type, description=description)
        session.add(obj)
        session.commit()
        return jsonify({'ok': True, 'id': obj.id, 'name': obj.name})
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'创建失败: {str(e)}'}), 500
    finally:
        session.close()


@main.route('/api/objects/<int:object_id>/sync-metrics', methods=['POST'])
def api_object_sync_metrics(object_id):
    """从仪表盘类型同步指标到巡检对象"""
    data = request.get_json() or {}
    dashboard_type_name = data.get('dashboard_type_name', '').strip()
    if not dashboard_type_name:
        return jsonify({'error': '缺少仪表盘类型名称'}), 400

    types_list = _load_dashboard_types()
    dashboard_type = next((t for t in types_list if t['name'] == dashboard_type_name), None)
    if not dashboard_type:
        return jsonify({'error': f'未找到仪表盘类型 "{dashboard_type_name}"'}), 404

    labels = dashboard_type.get('labels', {})
    if not labels:
        return jsonify({'ok': True, 'created': 0})

    session = SessionLocal()
    try:
        obj = session.query(InspectionObject).get(object_id)
        if not obj:
            return jsonify({'error': '巡检对象不存在'}), 404

        existing_keys = {m.key for m in obj.metrics}
        created = 0
        for i, (label_name, label_key) in enumerate(labels.items()):
            if label_key not in existing_keys:
                m = ObjectMetric(object_id=object_id, key=label_key, name=label_name, sort_order=i)
                session.add(m)
                created += 1
        session.commit()
        return jsonify({'ok': True, 'created': created, 'total': len(labels)})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@main.route('/api/ocr/test', methods=['POST'])
def api_ocr_test():
    """用当前配置测试 OCR 识别"""
    if not ocr_engine:
        return jsonify({'error': 'OCR 引擎未安装，请运行: pip install rapidocr-onnxruntime'}), 500

    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'error': '请提供图片数据'}), 400

    image_data = data['image']
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    config = _load_ocr_config()
    ignore_top = config.get('ignore_top', 0)
    ignore_bottom = config.get('ignore_bottom', 0)

    try:
        image_bytes = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(image_bytes))
        img_height = img.height
        top_cutoff = int(img_height * ignore_top / 100) if ignore_top > 0 else 0
        bottom_cutoff = img_height - int(img_height * ignore_bottom / 100) if ignore_bottom > 0 else img_height

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            tmp_path = tmp.name
        result, _ = ocr_engine(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        return jsonify({'error': f'图片处理失败: {str(e)}'}), 400

    filtered_result = []
    for item in (result or []):
        if item and len(item) >= 2:
            bbox = item[0]
            if bbox and len(bbox) >= 4:
                y_center = (bbox[0][1] + bbox[2][1]) / 2
                if y_center < top_cutoff or y_center > bottom_cutoff:
                    continue
            filtered_result.append(item)

    raw_lines = [item[1] for item in filtered_result if item]
    return jsonify({'raw_lines': raw_lines, 'config': config})


@main.route('/api/save', methods=['POST'])
def api_save():
    """保存 OCR 识别结果"""
    data = request.get_json()
    if not data or 'items' not in data:
        return jsonify({'error': '没有要保存的数据'}), 400

    items = data['items']
    session = SessionLocal()
    saved = 0
    skipped = 0
    created = 0
    last_object_id = None
    try:
        all_objects = session.query(InspectionObject).filter_by(status='active').all()
        all_inspectors = session.query(Inspector).all()

        for item in items:
            object_name = item.get('point_name', '').strip() or item.get('object_name', '').strip()
            location = item.get('location', '').strip()
            result = item.get('result', '正常')
            status_detail = item.get('status_detail', '')
            notes = item.get('notes', '')
            inspector_name = item.get('inspector', '')
            timestamp_str = item.get('timestamp')
            is_dashboard = item.get('is_dashboard', False)
            dashboard_type_name = item.get('dashboard_type_name', '') if is_dashboard else ''
            dashboard_category = item.get('dashboard_category', '') if is_dashboard else ''
            front_point_id = item.get('point_id')

            # 匹配巡检对象
            obj = None

            # 优先使用前端已选择的 point_id（但 device_type 须匹配）
            if front_point_id:
                try:
                    obj = session.query(InspectionObject).get(int(front_point_id))
                    if obj and dashboard_category and (obj.device_type or '') != dashboard_category:
                        print(f'  SAVE: 前端选择对象 device_type={obj.device_type} 与类别 {dashboard_category} 不匹配，忽略')
                        obj = None
                except (ValueError, TypeError):
                    obj = None

            # 如果有明确的对象名称，先按名称匹配（仪表盘类型需 device_type 匹配）
            if not obj and object_name:
                obj = _match_object(object_name, all_objects, expected_type=dashboard_category)
            
            # 仪表盘格式：优先按位置匹配（仪表盘类型需 device_type 匹配）
            if not obj and is_dashboard and location:
                obj = _match_object_by_location(location, all_objects, expected_type=dashboard_category)
            
            # 仪表盘格式：如果没有位置匹配，尝试按仪表盘类型匹配
            if not obj and is_dashboard:
                match_type = dashboard_category or '监控'
                obj = _match_object_by_type(match_type, all_objects)
            
            # 如果还是没有匹配，创建新对象
            if not obj:
                if is_dashboard and location:
                    obj_name = dashboard_type_name or location
                    obj_location = object_name or location
                elif object_name:
                    obj_name = object_name
                    obj_location = location
                else:
                    skipped += 1
                    continue
                
                obj = InspectionObject(
                    name=obj_name,
                    location=obj_location,
                    device_type=dashboard_category or '监控',
                    description=f'OCR自动创建 [{dashboard_type_name or "监控"}] - {status_detail}',
                    status='active'
                )
                session.add(obj)
                session.flush()
                all_objects.append(obj)
                created += 1

            # 匹配巡检人员
            inspector = None
            front_inspector_id = item.get('inspector_id')
            if front_inspector_id:
                try:
                    inspector = session.query(Inspector).get(int(front_inspector_id))
                except (ValueError, TypeError):
                    inspector = None
            if not inspector and inspector_name:
                inspector = _match_inspector(inspector_name, all_inspectors)
            if not inspector and all_inspectors:
                inspector = all_inspectors[0]

            # 解析时间
            timestamp = None
            if timestamp_str:
                if isinstance(timestamp_str, str):
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                    except ValueError:
                        timestamp = datetime.now()
                else:
                    timestamp = timestamp_str
            else:
                timestamp = datetime.now()

            # 根据指标阈值重新判断结果
            parsed_metrics = _parse_status_to_metrics(status_detail)

            # 自动创建指标配置（如果不存在）
            if parsed_metrics:
                existing_metrics = {m.key: m for m in session.query(ObjectMetric).filter_by(object_id=obj.id).all()}
                for key, val in parsed_metrics.items():
                    try:
                        fv = float(val)
                    except (ValueError, TypeError):
                        continue
                    if key in existing_metrics:
                        m = existing_metrics[key]
                        new_max = max(fv * 1.5, 100)
                        if m.unit == 'w':
                            new_max = max(fv * 1.5, 10000)
                        if new_max > (m.max_value or 100):
                            m.max_value = new_max
                        if fv >= 10000 and not m.unit:
                            m.unit = 'w'
                            m.max_value = max(fv * 1.5, 10000)
                    else:
                        unit = ''
                        max_val = max(fv * 1.5, 100)
                        if fv >= 10000:
                            unit = 'w'
                            max_val = max(fv * 1.5, 10000)
                        session.add(ObjectMetric(
                            object_id=obj.id, key=key, name=key, unit=unit,
                            max_value=max_val, show_in_chart=True
                        ))
                        print(f'  SAVE: 自动创建指标配置 key={key} max_value={max_val}')

            threshold_result = _check_metrics_thresholds(parsed_metrics, obj.id, session)
            if threshold_result:
                result = threshold_result

            record = InspectionRecord(
                point_id=obj.id,
                object_id=obj.id,
                inspector_id=inspector.id if inspector else None,
                result=result,
                status_detail=status_detail,
                metrics=json.dumps(parsed_metrics, ensure_ascii=False),
                notes=notes,
                timestamp=timestamp
            )
            session.add(record)
            session.commit()
            saved += 1
            last_object_id = obj.id
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'保存失败: {str(e)}'}), 500
    finally:
        session.close()

    return jsonify({'saved': saved, 'skipped': skipped, 'created': created, 'object_id': last_object_id})


def _match_object(name, all_objects, expected_type=None):
    """匹配巡检对象"""
    name_lower = name.lower()
    best = None
    best_score = 0
    expected_lower = expected_type.lower() if expected_type else None

    for obj in all_objects:
        if expected_lower and (obj.device_type or '').lower() != expected_lower:
            continue
        score = 0
        obj_name_lower = (obj.name or '').lower()
        location_lower = (obj.location or '').lower()

        if obj_name_lower and (obj_name_lower in name_lower or name_lower in obj_name_lower):
            score += 20
        if location_lower and location_lower in name_lower:
            score += 10
        if obj.device_type:
            dtype_lower = obj.device_type.lower()
            if dtype_lower in name_lower:
                score += 5

        if score > best_score:
            best_score = score
            best = obj

    if best and best_score >= 10:
        return best
    return None


def _match_object_by_location(location, all_objects, expected_type=None):
    """按位置匹配巡检对象"""
    if not location:
        return None
    
    location_lower = location.lower()
    best = None
    best_score = 0
    expected_lower = expected_type.lower() if expected_type else None

    for obj in all_objects:
        if expected_lower and (obj.device_type or '').lower() != expected_lower:
            continue
        score = 0
        obj_location_lower = (obj.location or '').lower()
        obj_name_lower = (obj.name or '').lower()

        # 位置完全匹配
        if obj_location_lower and obj_location_lower == location_lower:
            score += 30
        # 位置包含匹配
        elif obj_location_lower and location_lower in obj_location_lower:
            score += 20
        elif obj_location_lower and obj_location_lower in location_lower:
            score += 15
        # 名称包含位置
        elif obj_name_lower and location_lower in obj_name_lower:
            score += 10

        if score > best_score:
            best_score = score
            best = obj

    if best and best_score >= 15:
        return best
    return None


def _match_object_by_type(device_type, all_objects):
    """按设备类型匹配巡检对象（返回第一个匹配的）"""
    if not device_type:
        return None
    
    type_lower = device_type.lower()
    for obj in all_objects:
        if (obj.device_type or '').lower() == type_lower:
            return obj
    return None


def _match_inspector(name, all_inspectors):
    """匹配巡检人员"""
    name_lower = name.lower()
    for inspector in all_inspectors:
        if (inspector.name or '').lower() == name_lower:
            return inspector
    return None


@main.route('/api/export/json')
def api_export_json():
    """导出 JSON 数据 API"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).filter_by(status='active').all()
        data = []
        for obj in objects:
            records = (
                session.query(InspectionRecord)
                .filter_by(object_id=obj.id)
                .order_by(InspectionRecord.timestamp.desc())
                .all()
            )
            records_data = [
                {
                    'timestamp': r.timestamp.strftime('%Y-%m-%d %H:%M'),
                    'result': r.result,
                    'status_detail': r.status_detail,
                    'notes': r.notes,
                    'inspector': r.inspector.name if r.inspector else '未知',
                }
                for r in records
            ]
            data.append({
                'name': obj.name,
                'location': obj.location,
                'device_type': obj.device_type,
                'description': obj.description,
                'records': records_data,
            })

        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename="inspection_data.json"'}
        )
    finally:
        session.close()