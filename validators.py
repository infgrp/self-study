"""
공통 검증 함수 - 비밀번호·학번 등 여러 라우트에서 중복되던 규칙을 일원화.

각 함수는 (ok: bool, error_message: str | None) 튜플을 반환한다.
"""

import secrets
import string

import settings
from constants import STUDENT_ID_LENGTH


def validate_password(password):
    """비밀번호 정책 검증. 정책값은 SystemSetting에서 읽는다."""
    min_length = settings.get_int('password_min_length', 8)
    require_mixed = settings.get_bool('password_require_mixed', True)

    if not password or len(password) < min_length:
        return False, f'비밀번호는 {min_length}자 이상이어야 합니다.'

    if require_mixed:
        has_digit = any(c.isdigit() for c in password)
        has_alpha = any(c.isalpha() for c in password)
        if not has_digit:
            return False, '비밀번호에 숫자가 포함되어야 합니다.'
        if not has_alpha:
            return False, '비밀번호에 영문자가 포함되어야 합니다.'

    return True, None


def validate_student_id(student_id):
    """학번 형식 검증 (숫자 N자리)."""
    sid = (student_id or '').strip()
    if not sid.isdigit() or len(sid) != STUDENT_ID_LENGTH:
        return False, f'학번은 숫자 {STUDENT_ID_LENGTH}자리여야 합니다.'
    return True, None


def generate_temp_password():
    """관리자 비밀번호 초기화용 임시 비번 생성 (영문+숫자 혼합)."""
    length = settings.get_int('temp_password_length', 8)
    chars = string.ascii_letters + string.digits
    while True:
        pw = ''.join(secrets.choice(chars) for _ in range(length))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw
