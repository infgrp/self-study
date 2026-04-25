"""
DB 마이그레이션: student_rooms 테이블의 UNIQUE(study_room_id, seat_number) 제약 제거.

배경:
  migrate_add_constraints_v2.py에서 좌석 중복 방지 목적으로 추가했으나,
  실제 자습실은 남학생 zone과 여학생 zone이 물리적으로 분리돼 있어
  '남학생 1번'과 '여학생 1번'이 서로 다른 좌석을 의미한다.
  (room, seat)만으로는 zone을 표현할 수 없으므로 정상 배정도 IntegrityError로
  거부되어, 남녀 혼합 자습실에서 좌석 배정이 불가능해진다.

  zone 내 중복 방지는 코드 레벨(random.sample, used_m/used_f set)이 담당하므로
  DB 제약은 제거하는 것이 옳다.

동작:
  1. uq_room_seat 제약 존재 여부 확인 (멱등)
  2. 있으면 student_rooms 테이블을 제약 없이 재구축
  3. FK 무결성 검사

실행:
    python migrate_drop_room_seat_uq.py
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    try:
        # 현재 student_rooms의 CREATE 문 확인
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='student_rooms'")
        row = cur.fetchone()
        if not row or not row[0]:
            print("student_rooms 테이블이 존재하지 않습니다.")
            sys.exit(2)

        if 'uq_room_seat' not in row[0]:
            print("uq_room_seat 제약이 이미 없습니다 - 변경 사항 없음.")
            sys.exit(0)

        print("[1/2] student_rooms 재구축 (uq_room_seat 제약 제거)...")
        cur.execute("BEGIN")
        cur.execute("DROP TABLE IF EXISTS student_rooms_new")
        cur.execute("""
            CREATE TABLE student_rooms_new (
                id            INTEGER PRIMARY KEY,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                study_room_id INTEGER NOT NULL REFERENCES study_rooms(id),
                seat_number   INTEGER,
                pos_x         REAL,
                pos_y         REAL,
                CONSTRAINT uq_user_room UNIQUE (user_id)
            )
        """)
        cur.execute("""
            INSERT INTO student_rooms_new (id, user_id, study_room_id, seat_number, pos_x, pos_y)
            SELECT id, user_id, study_room_id, seat_number, pos_x, pos_y
            FROM student_rooms
        """)
        cur.execute("DROP TABLE student_rooms")
        cur.execute("ALTER TABLE student_rooms_new RENAME TO student_rooms")
        conn.commit()

        print("[2/2] FK 무결성 검사...")
        conn.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA foreign_key_check")
        bad = cur.fetchall()
        if bad:
            print(f"  [X] FK 위반: {bad}")
            sys.exit(3)
        print("  [OK]")
        print("\n마이그레이션 완료.")
    except Exception as e:
        conn.rollback()
        print(f"\n오류 발생, 롤백됨: {e}")
        sys.exit(4)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
