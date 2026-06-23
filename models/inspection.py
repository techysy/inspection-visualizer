from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection_records = relationship('InspectionRecord', back_populates='inspection_object')


class InspectionRecord(Base):
    """巡检记录"""
    __tablename__ = 'inspection_records'

    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, ForeignKey('inspection_objects.id'), nullable=False)
    inspector_id = Column(Integer, ForeignKey('inspectors.id'))  # 巡检人员
    result = Column(String(20), nullable=False)  # 巡检结果：正常/异常/合格/不合格
    status_detail = Column(Text)  # 状态详情：设备运行状态、温度、负载等
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inspection_records = relationship('InspectionRecord', back_populates='inspector')


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
            'created_at': 'DATETIME',
        },
        'inspection_records': {
            'object_id': 'INTEGER NOT NULL',
            'inspector_id': 'INTEGER',
            'result': 'VARCHAR(20) NOT NULL DEFAULT \'正常\'',
            'status_detail': 'TEXT',
            'notes': 'TEXT',
            'timestamp': 'DATETIME',
        },
        'inspectors': {
            'name': 'VARCHAR(50) NOT NULL DEFAULT \'\'',
            'team': 'VARCHAR(50)',
            'contact': 'VARCHAR(100)',
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