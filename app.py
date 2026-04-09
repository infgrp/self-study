"""
고등학생 자율학습 관리 시스템
Flask 웹 애플리케이션 진입점
"""

import os
import sqlite3
from datetime import timedelta, date, datetime
from flask import Flask, redirect, url_for, session as flask_session
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from models import db, User, StudyPeriodSetting
from sqlalchemy import event
from sqlalchemy.engine import Engine


# 기본 자습 시간 설정 (period -> (start_time, end_time))
DEFAULT_PERIODS = {
    'weekday': {
        0: ('07:30', '08:30'),
        1: ('18:00', '19:00'),
        2: ('19:10', '20:10'),
        3: ('20:20', '21:20'),
        4: ('21:30', '22:30'),
    },
    'saturday': {
        1: ('09:00', '10:00'),
        2: ('10:10', '11:10'),
        3: ('11:20', '12:20'),
    },
    'holiday': {
        1: ('09:00', '10:00'),
        2: ('10:10', '11:10'),
    },
}


def init_default_period_settings():
    """기본 자습 시간 설정을 DB에 초기화"""
    for day_type, periods in DEFAULT_PERIODS.items():
        for period, (start_time, end_time) in periods.items():
            # 이미 설정이 있는지 확인
            existing = StudyPeriodSetting.query.filter_by(
                day_type=day_type, period=period
            ).first()

            if not existing:
                setting = StudyPeriodSetting(
                    day_type=day_type,
                    period=period,
                    start_time=start_time,
                    end_time=end_time,
                    is_active=True
                )
                db.session.add(setting)

    db.session.commit()


@event.listens_for(Engine, 'connect')
def _set_sqlite_pragmas(dbapi_conn, _):
    """SQLite 연결마다 FK 강제 + WAL 모드 활성화"""
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA foreign_keys = ON')
        cur.execute('PRAGMA journal_mode = WAL')
        cur.close()


def create_app():
    app = Flask(__name__)

    # 설정
    basedir = os.path.abspath(os.path.dirname(__file__))
    secret_key_file = os.path.join(basedir, 'instance', 'secret_key.txt')
    if os.path.exists(secret_key_file):
        with open(secret_key_file) as f:
            secret_key = f.read().strip()
    else:
        secret_key = os.urandom(24).hex()
        os.makedirs(os.path.dirname(secret_key_file), exist_ok=True)
        with open(secret_key_file, 'w') as f:
            f.write(secret_key)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secret_key)
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        'sqlite:///' + os.path.join(basedir, 'instance', 'self_study.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # 세션 보안 설정
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)  # 12시간 후 자동 만료
    app.config['SESSION_COOKIE_HTTPONLY'] = True   # JS에서 세션 쿠키 접근 차단
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF 방어

    # instance 폴더 생성
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

    # DB 초기화
    db.init_app(app)

    # CSRF 보호
    CSRFProtect(app)

    # Flask-Login 설정
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요합니다.'
    login_manager.session_protection = 'basic'  # 브라우저 변경 시 세션 재발급
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(username):
        # username 기반 조회 (숫자 PK 의존 제거)
        user = User.query.filter_by(username=username).first()
        if user is None:
            return None
        # session_token 검증: DB 교체·복원 시 UUID가 달라지므로 기존 세션 즉시 차단
        if flask_session.get('_session_token') != user.session_token:
            return None
        return user

    # Blueprint 등록
    from auth import auth_bp
    from routes_student import student_bp
    from routes_teacher import teacher_bp
    from routes_admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # 메인 페이지 -> 로그인으로 리다이렉트
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # DB 테이블 생성 및 기본 설정 초기화
    with app.app_context():
        db.create_all()
        init_default_period_settings()
        _init_admin_account()

    # 야간 자동 조퇴 처리 스케줄러 시작
    _start_scheduler(app)

    return app


def _init_admin_account():
    """관리자 계정이 없으면 기본 admin 계정을 생성한다."""
    if User.query.filter_by(role='admin').first():
        return  # 이미 관리자 존재

    default_password = 'Admin1234!'
    admin = User(
        username='admin',
        name='관리자',
        role='admin',
        is_approved=True,
    )
    admin.set_password(default_password)
    db.session.add(admin)
    db.session.commit()

    print("\n" + "=" * 50)
    print("  [관리자 계정 자동 생성]")
    print(f"  아이디: admin")
    print(f"  비밀번호: {default_password}")
    print("  ※ 첫 로그인 후 반드시 비밀번호를 변경하세요!")
    print("=" * 50 + "\n")


def _auto_early_leave(app):
    """매일 23:59 — 입실 QR을 찍었지만 퇴실 QR을 찍지 않은 학생을 조퇴로 처리."""
    from models import Attendance, AttendanceLog
    with app.app_context():
        today = date.today()
        changed = 0
        try:
            targets = Attendance.query.filter(
                Attendance.date == today,
                Attendance.status == 'present',
                Attendance.checked_at.isnot(None),
                Attendance.checked_out_at.is_(None),
            ).all()
            for att in targets:
                att.status = 'early_leave'
                att.checked_out_at = datetime.combine(today, datetime.strptime('23:59', '%H:%M').time())
                att.early_leave_note = (att.early_leave_note or '') or '퇴실미확인(자동)'
                db.session.add(AttendanceLog(
                    attendance_id=att.id,
                    changed_by=None,
                    old_status='present',
                    new_status='early_leave',
                    note='퇴실미확인(자동)',
                ))
                changed += 1
            db.session.commit()
            if changed:
                print(f'[스케줄러] {today} 퇴실 미확인 {changed}명 → 조퇴 처리')
        except Exception as e:
            db.session.rollback()
            print(f'[스케줄러] 자동 조퇴 처리 오류: {e}')


def _start_scheduler(app):
    """APScheduler로 매일 23:59에 자동 조퇴 처리 잡을 등록한다.
    waitress는 단일 프로세스이므로 스케줄러가 중복 실행되지 않는다."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(timezone='Asia/Seoul')
        scheduler.add_job(
            _auto_early_leave,
            trigger='cron',
            hour=23, minute=59,
            args=[app],
            id='auto_early_leave',
            replace_existing=True,
        )
        scheduler.start()
    except Exception as e:
        print(f'[경고] 스케줄러 시작 실패: {e}')


def _get_lan_ip():
    """LAN 인터페이스의 실제 IP를 반환한다.
    gethostbyname(hostname)은 루프백이나 엉뚱한 주소를 돌려줄 수 있으므로,
    외부 연결 시도 소켓으로 라우팅되는 인터페이스 IP를 읽는다."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))   # 실제 패킷 전송 없음, 라우팅만 확인
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    from waitress import serve
    app = create_app()
    lan_ip = _get_lan_ip()
    print("=" * 50)
    print("  자율학습 관리 시스템")
    print(f"  http://{lan_ip}:5000  ← 학생/교사 모두 이 주소로 접속")
    print("=" * 50)
    serve(app, host='0.0.0.0', port=5000, threads=4)
