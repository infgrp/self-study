"""
데이터베이스 초기화 스크립트
기존 DB를 삭제하고 새로운 스키마로 재생성합니다.
※ 삭제 전에 자동으로 백업 파일을 생성합니다.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# DB 파일 경로
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'self_study.db')

# 1. DB 파일 삭제 (삭제 전 자동 백업)
if os.path.exists(db_path):
    # 자동 백업: 삭제 전에 타임스탬프 백업 파일 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(basedir, 'instance', f'self_study_pre_reset_{timestamp}.db')
    try:
        src = sqlite3.connect(db_path)
        bak = sqlite3.connect(backup_path)
        src.backup(bak)
        bak.close()
        src.close()
        print(f"✓ 자동 백업 완료: {backup_path}")
        print("  ⚠ 복원이 필요하면 관리자 페이지 → 백업/복원 → 'DB 교체 복원'에서 위 파일을 사용하세요.")
    except Exception as e:
        print(f"  ⚠ 자동 백업 실패: {e}")
        answer = input("  백업 없이 계속하시겠습니까? [y/N]: ").strip().lower()
        if answer != 'y':
            print("취소되었습니다.")
            sys.exit(0)

    try:
        os.remove(db_path)
        print(f"✓ 기존 데이터베이스 삭제: {db_path}")
    except PermissionError:
        print("✗ 오류: Flask 서버가 실행 중입니다.")
        print("  1. 터미널에서 Ctrl+C로 서버를 중지하세요.")
        print("  2. 이 스크립트를 다시 실행하세요: python reset_db.py")
        sys.exit(1)
else:
    print("✓ 기존 데이터베이스 없음")

# 2. 새 DB 생성
from app import create_app
app = create_app()
print("✓ 새 데이터베이스 생성 완료")
print("\n이제 'python app.py'로 서버를 시작하세요.")
