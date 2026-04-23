"""
날짜 유형 분류 유틸 - 달력 루프 등에서 반복 호출될 때 Holiday 조회로 인한
N+1 쿼리를 피할 수 있도록 선택적 캐시 파라미터를 지원한다.
"""

from models import Holiday
from constants import WEEKDAY_CODES


def get_day_type(check_date, holidays_cache=None):
    """날짜의 유형을 반환한다.
      - 'holiday'            : 등록된 공휴일
      - 'saturday'           : 토요일
      - 'sunday'             : 일요일
      - 'mon' ~ 'fri'        : 평일 요일 코드

    holidays_cache: {date: name} 딕셔너리. 제공되면 DB 조회 없이 dict lookup 사용.
    달력 렌더링처럼 여러 날짜를 순회할 때 호출부에서 공휴일을 한 번만 로드해
    이 함수에 전달하면 N+1 쿼리를 피할 수 있다.
    """
    if holidays_cache is not None:
        is_holiday = check_date in holidays_cache
    else:
        is_holiday = Holiday.query.filter_by(date=check_date).first() is not None

    if is_holiday:
        return 'holiday'
    wd = check_date.weekday()
    if wd == 5:
        return 'saturday'
    if wd == 6:
        return 'sunday'
    return WEEKDAY_CODES[wd]


def get_holiday_name(check_date, holidays_cache=None):
    """공휴일 이름 반환. 아니면 None."""
    if holidays_cache is not None:
        return holidays_cache.get(check_date)
    holiday = Holiday.query.filter_by(date=check_date).first()
    return holiday.name if holiday else None
