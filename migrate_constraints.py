"""
마이그레이션 스크립트 — 기존 SQLite DB에 유니크 제약 조건 추가
- users.student_id UNIQUE
- attendance (user_id, date, period) UNIQUE
- study_rooms.name UNIQUE
"""

import sqlite3
import os

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, 'instance', 'self_study.db')


def migrate():
    if not os.path.exists(DB_PATH):
        print(f'DB 파일을 찾을 수 없습니다: {DB_PATH}')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = OFF')
    conn.execute('PRAGMA journal_mode = WAL')

    try:
        # ── 1. users 테이블: student_id UNIQUE ──
        print('[1/3] users 테이블 마이그레이션 중...')
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
        print('  users 테이블 완료.')

        # ── 2. attendance 테이블: (user_id, date, period) UNIQUE ──
        print('[2/3] attendance 테이블 마이그레이션 중...')
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
                early_leave_note VARCHAR(200),
                UNIQUE (user_id, date, period)
            )
        ''')
        conn.execute('''
            INSERT OR IGNORE INTO attendance_new
                (id, user_id, date, period, status, study_room_id,
                 checked_at, checked_out_at, early_leave_note)
            SELECT id, user_id, date, period, status, study_room_id,
                   checked_at, checked_out_at, early_leave_note
            FROM attendance
        ''')
        conn.execute('DROP TABLE attendance')
        conn.execute('ALTER TABLE attendance_new RENAME TO attendance')
        print('  attendance 테이블 완료.')

        # ── 3. study_rooms 테이블: name UNIQUE ──
        print('[3/3] study_rooms 테이블 마이그레이션 중...')
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
        print('  study_rooms 테이블 완료.')

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
