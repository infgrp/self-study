"""
통합 DB 마이그레이션 스크립트 — 순서대로 실행해도 안전 (멱등)

실행:
    python migrate.py

적용 내용:
    1. attendance 테이블: checked_out_at, early_leave_note, study_minutes 컬럼 추가
    2. users 테이블: student_id UNIQUE 제약 추가
    3. attendance 테이블: (user_id, date, period) UNIQUE 제약 추가
    4. study_rooms 테이블: name UNIQUE 제약 추가
    5. users 테이블: session_token 컬럼 추가 (세션 보안 강화)
    6. schedules 테이블: (user_id, day_of_week, period) UNIQUE 제약 추가
"""

import sqlite3
import os
import uuid

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, 'instance', 'self_study.db')


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def index_exists(cur, index_name):
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
    return cur.fetchone() is not None


def migrate():
    if not os.path.exists(DB_PATH):
        print(f'DB 파일을 찾을 수 없습니다: {DB_PATH}')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = OFF')
    conn.execute('PRAGMA journal_mode = WAL')

    try:
        # ── 1. attendance 컬럼 추가 (ALTER TABLE — 기존 데이터 유지) ──
        print('[1/4] attendance 컬럼 확인...')
        cur = conn.cursor()
        added = []
        if not column_exists(cur, 'attendance', 'checked_out_at'):
            conn.execute('ALTER TABLE attendance ADD COLUMN checked_out_at DATETIME')
            added.append('checked_out_at')
        if not column_exists(cur, 'attendance', 'early_leave_note'):
            conn.execute('ALTER TABLE attendance ADD COLUMN early_leave_note VARCHAR(200)')
            added.append('early_leave_note')
        if not column_exists(cur, 'attendance', 'study_minutes'):
            conn.execute('ALTER TABLE attendance ADD COLUMN study_minutes INTEGER')
            added.append('study_minutes')
        if added:
            print(f'  컬럼 추가: {", ".join(added)}')
        else:
            print('  변경 없음.')

        # ── 2. users 테이블: student_id UNIQUE ──
        print('[2/4] users 테이블 UNIQUE 제약 확인...')
        if not index_exists(cur, 'uq_users_student_id'):
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    username        VARCHAR(50) NOT NULL UNIQUE,
                    password_hash   VARCHAR(200) NOT NULL,
                    name            VARCHAR(50) NOT NULL,
                    role            VARCHAR(10) NOT NULL,
                    grade           INTEGER,
                    class_num       INTEGER,
                    gender          VARCHAR(1),
                    student_id      VARCHAR(5) UNIQUE,
                    assigned_grade  INTEGER,
                    is_approved     BOOLEAN NOT NULL DEFAULT 1
                )
            ''')
            conn.execute('''
                INSERT OR IGNORE INTO users_new
                    (id, username, password_hash, name, role, grade, class_num,
                     gender, student_id, assigned_grade, is_approved)
                SELECT id, username, password_hash, name, role, grade, class_num,
                       gender, student_id, assigned_grade, is_approved
                FROM users
            ''')
            conn.execute('DROP TABLE users')
            conn.execute('ALTER TABLE users_new RENAME TO users')
            # 이후 검색용 인덱스 이름 확인을 위한 마커 인덱스
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_student_id ON users(student_id)")
            print('  UNIQUE 제약 추가 완료.')
        else:
            print('  이미 존재.')

        # ── 3. attendance 테이블: (user_id, date, period) UNIQUE ──
        print('[3/4] attendance 테이블 UNIQUE 제약 확인...')
        if not index_exists(cur, 'uq_attendance_user_date_period'):
            conn.execute('''
                CREATE TABLE IF NOT EXISTS attendance_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER NOT NULL REFERENCES users(id),
                    date            DATE NOT NULL,
                    period          INTEGER NOT NULL,
                    status          VARCHAR(15) NOT NULL DEFAULT 'present',
                    study_room_id   INTEGER REFERENCES study_rooms(id),
                    checked_at      DATETIME,
                    checked_out_at  DATETIME,
                    study_minutes   INTEGER,
                    early_leave_note VARCHAR(200),
                    UNIQUE (user_id, date, period)
                )
            ''')
            conn.execute('''
                INSERT OR IGNORE INTO attendance_new
                    (id, user_id, date, period, status, study_room_id,
                     checked_at, checked_out_at, study_minutes, early_leave_note)
                SELECT id, user_id, date, period, status, study_room_id,
                       checked_at, checked_out_at,
                       CASE WHEN checked_at IS NOT NULL AND checked_out_at IS NOT NULL
                            AND checked_out_at > checked_at
                            THEN CAST((julianday(checked_out_at) - julianday(checked_at)) * 1440 AS INTEGER)
                            ELSE NULL END,
                       early_leave_note
                FROM attendance
            ''')
            conn.execute('DROP TABLE attendance')
            conn.execute('ALTER TABLE attendance_new RENAME TO attendance')
            print('  UNIQUE 제약 추가 완료.')
        else:
            print('  이미 존재.')

        # ── 4. study_rooms 테이블: name UNIQUE ──
        print('[4/4] study_rooms 테이블 UNIQUE 제약 확인...')
        if not index_exists(cur, 'uq_study_rooms_name'):
            conn.execute('''
                CREATE TABLE IF NOT EXISTS study_rooms_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            VARCHAR(50) NOT NULL UNIQUE,
                    capacity        INTEGER DEFAULT 0,
                    male_capacity   INTEGER DEFAULT 0,
                    female_capacity INTEGER DEFAULT 0,
                    is_active       BOOLEAN DEFAULT 1,
                    "order"         INTEGER DEFAULT 0,
                    qr_token        VARCHAR(32) UNIQUE
                )
            ''')
            conn.execute('''
                INSERT OR IGNORE INTO study_rooms_new
                    (id, name, capacity, male_capacity, female_capacity,
                     is_active, "order", qr_token)
                SELECT id, name, capacity, male_capacity, female_capacity,
                       is_active, "order", qr_token
                FROM study_rooms
            ''')
            conn.execute('DROP TABLE study_rooms')
            conn.execute('ALTER TABLE study_rooms_new RENAME TO study_rooms')
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_study_rooms_name ON study_rooms(name)")
            print('  UNIQUE 제약 추가 완료.')
        else:
            print('  이미 존재.')

        # ── 5. users 테이블: session_token 컬럼 추가 ──
        print('[5/6] users session_token 컬럼 확인...')
        if not column_exists(cur, 'users', 'session_token'):
            conn.execute("ALTER TABLE users ADD COLUMN session_token VARCHAR(36)")
            cur.execute('SELECT id FROM users')
            for (uid,) in cur.fetchall():
                conn.execute('UPDATE users SET session_token = ? WHERE id = ?',
                             (str(uuid.uuid4()), uid))
            print('  session_token 컬럼 추가 및 UUID 생성 완료.')
        else:
            print('  이미 존재.')

        # ── 6. schedules 테이블: (user_id, day_of_week, period) UNIQUE 제약 추가 ──
        print('[6/6] schedules 테이블 UNIQUE 제약 확인...')
        if not index_exists(cur, 'uq_schedule_user_day_period'):
            # 중복 행이 있으면 최신 id만 남기고 삭제
            conn.execute('''
                DELETE FROM schedules
                WHERE id NOT IN (
                    SELECT MAX(id) FROM schedules
                    GROUP BY user_id, day_of_week, period
                )
            ''')
            conn.execute('''
                CREATE UNIQUE INDEX uq_schedule_user_day_period
                ON schedules(user_id, day_of_week, period)
            ''')
            print('  UNIQUE 제약 추가 완료.')
        else:
            print('  이미 존재.')

        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()
        print('\n마이그레이션 완료.')

    except Exception as e:
        conn.rollback()
        print(f'\n오류 발생, 롤백됨: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
