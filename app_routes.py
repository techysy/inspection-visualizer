import io
import re
import base64
import tempfile
from datetime import datetime
from pathlib import Path
import json
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, Response
from PIL import Image
from models.inspection import SessionLocal, InspectionObject, InspectionRecord, Inspector

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


def parse_inspection_form(ocr_result):
    """解析巡检表单 OCR 结果"""
    if not ocr_result:
        return []

    lines = []
    for item in ocr_result:
        if item and len(item) >= 2:
            text = item[1]
            lines.append(text)

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
                'object_name': pending_object,
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

        return render_template(
            'object_detail.html',
            object=obj,
            records=records,
            total_records=total_records,
            normal_count=normal_count,
            abnormal_count=abnormal_count,
            result_timeline=result_timeline
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
    try:
        all_objects = session.query(InspectionObject).filter_by(status='active').all()
        all_inspectors = session.query(Inspector).all()

        for item in records:
            object_name = item.get('object_name', '').strip()
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
                skipped += 1
                continue

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
                object_id=obj.id,
                inspector_id=inspector.id if inspector else None,
                result=result,
                status_detail=status_detail,
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

    return jsonify({'imported': imported, 'skipped': skipped})


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
    try:
        all_objects = session.query(InspectionObject).filter_by(status='active').all()
        all_inspectors = session.query(Inspector).all()

        for item in items:
            object_name = item.get('object_name', '').strip()
            result = item.get('result', '正常')
            status_detail = item.get('status_detail', '')
            notes = item.get('notes', '')
            inspector_name = item.get('inspector', '')
            timestamp_str = item.get('timestamp')

            if not object_name:
                skipped += 1
                continue

            # 匹配巡检对象
            obj = _match_object(object_name, all_objects)
            if not obj:
                skipped += 1
                continue

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
                object_id=obj.id,
                inspector_id=inspector.id if inspector else None,
                result=result,
                status_detail=status_detail,
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

    return jsonify({'saved': saved, 'skipped': skipped})


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