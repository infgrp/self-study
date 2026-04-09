"""
인증 Blueprint - 로그인, 로그아웃, 회원가입
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required
from urllib.parse import urlparse
from models import db, User

auth_bp = Blueprint('auth', __name__)


def is_safe_url(target):
    """리다이렉트 URL이 안전한지 확인 (같은 서버인지)"""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    # 상대 경로이거나 같은 서버인 경우만 허용
    return (test_url.scheme in ('', 'http', 'https') and
            (test_url.netloc == '' or ref_url.netloc == test_url.netloc))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # next 파라미터 (QR코드 스캔 등에서 로그인 후 돌아갈 URL)
    next_page = request.args.get('next')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        next_page = request.form.get('next') or next_page

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            # 교사 계정 승인 여부 확인 (미승인 교사는 로그인 불가)
            if user.role == 'teacher' and not user.is_approved:
                flash('계정 승인 대기 중입니다. 관리자에게 문의하세요.', 'warning')
                return render_template('pending_approval.html')

            session.clear()      # 이전 세션(다른 사용자 잔존 세션 포함) 완전 삭제
            session.permanent = True  # PERMANENT_SESSION_LIFETIME 적용 (12시간)
            session['_session_token'] = user.session_token  # DB 교체 감지용 토큰
            login_user(user)

            # next 파라미터가 있고 안전한 URL이면 해당 페이지로 이동
            if next_page and is_safe_url(next_page):
                return redirect(next_page)

            # 역할별 기본 리다이렉트
            if user.role == 'admin':
                return redirect(url_for('admin_bp.dashboard'))
            if user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            return redirect(url_for('student.dashboard'))

        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')

    return render_template('login.html', next=next_page)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        name = request.form.get('name', '').strip()
        role = request.form.get('role', 'student')
        if role not in ('student', 'teacher'):
            role = 'student'
        grade = request.form.get('grade', type=int)
        class_num = request.form.get('class_num', type=int)
        gender = request.form.get('gender', 'M')  # 'M' or 'F'
        student_id = request.form.get('student_id', '').strip()
        assigned_grade = request.form.get('assigned_grade', type=int)  # 교사 담당 학년

        if not username or not password or not name:
            flash('모든 필수 항목을 입력하세요.', 'danger')
            return render_template('register.html')

        # 비밀번호 확인
        if password != password_confirm:
            flash('비밀번호가 일치하지 않습니다.', 'danger')
            return render_template('register.html')

        # 비밀번호 안전성 검사
        if len(password) < 8:
            flash('비밀번호는 8자 이상이어야 합니다.', 'danger')
            return render_template('register.html')

        if not any(c.isdigit() for c in password):
            flash('비밀번호에 숫자가 포함되어야 합니다.', 'danger')
            return render_template('register.html')

        if not any(c.isalpha() for c in password):
            flash('비밀번호에 영문자가 포함되어야 합니다.', 'danger')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('이미 사용 중인 아이디입니다.', 'danger')
            return render_template('register.html')

        # 학번 유효성 검사 (학생만)
        if role == 'student':
            if not student_id.isdigit() or len(student_id) != 5:
                flash('학번은 숫자 5자리로 입력하세요.', 'danger')
                return render_template('register.html')
            if User.query.filter_by(student_id=student_id).first():
                flash('이미 등록된 학번입니다.', 'danger')
                return render_template('register.html')

        user = User(
            username=username,
            name=name,
            role=role,
            grade=grade if role == 'student' else None,
            class_num=class_num if role == 'student' else None,
            gender=gender if role == 'student' else None,
            student_id=student_id if role == 'student' else None,
            assigned_grade=assigned_grade if role == 'teacher' else None,
            # 교사는 관리자 승인 전까지 접근 불가
            is_approved=(role == 'student')
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if role == 'teacher':
            flash('회원가입이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.', 'info')
        else:
            flash('회원가입이 완료되었습니다. 로그인하세요.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('auth.login'))
