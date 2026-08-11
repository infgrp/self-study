"""
DB 마이그레이션: 핵심 조회 컬럼에 인덱스 추가.

models.py에 index=True를 추가해도 db.create_all()은 기존 테이블에
인덱스를 생성하지 않는다. 이 스크립트를 1회 실행해야 실제 DB에 반영된다.

모든 CREATE INDEX는 IF NOT EXISTS 로 작성되어 중복 실행해도 안전하다.

실행:
    python migrate_add_indexes.py
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')

INDEXES = [
    # (인덱스명, 테이블, 컬럼)
    ('ix_schedules_user_id',           'schedules',          'user_id'),
    ('ix_schedules_day_of_week',       'schedules',          'day_of_week'),
    ('ix_attendance_user_id',          'attendance',         'user_id'),
    ('ix_attendance_date',             'attendance',         'date'),
    ('ix_study_logs_user_id',          'study_logs',         'user_id'),
    ('ix_study_logs_date',             'study_logs',         'date'),
    ('ix_student_rooms_user_id',       'student_rooms',      'user_id'),
    ('ix_student_rooms_study_room_id', 'student_rooms',      'study_room_id'),
    ('ix_study_applications_user_id',  'study_applications', 'user_id'),
    ('ix_study_applications_date',     'study_applications', 'date'),
]


def index_exists(cur, index_name):
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cur.fetchone() is not None


def main():
    if not os.path.exists(DB_PATH):
        print(f'DB 파일을 찾을 수 없습니다: {DB_PATH}')
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    created = 0
    skipped = 0
    for idx_name, table, column in INDEXES:
        if index_exists(cur, idx_name):
            print(f'  건너뜀 (이미 존재): {idx_name}')
            skipped += 1
        else:
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})'
            )
            print(f'  생성: {idx_name} ON {table}({column})')
            created += 1

    conn.commit()
    conn.close()

    print()
    print(f'완료: {created}개 생성, {skipped}개 건너뜀')


if __name__ == '__main__':
    main()
