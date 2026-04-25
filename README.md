# 자율학습 관리 시스템 (self_study)

고등학교 야간 자율학습 운영을 위한 Flask 웹 애플리케이션입니다.
학생의 월별 자습 신청, 자습실 QR 입실·퇴실, 출결 자동 처리, 좌석 배정,
참여율 통계, 백업/복원까지 학교 내부망에서 단일 PC로 운영할 수 있도록 설계되어 있습니다.

자세한 운영 가이드는 [`manual.pdf`](manual.pdf)를 참조하세요 (50+페이지).

## 주요 기능

### 학생
- 월별 자습 신청 (요일별 교시 설정 반영)
- 자습실 QR 스캔으로 입실·퇴실
- 본인 월별 출결 이력 조회, 학습 기록 작성
- 마이페이지: 비밀번호 변경, 학번/성별 수정

### 교사
- 학생별 자습실 좌석 배정 (남/여 zone 분리, 임의 배정 + 수동 배정 + 드래그 배치도)
- 출석 관리: 수동 수정, 자동 지각/결석/조퇴 처리, 출결 수정 이력
- 참여율 통계 및 Excel 내보내기 (월별, 기간별)
- 자습 시간·공휴일·자습실·방과후 수업 설정
- QR코드 생성·인쇄, 좌석 배치도 시각화

### 관리자
- 교사 계정 승인, 사용자 관리, 비밀번호 초기화
- 시스템 설정 (사전 입실 시간·지각 임계·신청 마감일·비밀번호 정책 등 8개 운영 정책값)
- DB 백업 (`.db` 파일) / Excel 백업 (`.xlsx`)
- 새 학년도 초기화 (학생 데이터 삭제 + 시설 설정 보존)
- 백업 파일로 복원 (Excel 추가 모드 / DB 파일 완전 교체)

## 기술 스택

- Python 3.10+
- Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF)
- Waitress (운영 WSGI 서버 — 학내망 Wi-Fi 끊김 후에도 안정 동작)
- SQLite (WAL 모드, 외래키 강제)
- openpyxl (Excel 입출력)
- APScheduler (야간 자동 조퇴 처리)

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python app.py
```

또는 Windows에서 [`start_self_study.bat`](start_self_study.bat) 더블클릭.

처음 실행 시:
- `instance/self_study.db` 자동 생성 (스키마 + 기본 자습 시간 + 8개 시스템 설정 시드)
- `instance/secret_key.txt` 자동 생성
- 관리자 계정 자동 생성 (콘솔에 초기 비밀번호 출력 — **첫 로그인 후 즉시 변경**)

브라우저에서 `http://[서버IP]:5000` 접속.

## 디렉터리 구조 (요약)

```
self_study/
├── app.py                    # Flask 진입점, 로깅·스케줄러·부팅 시 검증
├── auth.py                   # 로그인/로그아웃/회원가입
├── routes_admin.py           # 관리자 라우트 (사용자·백업·복원·설정)
├── routes_teacher.py         # 교사 라우트 (출석·통계·자습실·좌석)
├── routes_student.py         # 학생 라우트 (신청·QR·학습기록)
├── models.py                 # SQLAlchemy 모델 + DB 제약
├── settings.py / validators.py / time_utils.py / day_utils.py / audit.py / constants.py
├── templates/                # Jinja2 템플릿
├── instance/                 # ⚠ 운영 데이터 (DB, secret_key) — 절대 외부 반출 금지
├── logs/                     # ⚠ 운영 로그 (audit.log, app.log)
├── manual.tex / manual.pdf   # 운영 매뉴얼 (50+페이지)
└── migrate_*.py              # 스키마 업그레이드 스크립트
```

## 운영 PC로 코드를 옮길 때 제외할 파일

다음을 압축에 **포함하지 마십시오** (운영 데이터·인증 정보 유출 방지):

- `instance/` (DB, secret_key, 기존 학생 정보)
- `logs/` (IP·요청 흐름)
- `__pycache__/`
- `*.aux`, `*.log`, `*.out`, `*.toc`, `*.synctex.gz` (LaTeX 부산물)
- `*.zip`

PowerShell 안전 압축 예시는 [`manual.pdf`](manual.pdf) 9.4절 참조.

## 마이그레이션 스크립트 (적용 순서)

운영 PC에서 코드를 업데이트한 후, **DB 백업을 먼저 받고** 다음 순서로 실행:

| 스크립트 | 적용 대상 | 내용 |
|---|---|---|
| [`migrate.py`](migrate.py) | v1.9 이하 → 최신 | `attendance` 컬럼·`session_token` 추가, UNIQUE 제약 |
| [`migrate_add_settings.py`](migrate_add_settings.py) | 시스템 설정 도입 이전 | `system_settings` 테이블 + 기본값 8개 시드 |
| [`migrate_add_constraints_v2.py`](migrate_add_constraints_v2.py) | 무결성 제약 도입 이전 | `users`·`attendance` CHECK 제약 |
| [`migrate_drop_room_seat_uq.py`](migrate_drop_room_seat_uq.py) | 좌석 unique 회귀 수정 | `student_rooms`의 잘못된 좌석 unique 제거 |

모든 스크립트는 **멱등(idempotent)** — 중복 실행해도 안전합니다.

## 보안 / 감사 로그

- `logs/audit.log` (5MB × 5 회전): 인증·관리자 작업·시스템 이벤트 11종 기록.
- 평문 비밀번호는 **어떤 경로로도 로그·flash·DB에 기록되지 않습니다**.
- DB 파일 복원·관리자 비밀번호 초기화 등 민감 작업은 모두 WARNING 레벨로 추적.
- 부팅 시 DB 무결성 제약·`session_token` NULL을 자동 검사하여 누락 시 안내.

## 학교 내부망 운영 전제

이 시스템은 **학내 Wi-Fi**에서만 접근 가능한 내부 시스템입니다.
외부 인터넷 노출이나 다중 학교 공유는 가정하지 않으며, 일부 편의 기능
(관리자 계정 자동 생성 등)은 그 전제 위에 설계되어 있습니다.

## 라이선스

학교 내부 사용을 목적으로 작성됨. 외부 배포·재사용 시 작성자에게 문의.
