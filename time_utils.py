"""
HH:MM 시각 문자열 유틸리티 - 코드 전반의 시간 비교가 문자열 lexicographic 비교에 의존하므로,
모든 진입 경로(UI 입력·Excel 복원)에서 'HH:MM' 포맷을 엄격 검증해 zero-padding이 보장되도록 한다.

문자열 포맷 유지 이유: study_period_settings 테이블이 String(5)로 설계되어 있고,
전환 시 마이그레이션 영향 범위가 넓다. 대신 경계에서의 검증을 강화해 나쁜 값이 들어오지 못하게 한다.
"""

import re
from datetime import datetime, timedelta

# 24시간 HH:MM, zero-padding 강제 (00:00 ~ 23:59)
_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def is_valid_time_str(s):
    """HH:MM(24시간) 포맷인지 엄격 검증. '9:30', '25:00', '12:60' 등은 False."""
    if not s:
        return False
    return bool(_TIME_RE.match(str(s).strip()))


def parse_time_str(s):
    """HH:MM 문자열을 datetime.time으로 파싱. 형식 오류면 None을 반환."""
    if not is_valid_time_str(s):
        return None
    return datetime.strptime(str(s).strip(), '%H:%M').time()


def validate_time_str(s, label='시각'):
    """(ok: bool, err: str | None) 튜플 반환. UI·복원 핸들러에서 사용."""
    if not is_valid_time_str(s):
        return False, f'{label} 형식이 올바르지 않습니다 (HH:MM, 24시간). 입력값: {s!r}'
    return True, None


def time_add_minutes(hhmm, minutes):
    """'HH:MM' 문자열에 minutes를 더한 'HH:MM' 문자열을 반환한다 (같은 날 내 이동).
    사전 입실·퇴실 grace 계산 등 반복되는 datetime.strptime + timedelta 패턴을 대체한다.
    """
    t = parse_time_str(hhmm)
    if t is None:
        raise ValueError(f'invalid HH:MM string: {hhmm!r}')
    dt = datetime.combine(datetime.today(), t) + timedelta(minutes=minutes)
    return dt.strftime('%H:%M')
