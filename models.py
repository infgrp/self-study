"""
DB 모델 정의 - 사용자, 시간표, 출석, 학습 기록
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import uuid

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student', 'teacher', 'admin'
    grade = db.Column(db.Integer)       # 학년 (1~3), 학생만
    class_num = db.Column(db.Integer)   # 반 번호, 학생만
    gender = db.Column(db.String(1))      # 'M'(남) / 'F'(여), 학생만
    student_id = db.Column(db.String(5), unique=True)  # 학번 5자리 (입학년도 제외), 학생만
    assigned_grade = db.Column(db.Integer)  # 담당 학년 (1~3), 교사만
    # 교사 계정 승인 여부 (학생·관리자는 항상 True, 교사는 관리자 승인 후 True)
    is_approved = db.Column(db.Boolean, nullable=False,
                            default=True, server_default='1')
    # 세션 무효화용 토큰: DB 교체 또는 비밀번호 변경 시 갱신 → 기존 세션 즉시 차단
    session_token = db.Column(db.String(36), nullable=False,
                              default=lambda: str(uuid.uuid4()))

    schedules = db.relationship('Schedule', backref='user', lazy=True)
    attendances = db.relationship('Attendance', backref='user', lazy=True)
    study_logs = db.relationship('StudyLog', backref='user', lazy=True)

    def get_id(self):
        """Flask-Login 세션 식별자 — 숫자 PK 대신 username 사용 (DB 교체 시 ID 충돌 방지)"""
        return self.username

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        # 비밀번호 변경 시 session_token 갱신 → 다른 기기의 세션 즉시 무효화
        self.session_token = str(uuid.uuid4())

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Schedule(db.Model):
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=월 ~ 4=금
    period = db.Column(db.Integer, nullable=False)        # 교시 (1~4)
    subject = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'day_of_week', 'period', name='uq_schedule_user_day_period'),
    )


class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    period = db.Column(db.Integer, nullable=False)
    # status 값: 'present'(출석), 'late'(지각), 'absent'(결석),
    #            'early_leave'(조퇴), 'approved_leave'(출석인정)
    status = db.Column(db.String(15), nullable=False, default='present')
    study_room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id'), nullable=True)
    checked_at = db.Column(db.DateTime, nullable=True, default=None)
    checked_out_at = db.Column(db.DateTime, nullable=True)        # QR 퇴실 시각
    study_minutes = db.Column(db.Integer, nullable=True)          # QR 입실~퇴실 실측 자습시간(분)
    early_leave_note = db.Column(db.String(200), nullable=True)   # 조퇴 사유 / 교사 인정 메모

    study_room = db.relationship('StudyRoom', backref='attendances')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', 'period', name='uq_attendance_user_date_period'),
    )


class StudyLog(db.Model):
    __tablename__ = 'study_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    subject = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # 분 단위
    memo = db.Column(db.Text)


class Holiday(db.Model):
    """공휴일 등록 테이블"""
    __tablename__ = 'holidays'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(50), nullable=False)  # 공휴일 이름


class StudyPeriodSetting(db.Model):
    """자습 시간 설정 (평일/토요일/공휴일별)"""
    __tablename__ = 'study_period_settings'

    id = db.Column(db.Integer, primary_key=True)
    day_type = db.Column(db.String(10), nullable=False)  # 'weekday', 'saturday', 'holiday'
    period = db.Column(db.Integer, nullable=False)        # 교시 (1~4)
    start_time = db.Column(db.String(5), nullable=False)  # 'HH:MM'
    end_time = db.Column(db.String(5), nullable=False)    # 'HH:MM'
    is_active = db.Column(db.Boolean, default=True)       # 해당 교시 사용 여부

    __table_args__ = (
        db.UniqueConstraint('day_type', 'period', name='uq_day_type_period'),
    )


class StudyRoom(db.Model):
    """자습 공간 (교실, 독서실 등)"""
    __tablename__ = 'study_rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # 공간 이름
    capacity = db.Column(db.Integer, default=0)               # 전체 수용 인원
    male_capacity = db.Column(db.Integer, default=0)          # 남학생 수용 인원
    female_capacity = db.Column(db.Integer, default=0)        # 여학생 수용 인원
    is_active = db.Column(db.Boolean, default=True)           # 사용 여부
    order = db.Column(db.Integer, default=0)                  # 표시 순서
    qr_token = db.Column(db.String(32), unique=True)          # QR코드용 고유 토큰


class StudentRoom(db.Model):
    """학생별 자습 공간 배정"""
    __tablename__ = 'student_rooms'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    study_room_id = db.Column(db.Integer, db.ForeignKey('study_rooms.id'), nullable=False)
    seat_number = db.Column(db.Integer, nullable=True)    # 배정된 좌석 번호 (랜덤 배치 후 설정)
    pos_x = db.Column(db.Float, nullable=True)             # 배치도 X 위치 (%, 0~100)
    pos_y = db.Column(db.Float, nullable=True)             # 배치도 Y 위치 (%, 0~100)

    user = db.relationship('User', backref='assigned_room')
    study_room = db.relationship('StudyRoom', backref='assigned_students')

    __table_args__ = (
        db.UniqueConstraint('user_id', name='uq_user_room'),
    )


class StudyApplication(db.Model):
    """월별 자습 신청"""
    __tablename__ = 'study_applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)           # 신청 날짜
    period = db.Column(db.Integer, nullable=False)       # 교시
    applied_at = db.Column(db.DateTime, default=datetime.now)  # 신청 시각

    user = db.relationship('User', backref='study_applications')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', 'period', name='uq_user_date_period'),
    )


class AttendanceLog(db.Model):
    """출결 수정 이력"""
    __tablename__ = 'attendance_logs'

    id          = db.Column(db.Integer, primary_key=True)
    attendance_id = db.Column(db.Integer, db.ForeignKey('attendance.id', ondelete='CASCADE'), nullable=False)
    changed_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    old_status  = db.Column(db.String(20))
    new_status  = db.Column(db.String(20), nullable=False)
    changed_at  = db.Column(db.DateTime, default=datetime.now)
    note        = db.Column(db.String(50))  # '자동처리', '수동처리'

    changed_by_user = db.relationship('User', foreign_keys=[changed_by])
    attendance      = db.relationship('Attendance',
                          backref=db.backref('logs', lazy=True, cascade='all, delete-orphan'))
