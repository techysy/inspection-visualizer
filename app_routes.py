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

try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
except ImportError:
    ocr_engine = None

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


def _extract_location_from_lines(lines):
    """从行列表中提取位置信息"""
    skip_words = ['监控点总数', '在线', '离线', '未检测', '监控点在线率', '默认区域设置', 'admin']
    
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

    # 尝试解析仪表盘格式（监控系统截图）
    dashboard_result = parse_dashboard_screenshot(all_text, lines)
    if dashboard_result:
        return [dashboard_result]

    # 传统表单格式解析
    return parse_traditional_form(lines)


def parse_dashboard_screenshot(all_text, lines):
    """解析监控系统仪表盘截图"""
    region_name = ''
    total = 0
    online = 0
    offline = 0
    undetected = 0
    online_rate = ''

    # 识别"监控点总数"后面的大数字
    total_match = re.search(r'监控点总数\s*(\d+)', all_text)
    if total_match:
        total = int(total_match.group(1))

    # 识别"在线"数量（排除"离线"、"在线率"）
    online_match = re.search(r'(?<!离)在线\s*(\d+)', all_text)
    if online_match:
        online = int(online_match.group(1))

    # 识别"离线"数量
    offline_match = re.search(r'离线\s*(\d+)', all_text)
    if offline_match:
        offline = int(offline_match.group(1))

    # 识别"未检测"数量
    undetected_match = re.search(r'未检测\s*(\d+)', all_text)
    if undetected_match:
        undetected = int(undetected_match.group(1))

    # 识别在线率百分比
    rate_match = re.search(r'(\d{1,3}\.\d{1,2})%', all_text)
    if rate_match:
        online_rate = rate_match.group(0)

    # 识别区域名称
    region_name = _extract_location_from_lines(lines)

    # 必须至少识别到总数或在线数才算有效
    if total == 0 and online == 0:
        return None

    # 构建状态详情
    status_detail_parts = []
    if total > 0:
        status_detail_parts.append(f'监控点总数: {total}')
    if online > 0:
        status_detail_parts.append(f'在线: {online}')
    if offline > 0:
        status_detail_parts.append(f'离线: {offline}')
    if undetected > 0:
        status_detail_parts.append(f'未检测: {undetected}')
    if online_rate:
        status_detail_parts.append(f'在线率: {online_rate}')

    # 判断整体状态
    result = '正常'
    if offline > 0:
        result = '异常'
    if online_rate:
        rate_value = float(online_rate.replace('%', ''))
        if rate_value < 90:
            result = '异常'
        elif rate_value < 95:
            result = '需关注'

    # 返回结果：区域名称作为location，point_name留空以便后续匹配
    return {
        'point_name': '',  # 留空，由保存逻辑匹配
        'location': region_name,  # 区域名称作为位置
        'result': result,
        'status_detail': '; '.join(status_detail_parts),
        'notes': '',
        'inspector': '',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'is_dashboard': True,  # 标记为仪表盘格式
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

        # 统计数据
        total_records = len(records)
        normal_count = sum(1 for r in records if r.result == '正常')
        abnormal_count = sum(1 for r in records if r.result == '异常')

        # 按结果分组，用于图表
        result_timeline = {}
        for record in records:
            result_key = record.result
            if result_key not in result_timeline:
                result_timeline[result_key] = []
            result_timeline[result_key].append({
                'x': record.timestamp.strftime('%Y-%m-%d %H:%M'),
                'y': 1 if record.result == '正常' else 0,
                'result': record.result,
                'inspector': record.inspector.name if record.inspector else '未知',
            })

        # 获取指标配置
        object_metrics = session.query(ObjectMetric).filter_by(object_id=object_id).order_by(ObjectMetric.sort_order).all()
        metrics_config = [
            {'id': m.id, 'key': m.key, 'name': m.name, 'unit': m.unit, 'show_in_chart': m.show_in_chart}
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

        data = [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'result': r.result,
                'status_detail': r.status_detail,
                'metrics': json.loads(r.metrics) if r.metrics else {},
                'notes': r.notes,
                'inspector': r.inspector.name if r.inspector else '未知',
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
                'show_in_chart': m.show_in_chart,
                'sort_order': m.sort_order,
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
    if not key or not name:
        return jsonify({'error': 'key 和 name 不能为空'}), 400
    session = SessionLocal()
    try:
        metric = ObjectMetric(
            object_id=object_id, key=key, name=name,
            unit=unit, show_in_chart=show_in_chart, sort_order=sort_order
        )
        session.add(metric)
        session.commit()
        return jsonify({'id': metric.id, 'key': metric.key, 'name': metric.name,
                        'unit': metric.unit, 'show_in_chart': metric.show_in_chart})
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
        if 'name' in data:
            metric.name = data['name']
        if 'unit' in data:
            metric.unit = data['unit']
        if 'show_in_chart' in data:
            metric.show_in_chart = data['show_in_chart']
        if 'sort_order' in data:
            metric.sort_order = data['sort_order']
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

    try:
        image_bytes = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(image_bytes))
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            tmp_path = tmp.name
        result, _ = ocr_engine(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        return jsonify({'error': f'图片处理失败: {str(e)}'}), 400

    items = parse_inspection_form(result)
    return jsonify({'items': items, 'raw_lines': [item[1] for item in (result or []) if item]})


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
            front_point_id = item.get('point_id')

            # 匹配巡检对象
            obj = None

            # 优先使用前端已选择的 point_id
            if front_point_id:
                try:
                    obj = session.query(InspectionObject).get(int(front_point_id))
                except (ValueError, TypeError):
                    obj = None

            # 如果有明确的对象名称，先按名称匹配
            if not obj and object_name:
                obj = _match_object(object_name, all_objects)
            
            # 仪表盘格式：优先按位置匹配
            if not obj and is_dashboard and location:
                obj = _match_object_by_location(location, all_objects)
            
            # 仪表盘格式：如果没有位置匹配，尝试匹配监控类型
            if not obj and is_dashboard:
                obj = _match_object_by_type('监控', all_objects)
            
            # 如果还是没有匹配，创建新对象
            if not obj:
                if is_dashboard and location:
                    obj_name = location
                    obj_location = location
                elif object_name:
                    obj_name = object_name
                    obj_location = location
                else:
                    skipped += 1
                    continue
                
                obj = InspectionObject(
                    name=obj_name,
                    location=obj_location,
                    device_type='监控',
                    description=f'OCR自动创建 - {status_detail}',
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
            session.commit()
            saved += 1
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'保存失败: {str(e)}'}), 500
    finally:
        session.close()

    return jsonify({'saved': saved, 'skipped': skipped, 'created': created})


def _match_object(name, all_objects):
    """匹配巡检对象"""
    name_lower = name.lower()
    best = None
    best_score = 0

    for obj in all_objects:
        score = 0
        obj_name_lower = (obj.name or '').lower()
        location_lower = (obj.location or '').lower()

        if obj_name_lower and obj_name_lower in name_lower:
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


def _match_object_by_location(location, all_objects):
    """按位置匹配巡检对象"""
    if not location:
        return None
    
    location_lower = location.lower()
    best = None
    best_score = 0

    for obj in all_objects:
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


@main.route('/export/json')
def export_json():
    """导出 JSON"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).all()
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


@main.route('/export/html')
def export_html():
    """导出 HTML"""
    session = SessionLocal()
    try:
        objects = session.query(InspectionObject).all()
        all_data = []
        for obj in objects:
            records = (
                session.query(InspectionRecord)
                .filter_by(object_id=obj.id)
                .order_by(InspectionRecord.timestamp.desc())
                .all()
            )
            all_data.append({
                'object': obj,
                'records': records,
            })

        html = render_template('export.html', all_data=all_data, now=datetime.utcnow())
        return Response(
            html,
            mimetype='text/html',
            headers={'Content-Disposition': 'attachment; filename="inspection_report.html"'}
        )
    finally:
        session.close()