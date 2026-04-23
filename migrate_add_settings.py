"""
DB 마이그레이션: system_settings 테이블 생성 + 기본 정책값 시드.

기존 DB(self_study.db)에 영향 없이 새 테이블만 추가한다.
이미 테이블이 있으면 누락된 키만 시드한다.

실행:
    python migrate_add_settings.py
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')

# settings.py의 SETTINGS_SCHEMA와 1:1 동기화 — 변경 시 양쪽 모두 갱신
SEED_VALUES = [
    ('early_checkin_minutes',     '30',   'int',  '사전 입실 허용 시간(분) - 교시 시작 N분 전부터 입실 QR 허용', 0, 120),
    ('checkout_grace_minutes',    '10',   'int',  '퇴실 grace 시간(분) - 교시 종료 후 N분까지 퇴실 QR 허용',   0,  60),
    ('late_threshold_minutes',    '10',   'int',  '지각 판정 시간(분) - 교시 시작 후 N분 이내는 출석, 이후는 지각', 0, 60),
    ('apply_cutoff_day',          '20',   'int',  '월별 자습 신청 마감일 - 매월 N일 이전이면 다음달 신청 가능', 1,  31),
    ('participation_rate_default','80',   'int',  '참여율 통계 기본 기준(%) - 통계 화면 첫 진입 시 기본 필터',  0, 100),
    ('password_min_length',       '8',    'int',  '비밀번호 최소 길이',                                       4,  30),
    ('password_require_mixed',    'true', 'bool', '비밀번호에 영문+숫자 혼합 강제 여부',                       None, None),
    ('temp_password_length',      '8',    'int',  '관리자가 비밀번호 초기화 시 자동 생성하는 임시 비번 길이',  6,  20),
]


def table_exists(cur, table):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        print("앱을 한 번이라도 실행하면 자동 생성됩니다.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    created = False
    if not table_exists(cur, 'system_settings'):
        cur.execute("""
            CREATE TABLE system_settings (
                key         VARCHAR(50) PRIMARY KEY,
                value       VARCHAR(200) NOT NULL,
                value_type  VARCHAR(10)  NOT NULL,
                description VARCHAR(200),
                min_value   INTEGER,
                max_value   INTEGER,
                updated_at  DATETIME,
                updated_by  INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(id)
            )
        """)
        created = True

    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    seeded = 0
    for key, value, vtype, desc, vmin, vmax in SEED_VALUES:
        cur.execute("SELECT 1 FROM system_settings WHERE key=?", (key,))
        if cur.fetchone():
            continue
        cur.execute("""
            INSERT INTO system_settings
              (key, value, value_type, description, min_value, max_value, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """, (key, value, vtype, desc, vmin, vmax, now))
        seeded += 1

    conn.commit()
    conn.close()

    if created:
        print("system_settings 테이블 생성 완료.")
    if seeded:
        print(f"기본 설정값 {seeded}개 시드 완료.")
    if not created and not seeded:
        print("이미 모든 설정이 존재합니다. 변경 사항 없음.")


if __name__ == '__main__':
    main()
