from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
from config import config

Base = declarative_base()

app_config = config['default']
engine = create_engine(app_config.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(bind=engine)


class InspectionObject(Base):
    """巡检对象"""
    __tablename__ = 'inspection_objects'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # 名称
    location = Column(String(100))  # 位置/机房/区域
    device_type = Column(String(50))  # 类型：服务器/网络设备/存储/UPS等
    status = Column(String(20), default='active')  # 状态：active/inactive/maintenance
    description = Column(String(255))  # 描述/备注
    sort_order = Column(Integer, default=0)  # 排序序号
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection_records = relationship('InspectionRecord', back_populates='inspection_object')
    metrics = relationship('ObjectMetric', back_populates='inspection_object', cascade='all, delete-orphan')


class ObjectMetric(Base):
    """巡检对象的指标配置"""
    __tablename__ = 'object_metrics'

    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, ForeignKey('inspection_objects.id'), nullable=False)
    key = Column(String(50), nullable=False)       # 指标键名，如 onlinerate
    name = Column(String(50), nullable=False)      # 显示名称，如 在线率
    unit = Column(String(20), default='')           # 单位，如 %
    max_value = Column(Float, default=100)          # 图表Y轴最大值，百分比默认100
    show_in_chart = Column(Boolean, default=True)   # 是否参与可视化
    sort_order = Column(Integer, default=0)         # 排序
    # 阈值设置
    warn_threshold = Column(Float, nullable=True)   # 需关注阈值（为空则不启用）
    error_threshold = Column(Float, nullable=True)  # 异常阈值（为空则不启用）
    threshold_direction = Column(String(2), default='lt')  # lt=小于触发, gt=大于触发

    inspection_object = relationship('InspectionObject', back_populates='metrics')


class InspectionRecord(Base):
    """巡检记录"""
    __tablename__ = 'inspection_records'

    id = Column(Integer, primary_key=True)
    point_id = Column(Integer, nullable=False, default=0)  # 兼容旧数据库，非ORM关系
    object_id = Column(Integer, ForeignKey('inspection_objects.id'), nullable=False)
    inspector_id = Column(Integer, ForeignKey('inspectors.id'))  # 巡检人员
    result = Column(String(20), nullable=False)  # 巡检结果：正常/异常/合格/不合格
    status_detail = Column(Text)  # 状态详情：设备运行状态、温度、负载等
    metrics = Column(Text)  # JSON: 结构化指标值 {"onlinerate": "84.79", "online": "574", ...}
    notes = Column(Text)  # 备注/问题描述
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)  # 巡检时间

    inspection_object = relationship('InspectionObject', back_populates='inspection_records')
    inspector = relationship('Inspector', back_populates='inspection_records')


class Inspector(Base):
    """巡检人员/班组"""
    __tablename__ = 'inspectors'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)  # 姓名
    team = Column(String(50))  # 所属班组/部门
    contact = Column(String(100))  # 联系方式（电话/邮箱）
    username = Column(String(50), unique=True, nullable=True)  # 登录用户名
    password = Column(String(200), nullable=True)  # 登录密码（werkzeug hash）
    is_admin = Column(Boolean, default=False)  # 管理员权限
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection_records = relationship('InspectionRecord', back_populates='inspector')


class DailyListRecord(Base):
    """日列表快照（群成员、粉丝列表等计数模式数据）"""
    __tablename__ = 'daily_list_records'

    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, ForeignKey('inspection_objects.id'), nullable=False)
    date = Column(Date, nullable=False)                      # 记录日期
    content_type = Column(String(50), default='list')        # 内容类型
    items = Column(Text)                                     # JSON 数组：去重后的列表
    count = Column(Integer, default=0)                       # 去重后计数
    raw_count = Column(Integer, default=0)                   # 原始识别条目数
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection_object = relationship('InspectionObject')

    __table_args__ = (
        UniqueConstraint('object_id', 'date', 'content_type', name='uq_daily_list'),
    )


def init_db():
    Base.metadata.create_all(engine)

    import sqlite3
    from config import config as app_config_module
    db_path = app_config_module['default'].SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    TABLE_COLUMNS = {
        'inspection_objects': {
            'name': 'VARCHAR(100) NOT NULL DEFAULT \'\'',
            'location': 'VARCHAR(100)',
            'device_type': 'VARCHAR(50)',
            'status': 'VARCHAR(20) DEFAULT \'active\'',
            'description': 'VARCHAR(255)',
            'sort_order': 'INTEGER DEFAULT 0',
            'created_at': 'DATETIME',
        },
        'inspection_records': {
            'point_id': 'INTEGER NOT NULL DEFAULT 0',
            'object_id': 'INTEGER NOT NULL',
            'inspector_id': 'INTEGER',
            'result': 'VARCHAR(20) NOT NULL DEFAULT \'正常\'',
            'status_detail': 'TEXT',
            'metrics': 'TEXT',
            'notes': 'TEXT',
            'timestamp': 'DATETIME',
        },
        'inspectors': {
            'name': 'VARCHAR(50) NOT NULL DEFAULT \'\'',
            'team': 'VARCHAR(50)',
            'contact': 'VARCHAR(100)',
            'username': 'VARCHAR(50)',
            'password': 'VARCHAR(200)',
            'is_admin': 'BOOLEAN DEFAULT 0',
            'created_at': 'DATETIME',
        },
        'object_metrics': {
            'object_id': 'INTEGER NOT NULL',
            'key': 'VARCHAR(50) NOT NULL',
            'name': 'VARCHAR(50) NOT NULL',
            'unit': 'VARCHAR(20) DEFAULT \'\'',
            'max_value': 'FLOAT DEFAULT 100',
            'show_in_chart': 'BOOLEAN DEFAULT 1',
            'sort_order': 'INTEGER DEFAULT 0',
        },
        'daily_list_records': {
            'object_id': 'INTEGER NOT NULL',
            'date': 'DATE NOT NULL',
            'content_type': 'VARCHAR(50) DEFAULT \'list\'',
            'items': 'TEXT',
            'count': 'INTEGER DEFAULT 0',
            'raw_count': 'INTEGER DEFAULT 0',
            'created_at': 'DATETIME',
        },
    }

    for table, columns in TABLE_COLUMNS.items():
        cursor.execute(f'PRAGMA table_info({table})')
        existing = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in columns.items():
            if col_name not in existing:
                try:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_def}')
                except sqlite3.OperationalError:
                    pass

    conn.commit()
    conn.close()