"""
시스템 설정 접근자 - SystemSetting 테이블에서 운영 정책값을 읽고 캐스팅한다.

DB 조회 실패 / 값 형식 오류 시 항상 default를 반환한다.
캐싱하지 않으므로 관리자가 변경 즉시 반영된다.
"""

from models import db, SystemSetting


# ── 설정 스키마 ────────────────────────────────────────────────
# 키, 기본값(문자열), 타입, 설명, 검증 범위(int 한정)
SETTINGS_SCHEMA = [
    {
        'key': 'early_checkin_minutes', 'default': '30', 'type': 'int',
        'min': 0, 'max': 120,
        'description': '사전 입실 허용 시간(분) - 교시 시작 N분 전부터 입실 QR 허용',
    },
    {
        'key': 'checkout_grace_minutes', 'default': '10', 'type': 'int',
        'min': 0, 'max': 60,
        'description': '퇴실 grace 시간(분) - 교시 종료 후 N분까지 퇴실 QR 허용',
    },
    {
        'key': 'late_threshold_minutes', 'default': '10', 'type': 'int',
        'min': 0, 'max': 60,
        'description': '지각 판정 시간(분) - 교시 시작 후 N분 이내는 출석, 이후는 지각',
    },
    {
        'key': 'apply_cutoff_day', 'default': '20', 'type': 'int',
        'min': 1, 'max': 31,
        'description': '월별 자습 신청 마감일 - 매월 N일 이전이면 다음달 신청 가능',
    },
    {
        'key': 'participation_rate_default', 'default': '80', 'type': 'int',
        'min': 0, 'max': 100,
        'description': '참여율 통계 기본 기준(%) - 통계 화면 첫 진입 시 기본 필터',
    },
    {
        'key': 'password_min_length', 'default': '8', 'type': 'int',
        'min': 4, 'max': 30,
        'description': '비밀번호 최소 길이',
    },
    {
        'key': 'password_require_mixed', 'default': 'true', 'type': 'bool',
        'min': None, 'max': None,
        'description': '비밀번호에 영문+숫자 혼합 강제 여부',
    },
    {
        'key': 'temp_password_length', 'default': '8', 'type': 'int',
        'min': 6, 'max': 20,
        'description': '관리자가 비밀번호 초기화 시 자동 생성하는 임시 비번 길이',
    },
]

_DEFAULTS = {s['key']: s['default'] for s in SETTINGS_SCHEMA}


def _get_raw(key):
    s = SystemSetting.query.filter_by(key=key).first()
    return s.value if s else None


def get_int(key, default=None):
    raw = _get_raw(key)
    if raw is None:
        raw = _DEFAULTS.get(key, default)
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def get_bool(key, default=False):
    raw = _get_raw(key)
    if raw is None:
        raw = _DEFAULTS.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ('true', '1', 'yes', 'on')


def get_str(key, default=''):
    raw = _get_raw(key)
    if raw is None:
        return _DEFAULTS.get(key, default)
    return raw


def init_default_settings():
    """앱 시작 시 SystemSetting에 누락된 키를 기본값으로 시드한다."""
    for spec in SETTINGS_SCHEMA:
        existing = SystemSetting.query.filter_by(key=spec['key']).first()
        if existing:
            # 메타데이터(설명·범위·타입)는 코드가 항상 우선
            existing.value_type  = spec['type']
            existing.description = spec['description']
            existing.min_value   = spec['min']
            existing.max_value   = spec['max']
        else:
            db.session.add(SystemSetting(
                key=spec['key'],
                value=spec['default'],
                value_type=spec['type'],
                description=spec['description'],
                min_value=spec['min'],
                max_value=spec['max'],
            ))
    db.session.commit()
