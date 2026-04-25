"""
DB 마이그레이션: 데이터 무결성 제약 추가

추가되는 제약:
  1. users          CHECK(role IN ('student','teacher','admin'))
  2. users          CHECK(gender IS NULL OR gender IN ('M','F'))
  3. attendance     CHECK(status IN ('present','late','absent','early_leave','approved_leave','after_school'))
  4. student_rooms  UNIQUE(study_room_id, seat_number)   -- NULL은 distinct로 허용

SQLite는 ALTER TABLE로 CHECK/UNIQUE 제약을 추가할 수 없어, 각 테이블을 재구축한다.
실행 전 반드시 DB 백업을 수행하라. 스크립트는 실행 중 오류 발생 시 자동 롤백한다.

동작 순서:
  [1] 사전 검사 - 현재 데이터가 추가될 제약을 위반하는지 스캔
      위반이 있으면 상세 내역 출력 후 중단 (강제 실행 옵션 없음 - 데이터 정정이 선행)
  [2] 테이블 재구축 - 임시 테이블 생성 → 데이터 복사 → DROP → RENAME
  [3] 완료 후 PRAGMA foreign_keys로 FK 무결성 검증

실행:
    python migrate_add_constraints_v2.py

이 스크립트는 멱등(idempotent)하게 작성되어 있다 - 이미 제약이 적용된 상태라면 건너뛴다.
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')


# ── 사전 검사 쿼리 ────────────────────────────────────────────────

PRE_CHECKS = [
    {
        'name': 'users.role',
        'query': "SELECT id, username, role FROM users WHERE role NOT IN ('student','teacher','admin')",
        'msg': "users.role 위반 행",
    },
    {
        'name': 'users.gender',
        'query': "SELECT id, username, gender FROM users WHERE gender IS NOT NULL AND gender NOT IN ('M','F')",
        'msg': "users.gender 위반 행 (NULL 또는 'M'/'F'만 허용)",
    },
    {
        'name': 'attendance.status',
        'query': ("SELECT id, user_id, date, period, status FROM attendance "
                  "WHERE status NOT IN ('present','late','absent','early_leave','approved_leave','after_school')"),
        'msg': "attendance.status 위반 행",
    },
    # NOTE: student_rooms (study_room_id, seat_number) 중복 검사는 제거됨.
    # 남/여 zone 구조에서는 같은 번호가 정상이며 zone 정보가 user.gender로만 표현되어
    # SQL UNIQUE로 모델링하기 어렵다. 코드 레벨에서 zone 내 중복을 막는다.
]


def run_pre_checks(cur):
    """제약 위반 데이터를 스캔해 문제 없으면 True, 있으면 출력 후 False."""
    violations = []
    for chk in PRE_CHECKS:
        cur.execute(chk['query'])
        rows = cur.fetchall()
        if rows:
            violations.append((chk, rows))
    if not violations:
        print("[1/3] 사전 검사 통과 - 제약 위반 데이터 없음.")
        return True

    print("[1/3] 사전 검사 실패 - 아래 데이터를 먼저 정정한 뒤 재실행하세요:\n")
    for chk, rows in violations:
        print(f"  ▷ {chk['msg']}:")
        for r in rows[:20]:
            print(f"      {r}")
        if len(rows) > 20:
            print(f"      ... 외 {len(rows) - 20}건")
        print()
    return False


# ── 제약 이미 적용됐는지 확인 (멱등성) ────────────────────────────

def constraint_already_applied(cur, table, needle):
    """sqlite_master에서 테이블의 CREATE 문에 특정 제약 조각이 포함됐는지 확인."""
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    return needle in row[0]


# ── 테이블 재구축 ─────────────────────────────────────────────────

REBUILD_STATEMENTS = {
    'users': {
        'marker': "ck_users_role",
        'create_new': """
            CREATE TABLE users_new (
                id              INTEGER PRIMARY KEY,
                username        VARCHAR(50)  NOT NULL UNIQUE,
                password_hash   VARCHAR(200) NOT NULL,
                name            VARCHAR(50)  NOT NULL,
                role            VARCHAR(10)  NOT NULL,
                grade           INTEGER,
                class_num       INTEGER,
                gender          VARCHAR(1),
                student_id      VARCHAR(5)   UNIQUE,
                assigned_grade  INTEGER,
                is_approved     BOOLEAN      NOT NULL DEFAULT 1,
                session_token   VARCHAR(36)  NOT NULL,
                CONSTRAINT ck_users_role   CHECK (role IN ('student','teacher','admin')),
                CONSTRAINT ck_users_gender CHECK (gender IS NULL OR gender IN ('M','F'))
            )
        """,
        'copy': """
            INSERT INTO users_new
              (id, username, password_hash, name, role, grade, class_num,
               gender, student_id, assigned_grade, is_approved, session_token)
            SELECT id, username, password_hash, name, role, grade, class_num,
                   gender, student_id, assigned_grade, is_approved, session_token
            FROM users
        """,
    },
    'attendance': {
        'marker': "ck_attendance_status",
        'create_new': """
            CREATE TABLE attendance_new (
                id               INTEGER  PRIMARY KEY,
                user_id          INTEGER  NOT NULL REFERENCES users(id),
                date             DATE     NOT NULL,
                period           INTEGER  NOT NULL,
                status           VARCHAR(15) NOT NULL DEFAULT 'present',
                study_room_id    INTEGER  REFERENCES study_rooms(id),
                checked_at       DATETIME,
                checked_out_at   DATETIME,
                study_minutes    INTEGER,
                early_leave_note VARCHAR(200),
                CONSTRAINT uq_attendance_user_date_period UNIQUE (user_id, date, period),
                CONSTRAINT ck_attendance_status CHECK (
                    status IN ('present','late','absent','early_leave','approved_leave','after_school')
                )
            )
        """,
        'copy': """
            INSERT INTO attendance_new
              (id, user_id, date, period, status, study_room_id,
               checked_at, checked_out_at, study_minutes, early_leave_note)
            SELECT id, user_id, date, period, status, study_room_id,
                   checked_at, checked_out_at, study_minutes, early_leave_note
            FROM attendance
        """,
    },
    # NOTE: student_rooms는 더 이상 재구축 대상 아님.
    # 초기 v2에서 uq_room_seat 제약을 추가했으나 남/여 zone 구조와 충돌해 제거됨
    # (migrate_drop_room_seat_uq.py로 별도 처치).
}


def rebuild_table(cur, table):
    spec = REBUILD_STATEMENTS[table]

    if constraint_already_applied(cur, table, spec['marker']):
        print(f"  - {table}: 이미 적용됨 (건너뜀)")
        return False

    print(f"  - {table}: 재구축 시작...")
    cur.execute(f"DROP TABLE IF EXISTS {table}_new")
    cur.execute(spec['create_new'])
    cur.execute(spec['copy'])
    cur.execute(f"DROP TABLE {table}")
    cur.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    print(f"  - {table}: 완료")
    return True


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")   # 재구축 중에는 FK 잠시 off
    cur = conn.cursor()

    try:
        # [1] 사전 검사
        if not run_pre_checks(cur):
            conn.close()
            sys.exit(2)

        # [2] 트랜잭션 시작 후 각 테이블 재구축
        print("\n[2/3] 테이블 재구축 (트랜잭션)...")
        cur.execute("BEGIN")
        rebuilt = 0
        for table in ('users', 'attendance'):
            if rebuild_table(cur, table):
                rebuilt += 1
        conn.commit()

        # [3] FK 무결성 검사
        print("\n[3/3] 외래 키 무결성 검사...")
        conn.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA foreign_key_check")
        bad = cur.fetchall()
        if bad:
            print("  [X] FK 위반이 발견됐습니다. 복원이 필요합니다:")
            for row in bad:
                print(f"      {row}")
            sys.exit(3)
        print("  [OK] FK 무결성 OK")

        print(f"\n마이그레이션 완료. {rebuilt}개 테이블 재구축.")
    except Exception as e:
        conn.rollback()
        print(f"\n오류 발생, 롤백됨: {e}")
        sys.exit(4)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
