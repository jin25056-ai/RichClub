# RichClub

주식 자산 관리 플랫폼

## 구조

```
RichClub/
  web_server/      # FastAPI 백엔드
  web_client/      # React + TypeScript 프론트엔드
  docker-compose.yml
  .github/workflows/
```

## 시스템 구성도
![alt text](images/image.png)

---

## 인증 규칙

### 암호화
- 비밀번호: `bcrypt` 해싱 (단방향, 복호화 불가)
- 토큰: `HS256` 알고리즘 JWT

### JWT 토큰 구조
| 토큰 | 유효기간 | 용도 |
|---|---|---|
| access_token | 60분 | API 요청 인증 |
| refresh_token | 14일 | access_token 재발급 |

### API 인증 방식
```
Authorization: Bearer <access_token>
```

### 엔드포인트
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | /api/v1/auth/signup | 회원가입 |
| POST | /api/v1/auth/login | 로그인 |
| POST | /api/v1/auth/refresh | 토큰 재발급 |
| GET | /api/v1/auth/me | 내 정보 조회 |

### MongoDB users 컬렉션 구조
```json
{
  "_id": "ObjectId",
  "email": "string (unique index)",
  "hashed_password": "string (bcrypt)",
  "name": "string",
  "is_active": "boolean",
  "created_at": "datetime (UTC)",
  "updated_at": "datetime (UTC)"
}
```

---

## 로컬 실행

### 백엔드 (web_server)

> Windows 환경에서는 python 대신 py 사용, pip 대신 python -m pip 사용

```powershell
cd web_server

# 1. 가상환경 생성 (Python 3.11 필요)
py -3.11 -m venv .venv --copies

# 2. 가상환경 활성화 - (.venv) 표시 확인
.venv\Scripts\Activate.ps1

# 실행 정책 오류 시 먼저 실행 후 다시 활성화
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. 패키지 설치
python -m pip install -r requirements.txt

# 4. 서버 실행
python -m uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs

### 환경변수 설정

`web_server/.env` 파일 작성:

```
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net
MONGODB_DB=richclub
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 프론트엔드 (web_client)

```powershell
cd web_client
npm install
npm start
```

---

## Docker로 전체 실행

```powershell
docker compose up -d
```

---

## CI/CD

GitHub Actions 사용. GitHub Secrets 설정 필요:

| Secret | 설명 |
|---|---|
| DOCKERHUB_USERNAME | Docker Hub 계정 |
| DOCKERHUB_TOKEN | Docker Hub 액세스 토큰 |
| DEPLOY_HOST | 배포 서버 IP |
| DEPLOY_USER | 배포 서버 SSH 사용자 |
| DEPLOY_SSH_KEY | 배포 서버 SSH 개인키 |

- `main` 브랜치 push: 테스트 + Docker 빌드 + 서버 자동 배포
- PR: 테스트만 실행
