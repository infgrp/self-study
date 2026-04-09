"""
학생 기능 Blueprint - 대시보드, 시간표, 출석, 학습 기록
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, User, Schedule, Attendance, StudyLog, Holiday, StudyPeriodSetting, StudyApplication, StudentRoom, StudyRoom, AttendanceLog
from datetime import date, datetime, timedelta
import calendar

student_bp = Blueprint('student', __name__)

DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']

DAY_TYPE_LABELS = {
    'mon': '월요일', 'tue': '화요일', 'wed': '수요일',
    'thu': '목요일', 'fri': '금요일',
    'weekday': '평일', 'saturday': '토요일',
    'holiday': '공휴일', 'sunday': '일요일',
}

# 기본 자습 시간 (DB 설정이 없을 때 사용)
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
    'sunday': {}
}


WEEKDAY_CODES = ['mon', 'tue', 'wed', 'thu', 'fri']

def get_day_type(check_date):
    """날짜의 유형 반환: 'holiday', 'saturday', 'sunday', 또는 요일코드('mon'~'fri')"""
    if Holiday.query.filter_by(date=check_date).first():
        return 'holiday'
    wd = check_date.weekday()
    if wd == 5:
        return 'saturday'
    if wd == 6:
        return 'sunday'
    return WEEKDAY_CODES[wd]


def get_period_times(day_type):
    """해당 일자 유형의 자습 시간 설정 반환.
    특정 요일 설정 → 'weekday'/'saturday'/'holiday' 공통 설정 → 기본값 순으로 폴백."""
    settings = StudyPeriodSetting.query.filter_by(
        day_type=day_type, is_active=True
    ).order_by(StudyPeriodSetting.period).all()
    if settings:
        return {s.period: (s.start_time, s.end_time) for s in settings}

    # 특정 요일이면 공통 'weekday' 설정으로 폴백
    fallback = 'weekday' if day_type in WEEKDAY_CODES else day_type
    if fallback != day_type:
        settings = StudyPeriodSetting.query.filter_by(
            day_type=fallback, is_active=True
        ).order_by(StudyPeriodSetting.period).all()
        if settings:
            return {s.period: (s.start_time, s.end_time) for s in settings}

    return DEFAULT_PERIODS.get(fallback, {})


def get_holiday_name(check_date):
    """공휴일 이름 반환"""
    holiday = Holiday.query.filter_by(date=check_date).first()
    return holiday.name if holiday else None


@student_bp.before_request
@login_required
def check_student():
    if current_user.role != 'student':
        flash('학생만 접근할 수 있습니다.', 'danger')
        return redirect(url_for('auth.login'))


@student_bp.route('/')
def dashboard():
    today = date.today()
    dow = today.weekday()  # 0=월 ~ 6=일

    # 오늘 일자 유형 판별
    day_type = get_day_type(today)
    day_type_label = DAY_TYPE_LABELS[day_type]
    holiday_name = get_holiday_name(today)

    # 해당 일자 유형의 자습 시간 설정
    period_times = get_period_times(day_type)

    # 오늘 자습 신청 현황
    today_applications = {a.period: a for a in StudyApplication.query.filter_by(
        user_id=current_user.id, date=today
    ).all()}

    # 오늘 출석 현황
    today_attendance = {a.period: a for a in Attendance.query.filter_by(
        user_id=current_user.id, date=today
    ).all()}

    # 이번 달 신청 현황 요약
    first_day = date(today.year, today.month, 1)
    last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    month_applications = StudyApplication.query.filter(
        StudyApplication.user_id == current_user.id,
        StudyApplication.date >= first_day,
        StudyApplication.date <= last_day
    ).count()

    # 이번 주 학습 시간 합계
    week_start = today - timedelta(days=today.weekday())
    week_logs = StudyLog.query.filter(
        StudyLog.user_id == current_user.id,
        StudyLog.date >= week_start,
        StudyLog.date <= today
    ).all()
    total_minutes = sum(log.duration for log in week_logs)

    return render_template('student/dashboard.html',
                           today=today,
                           dow=dow,
                           day_names=DAY_NAMES,
                           day_type=day_type,
                           day_type_label=day_type_label,
                           holiday_name=holiday_name,
                           today_applications=today_applications,
                           today_attendance=today_attendance,
                           period_times=period_times,
                           month_applications=month_applications,
                           total_minutes=total_minutes)


@student_bp.route('/apply', methods=['GET', 'POST'])
def apply():
    """월별 자습 신청"""
    # 년/월 파라미터 (기본: 다음달)
    today = date.today()
    # 기본적으로 다음 달을 보여줌 (신청 마감 전이라면)
    if today.day <= 20:  # 20일 이전이면 다음달 신청 가능
        default_year = today.year if today.month < 12 else today.year + 1
        default_month = today.month + 1 if today.month < 12 else 1
    else:
        default_year = today.year
        default_month = today.month

    year = request.args.get('year', default_year, type=int)
    month = request.args.get('month', default_month, type=int)
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        month = default_month
        year = default_year

    if request.method == 'POST':
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int)

        if not year or not month or not (1 <= month <= 12) or not (2000 <= year <= 2100):
            flash('잘못된 날짜입니다.', 'danger')
            return redirect(url_for('student.apply'))

        # 해당 월의 기존 신청 삭제
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        StudyApplication.query.filter(
            StudyApplication.user_id == current_user.id,
            StudyApplication.date >= first_day,
            StudyApplication.date <= last_day
        ).delete()

        # 새 신청 저장
        applied_count = 0
        for key in request.form:
            if key.startswith('apply_'):
                parts = key.split('_')
                if len(parts) == 3:
                    try:
                        day = int(parts[1])
                        period = int(parts[2])
                    except (ValueError, IndexError):
                        continue
                    if not (1 <= day <= 31) or not (0 <= period <= 9):
                        continue
                    try:
                        apply_date = date(year, month, day)
                    except ValueError:
                        continue

                    # 일요일은 제외
                    if apply_date.weekday() == 6:
                        continue

                    # 해당 날짜의 유효 교시인지 서버에서 검증
                    day_type = get_day_type(apply_date)
                    valid_periods = get_period_times(day_type)
                    if period not in valid_periods:
                        continue

                    app = StudyApplication(
                        user_id=current_user.id,
                        date=apply_date,
                        period=period
                    )
                    db.session.add(app)
                    applied_count += 1

        db.session.commit()
        flash(f'{year}년 {month}월 자습 신청이 완료되었습니다. ({applied_count}건)', 'success')
        return redirect(url_for('student.apply', year=year, month=month))

    # 달력 데이터 생성
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    first_weekday = first_day.weekday()  # 0=월 ~ 6=일

    # 해당 월의 신청 현황
    applications = StudyApplication.query.filter(
        StudyApplication.user_id == current_user.id,
        StudyApplication.date >= first_day,
        StudyApplication.date <= last_day
    ).all()
    applied_set = {(a.date, a.period) for a in applications}

    # 공휴일 목록
    holidays = {h.date: h.name for h in Holiday.query.filter(
        Holiday.date >= first_day,
        Holiday.date <= last_day
    ).all()}

    # 각 요일별 자습 시간 (요일별 개별 설정 지원)
    period_times_by_code = {code: get_period_times(code) for code in WEEKDAY_CODES}
    period_times_weekday = period_times_by_code.get('mon') or get_period_times('weekday')
    period_times_saturday = get_period_times('saturday')
    period_times_holiday = get_period_times('holiday')

    # 달력에 표시할 날짜 목록
    cal_days = []
    for day in range(1, last_day.day + 1):
        d = date(year, month, day)
        day_type = get_day_type(d)

        if day_type in WEEKDAY_CODES:
            periods = period_times_by_code[day_type]
        elif day_type == 'saturday':
            periods = period_times_saturday
        elif day_type == 'holiday':
            periods = period_times_holiday
        else:
            periods = {}

        cal_days.append({
            'day': day,
            'date': d,
            'weekday': d.weekday(),
            'day_type': day_type,
            'holiday_name': holidays.get(d),
            'periods': periods
        })

    # 이번 달 신청 가능한 교시 전체 목록 (버튼 생성용)
    all_available_periods = sorted({p for d in cal_days for p in d['periods'].keys()})

    # 이전/다음 달
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('student/apply.html',
                           year=year,
                           month=month,
                           cal_days=cal_days,
                           first_weekday=first_weekday,
                           applied_set=applied_set,
                           day_names=DAY_NAMES,
                           prev_year=prev_year,
                           prev_month=prev_month,
                           next_year=next_year,
                           next_month=next_month,
                           period_times_weekday=period_times_weekday,
                           period_times_saturday=period_times_saturday,
                           period_times_holiday=period_times_holiday,
                           all_available_periods=all_available_periods)


@student_bp.route('/log', methods=['GET', 'POST'])
def study_log():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        duration = request.form.get('duration', type=int)
        memo = request.form.get('memo', '').strip()
        log_date_str = request.form.get('date', '')

        if not subject or not duration:
            flash('과목과 학습 시간을 입력하세요.', 'danger')
            return redirect(url_for('student.study_log'))

        if duration <= 0:
            flash('학습 시간은 1분 이상이어야 합니다.', 'danger')
            return redirect(url_for('student.study_log'))

        log_date = date.today()
        if log_date_str:
            try:
                log_date = date.fromisoformat(log_date_str)
            except ValueError:
                pass

        log = StudyLog(
            user_id=current_user.id,
            date=log_date,
            subject=subject,
            duration=duration,
            memo=memo
        )
        db.session.add(log)
        db.session.commit()
        flash('학습 기록이 저장되었습니다.', 'success')
        return redirect(url_for('student.study_log'))

    # 최근 30일 학습 기록
    since = date.today() - timedelta(days=30)
    logs = StudyLog.query.filter(
        StudyLog.user_id == current_user.id,
        StudyLog.date >= since
    ).order_by(StudyLog.date.desc(), StudyLog.id.desc()).all()

    return render_template('student/study_log.html', logs=logs, today=date.today())


@student_bp.route('/my-attendance')
def my_attendance():
    """학생 본인 월별 출결 이력 조회"""
    today = date.today()
    year  = request.args.get('year',  today.year,  type=int)
    month = request.args.get('month', today.month, type=int)
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        year, month = today.year, today.month

    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])

    # 신청 데이터
    apps = {(a.date, a.period)
            for a in StudyApplication.query.filter(
                StudyApplication.user_id == current_user.id,
                StudyApplication.date >= first_day,
                StudyApplication.date <= last_day
            ).all()}

    # 출결 데이터
    atts = {(a.date, a.period): a
            for a in Attendance.query.filter(
                Attendance.user_id == current_user.id,
                Attendance.date >= first_day,
                Attendance.date <= last_day
            ).all()}

    # 자습 시간 설정 (교시 목록용)
    all_periods = sorted({p for _, p in apps} | {p for _, p in atts}) or [1, 2, 3, 4]

    # 날짜별 데이터 구성
    days = []
    for day in range(1, last_day.day + 1):
        d = date(year, month, day)
        if d > today:
            break
        day_apps  = {p for (dd, p) in apps if dd == d}
        day_atts  = {p: atts[(d, p)] for p in all_periods if (d, p) in atts}
        if day_apps or day_atts:
            days.append({'date': d, 'apps': day_apps, 'atts': day_atts})

    # 월간 요약 통계
    total_applied     = len(apps)
    total_present     = sum(1 for a in atts.values() if a.status == 'present')
    total_late        = sum(1 for a in atts.values() if a.status == 'late')
    total_absent      = sum(1 for a in atts.values() if a.status == 'absent')
    total_early_leave = sum(1 for a in atts.values() if a.status == 'early_leave')
    total_approved    = sum(1 for a in atts.values() if a.status == 'approved_leave')
    # 출석인정(approved_leave)도 참여로 계산
    rate = round(
        (total_present + total_late + total_approved) / total_applied * 100
    ) if total_applied else 0

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    return render_template('student/my_attendance.html',
                           year=year, month=month,
                           days=days,
                           all_periods=all_periods,
                           total_applied=total_applied,
                           total_present=total_present,
                           total_late=total_late,
                           total_absent=total_absent,
                           total_early_leave=total_early_leave,
                           total_approved=total_approved,
                           rate=rate,
                           prev_year=prev_year, prev_month=prev_month,
                           next_year=next_year, next_month=next_month)


@student_bp.route('/qr-attend/<token>', methods=['GET', 'POST'])
def qr_attend(token):
    """QR코드를 통한 출석 체크"""
    # 토큰으로 자습 공간 조회
    room = StudyRoom.query.filter_by(qr_token=token).first()
    if not room:
        flash('유효하지 않은 QR코드입니다.', 'danger')
        return redirect(url_for('student.dashboard'))

    if request.method == 'GET':
        return render_template('student/qr_confirm.html', room=room, token=token, action='attend')

    # POST: 출석 처리
    today = date.today()
    now = datetime.now()

    # 배정된 자습실 확인 (다른 방 QR 차단)
    assigned = StudentRoom.query.filter_by(user_id=current_user.id, study_room_id=room.id).first()
    if not assigned:
        flash(f'해당 자습실({room.name})에 배정된 학생이 아닙니다.', 'danger')
        return redirect(url_for('student.dashboard'))

    # 오늘 일자 유형 및 자습 시간 확인
    day_type = get_day_type(today)
    period_times = get_period_times(day_type)

    if not period_times:
        flash('오늘은 자습이 없는 날입니다.', 'warning')
        return redirect(url_for('student.dashboard'))

    # 오늘 이 학생의 자습 신청 교시 집합
    applied_periods = {
        a.period for a in StudyApplication.query.filter_by(
            user_id=current_user.id, date=today
        ).all()
    }

    if not applied_periods:
        flash('오늘 자습을 신청하지 않았습니다.', 'warning')
        return redirect(url_for('student.dashboard'))

    # 현재 시간에 해당하는 교시 찾기 (진행 중 → 시작 전 순으로)
    current_time = now.strftime('%H:%M')
    current_period = None
    early = False  # 교시 시작 전 사전 입실 여부

    # 1순위: 현재 진행 중인 교시 중 학생이 신청한 교시
    for period, (start, end) in sorted(period_times.items()):
        if start <= current_time <= end and period in applied_periods:
            current_period = period
            break

    # 2순위: 아직 시작 안 한 교시 중 학생이 신청한 가장 빠른 교시 (사전 입실, 시작 30분 전부터 허용)
    EARLY_CHECKIN_MINUTES = 30
    if current_period is None:
        upcoming = [
            (p, s) for p, (s, e) in sorted(period_times.items())
            if current_time < s and p in applied_periods
            and (datetime.strptime(s, '%H:%M') - timedelta(minutes=EARLY_CHECKIN_MINUTES)).strftime('%H:%M') <= current_time
        ]
        if upcoming:
            current_period, _ = upcoming[0]
            early = True

    if current_period is None:
        flash('현재 출석할 수 있는 교시가 없습니다. (자습 시간이 모두 지났거나 미신청)', 'warning')
        return redirect(url_for('student.dashboard'))

    # 기존 출결 레코드 확인
    existing = Attendance.query.filter_by(
        user_id=current_user.id, date=today, period=current_period
    ).first()

    start_str = period_times[current_period][0]

    if existing:
        if existing.status == 'late' and existing.checked_at is None:
            # 자동처리로 지각 기록됐지만 실제 QR 미스캔 → 입실 시각 기록, 지각 유지
            existing.checked_at = now
            existing.study_room_id = room.id
            db.session.flush()
            db.session.add(AttendanceLog(
                attendance_id=existing.id,
                changed_by=None,
                old_status='late',
                new_status='late',
                note='QR입실(자동지각 후 입실)',
            ))
            db.session.commit()
            flash(f'{room.name}에서 {current_period}교시 지각 처리되었습니다.', 'warning')
        elif existing.status in ('present', 'late', 'approved_leave'):
            flash(f'{current_period}교시 출석은 이미 완료되었습니다.', 'info')
        elif existing.status in ('absent', 'early_leave'):
            # 자동처리로 지각/결석 처리됐거나 조퇴 후 재입실 → 출석으로 갱신
            old_status = existing.status
            existing.status = 'present'
            existing.checked_at = now
            existing.study_room_id = room.id
            db.session.flush()
            db.session.add(AttendanceLog(
                attendance_id=existing.id,
                changed_by=None,
                old_status=old_status,
                new_status='present',
                note='QR입실(재처리)',
            ))
            db.session.commit()
            flash(f'{room.name}에서 {current_period}교시 출석 처리되었습니다.', 'success')
        else:
            flash(f'{current_period}교시 출석은 이미 완료되었습니다.', 'info')
    else:
        att = Attendance(
            user_id=current_user.id,
            date=today,
            period=current_period,
            status='present',
            study_room_id=room.id,
            checked_at=now
        )
        db.session.add(att)
        db.session.commit()
        if early:
            flash(f'{room.name}에서 {current_period}교시 사전 입실 완료 (시작: {start_str}).', 'success')
        else:
            flash(f'{room.name}에서 {current_period}교시 출석이 완료되었습니다.', 'success')

    return redirect(url_for('student.dashboard'))


@student_bp.route('/qr-checkout/<token>', methods=['GET', 'POST'])
def qr_checkout(token):
    """QR코드를 통한 퇴실 체크 — 종료시간 전 퇴실 시 조퇴 처리"""
    # 토큰으로 자습 공간 확인
    room = StudyRoom.query.filter_by(qr_token=token).first()
    if not room:
        flash('유효하지 않은 QR코드입니다.', 'danger')
        return redirect(url_for('student.dashboard'))

    if request.method == 'GET':
        return render_template('student/qr_confirm.html', room=room, token=token, action='checkout')

    # POST: 퇴실 처리
    today = date.today()
    now = datetime.now()

    # 오늘 자습 시간 확인
    day_type = get_day_type(today)
    period_times = get_period_times(day_type)
    if not period_times:
        flash('오늘은 자습이 없는 날입니다.', 'warning')
        return redirect(url_for('student.dashboard'))

    # 퇴실 허용 여유 시간 (교시 종료 후 N분까지 퇴실 QR 허용)
    CHECKOUT_GRACE_MINUTES = 10

    # 현재 진행 중이거나 종료 후 여유 시간 내인 교시 찾기
    current_time = now.strftime('%H:%M')
    current_period = None
    period_end_time = None
    for period, (start, end) in sorted(period_times.items()):
        grace_end = (datetime.strptime(end, '%H:%M') + timedelta(minutes=CHECKOUT_GRACE_MINUTES)).strftime('%H:%M')
        if start <= current_time <= grace_end:
            current_period = period
            period_end_time = end
            break

    if current_period is None:
        flash('퇴실 처리 가능한 교시가 없습니다. (자습 시간 종료 10분 후까지만 퇴실 QR이 동작합니다.)', 'warning')
        return redirect(url_for('student.dashboard'))

    # 입실 출석 기록 확인
    att = Attendance.query.filter_by(
        user_id=current_user.id, date=today, period=current_period
    ).first()

    if not att:
        flash(f'{current_period}교시 입실 기록이 없습니다. 먼저 입실 QR코드를 스캔하세요.', 'warning')
        return redirect(url_for('student.dashboard'))

    # 입실한 자습실과 현재 QR 자습실이 다르면 거부
    # (study_room_id가 None인 경우 = 자동처리 학생 → 현재 배정 자습실 확인)
    if att.study_room_id is not None and att.study_room_id != room.id:
        flash('입실할 때 스캔한 자습실의 QR코드를 사용하세요.', 'danger')
        return redirect(url_for('student.dashboard'))
    assigned = StudentRoom.query.filter_by(user_id=current_user.id).first()
    if att.study_room_id is None and assigned and assigned.study_room_id != room.id:
        flash(f'배정된 자습실({room.name})의 QR코드를 사용하세요.', 'danger')
        return redirect(url_for('student.dashboard'))

    # 퇴실 시각 갱신 (재스캔 시 최종 스캔 시각으로 업데이트)
    already_checked_out = att.checked_out_at is not None
    att.checked_out_at = now

    # 실측 자습시간 계산 (입실 시각이 있을 때만)
    if att.checked_at:
        att.study_minutes = max(0, int((now - att.checked_at).total_seconds() // 60))

    # 종료 시각 이전이면 조퇴, 이후(정상 퇴실 또는 여유 시간 내)면 출석
    is_early_leave = current_time < period_end_time

    if is_early_leave:
        # 조퇴 — 이미 조퇴/출석인정 상태면 상태는 그대로, 퇴실 시각만 갱신
        if att.status not in ('early_leave', 'approved_leave'):
            old_status = att.status
            att.status = 'early_leave'
            db.session.flush()
            db.session.add(AttendanceLog(
                attendance_id=att.id,
                changed_by=None,
                old_status=old_status,
                new_status='early_leave',
                note='조퇴(QR퇴실)',
            ))
        db.session.commit()
        flash(
            f'{current_period}교시 조퇴 처리되었습니다. '
            f'퇴실 시각: {now.strftime("%H:%M")} '
            f'(종료: {period_end_time}) — 담당 교사가 사유 확인 후 출석인정 가능합니다.',
            'warning',
        )
    else:
        # 정상 퇴실 — 이전에 조퇴로 처리됐으면 present로 복원
        if att.status == 'early_leave':
            old_status = att.status
            att.status = 'present'
            db.session.flush()
            db.session.add(AttendanceLog(
                attendance_id=att.id,
                changed_by=None,
                old_status=old_status,
                new_status='present',
                note='조퇴→출석(QR재스캔)',
            ))
        db.session.commit()
        if already_checked_out:
            flash(f'{current_period}교시 퇴실 시각이 갱신되었습니다. ({now.strftime("%H:%M")})', 'success')
        else:
            flash(f'{current_period}교시 퇴실이 확인되었습니다. ({now.strftime("%H:%M")})', 'success')

    return redirect(url_for('student.dashboard'))


@student_bp.route('/mypage', methods=['GET', 'POST'])
@login_required
def mypage():
    """학생 마이페이지 - 내 정보 수정 / 비밀번호 변경"""
    if request.method == 'POST':
        action = request.form.get('action', 'password')

        if action == 'profile':
            # 학번 / 성별 수정
            new_student_id = request.form.get('student_id', '').strip()
            new_gender     = request.form.get('gender', '').strip()

            if new_student_id:
                # 형식 검사: 숫자 5자리
                if not (len(new_student_id) == 5 and new_student_id.isdigit()):
                    flash('학번은 숫자 5자리여야 합니다.', 'danger')
                    return render_template('student/mypage.html')
                # 중복 확인 (본인 제외)
                dup = User.query.filter(
                    User.student_id == new_student_id,
                    User.id != current_user.id
                ).first()
                if dup:
                    flash('이미 사용 중인 학번입니다.', 'danger')
                    return render_template('student/mypage.html')
                current_user.student_id = new_student_id

            if new_gender in ('M', 'F'):
                current_user.gender = new_gender

            db.session.commit()
            flash('정보가 수정되었습니다.', 'success')
            return redirect(url_for('student.mypage'))

        # 비밀번호 변경
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('현재 비밀번호가 올바르지 않습니다.', 'danger')
            return render_template('student/mypage.html')

        if new_pw != confirm_pw:
            flash('새 비밀번호가 일치하지 않습니다.', 'danger')
            return render_template('student/mypage.html')

        if len(new_pw) < 8 or not any(c.isdigit() for c in new_pw) \
                or not any(c.isalpha() for c in new_pw):
            flash('새 비밀번호는 8자 이상, 영문+숫자를 포함해야 합니다.', 'danger')
            return render_template('student/mypage.html')

        current_user.set_password(new_pw)
        db.session.commit()
        flash('비밀번호가 변경되었습니다. 다시 로그인해 주세요.', 'success')
        return redirect(url_for('student.dashboard'))

    return render_template('student/mypage.html')
