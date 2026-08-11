"""
DB 복구 스크립트 - system_settings 중복 스키마 오류 수정
손상된 DB에서 모든 데이터를 추출하고 새로운 깨끗한 DB를 생성합니다.
"""
import sqlite3
import shutil
import os
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'self_study.db')
BACKUP_PATH = DB_PATH + f'.pre_repair_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
NEW_DB_PATH = DB_PATH + '.repaired'

IMMUTABLE_URI = 'file:instance/self_study.db?mode=ro&immutable=1'

TABLE_ORDER = [
    'users',
    'holidays',
    'study_period_settings',
    'study_rooms',
    'schedules',
    'study_logs',
    'study_applications',
    'attendance',
    'attendance_logs',
    'student_rooms',
    'system_settings',
]

def read_schema(conn, table_name):
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=? ORDER BY rowid LIMIT 1",
        (table_name,)
    )
    row = cur.fetchone()
    return row[0] if row else None

def read_all_data(conn, table_name):
    try:
        cur = conn.execute(f'SELECT * FROM "{table_name}"')
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return cols, rows
    except Exception as e:
        print(f'  경고: {table_name} 읽기 실패 - {e}')
        return [], []

def main():
    print('=' * 60)
    print('SQLite DB 복구 스크립트')
    print('=' * 60)

    # 1. 손상된 DB 백업
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f'[1] 손상된 DB 백업 완료: {os.path.basename(BACKUP_PATH)}')

    # 2. 손상된 DB에서 데이터 추출 (immutable+ro 모드)
    print('[2] 손상된 DB에서 데이터 추출 중...')
    try:
        old_conn = sqlite3.connect(IMMUTABLE_URI, uri=True)
        old_conn.execute('PRAGMA writable_schema=ON')  # 스키마 검증 완화
        old_conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f'오류: 손상된 DB를 열 수 없습니다 - {e}')
        sys.exit(1)

    # 사용 가능한 테이블 목록 확인 (중복 포함, DISTINCT로 한 번만)
    cur = old_conn.execute(
        "SELECT DISTINCT name FROM sqlite_master WHERE type='table' ORDER BY rowid"
    )
    available_tables = {r[0] for r in cur.fetchall()}
    print(f'  발견된 테이블: {sorted(available_tables)}')

    # 각 테이블의 스키마와 데이터 읽기
    schemas = {}
    data = {}
    for table in TABLE_ORDER:
        if table not in available_tables:
            print(f'  건너뜀: {table} (존재하지 않음)')
            continue
        schema = read_schema(old_conn, table)
        if schema:
            schemas[table] = schema
            cols, rows = read_all_data(old_conn, table)
            data[table] = (cols, rows)
            print(f'  {table}: {len(rows)}행 추출')

    old_conn.close()

    # 3. 새 DB 생성
    print('[3] 새 DB 생성 중...')
    if os.path.exists(NEW_DB_PATH):
        os.remove(NEW_DB_PATH)

    new_conn = sqlite3.connect(NEW_DB_PATH)
    new_conn.execute('PRAGMA foreign_keys=OFF')
    new_conn.execute('PRAGMA journal_mode=WAL')

    for table in TABLE_ORDER:
        if table not in schemas:
            continue
        try:
            new_conn.execute(schemas[table])
            print(f'  테이블 생성: {table}')
        except Exception as e:
            print(f'  테이블 생성 실패: {table} - {e}')

    # 4. 데이터 삽입
    print('[4] 데이터 삽입 중...')
    for table in TABLE_ORDER:
        if table not in data:
            continue
        cols, rows = data[table]
        if not rows:
            continue
        placeholders = ','.join(['?' for _ in cols])
        col_names = ','.join([f'"{c}"' for c in cols])
        sql = f'INSERT OR REPLACE INTO "{table}" ({col_names}) VALUES ({placeholders})'
        try:
            new_conn.executemany(sql, rows)
            print(f'  {table}: {len(rows)}행 삽입')
        except Exception as e:
            print(f'  삽입 실패: {table} - {e}')

    new_conn.execute('PRAGMA foreign_keys=ON')

    # 5. 무결성 검사
    print('[5] 무결성 검사...')
    cur = new_conn.execute('PRAGMA integrity_check')
    result = cur.fetchone()[0]
    print(f'  결과: {result}')

    new_conn.commit()
    new_conn.close()

    if result != 'ok':
        print('오류: 새 DB도 무결성 문제가 있습니다. 수동 확인 필요.')
        sys.exit(1)

    # 6. 교체
    print('[6] DB 교체 중...')
    os.replace(NEW_DB_PATH, DB_PATH)
    print(f'  완료: {DB_PATH} 교체됨')

    print()
    print('복구 완료! 앱을 다시 시작하세요.')
    print(f'원본 손상 백업: {os.path.basename(BACKUP_PATH)}')

if __name__ == '__main__':
    main()
