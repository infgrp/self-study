"""
DB 마이그레이션: Attendance 테이블에 퇴실 관련 컬럼 추가
  - checked_out_at   (DATETIME, nullable)
  - early_leave_note (VARCHAR(200), nullable)

기존 데이터는 유지됩니다. 이미 컬럼이 있으면 건너뜁니다.

실행:
    python migrate_add_checkout.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    added = []

    if not column_exists(cur, 'attendance', 'checked_out_at'):
        cur.execute("ALTER TABLE attendance ADD COLUMN checked_out_at DATETIME")
        added.append('checked_out_at')

    if not column_exists(cur, 'attendance', 'early_leave_note'):
        cur.execute("ALTER TABLE attendance ADD COLUMN early_leave_note VARCHAR(200)")
        added.append('early_leave_note')

    conn.commit()
    conn.close()

    if added:
        print(f"컬럼 추가 완료: {', '.join(added)}")
    else:
        print("이미 모든 컬럼이 존재합니다. 변경 사항 없음.")


if __name__ == '__main__':
    main()
