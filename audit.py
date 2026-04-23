"""
구조화된 감사 로그 - 인증, 관리자 작업, DB 복원 등 추적 대상 이벤트를 기록한다.

기본 대상: logs/audit.log (회전, 5MB x 5개). create_app()에서 설정된다.

사용:
    from audit import log_audit
    log_audit('auth.login_success', user=username)
    log_audit('admin.pw_reset', admin=current_user.username, target=user.username)
"""

import logging

_AUDIT_LOGGER_NAME = 'self_study.audit'


def log_audit(event, level='info', **fields):
    """감사 이벤트를 기록한다.
      event   : 점 구분 이벤트 키 (예: 'auth.login_success')
      level   : 'info' | 'warning' | 'error'
      fields  : 임의 키/값 쌍 (user=..., target=..., ip=...)
    """
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    # key=value 포맷이 grep하기 쉽다
    tail = ' '.join(f'{k}={v}' for k, v in fields.items() if v is not None)
    message = f'{event} {tail}'.strip()
    if level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)
    else:
        logger.info(message)
