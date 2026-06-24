# RichClub

주식 자산 관리 플랫폼

## 구조

```
RichClub/
  web_server/      # FastAPI 백엔드
  web_client/      # React + TypeScript 프론트엔드
  collect_data/    # 데이터 수집 스크립트 (seongsu, jungho 등 팀원별)
  docker-compose.yml
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
Bearer 토큰 또는 HttpOnly 쿠키 둘 다 지원

```
Authorization: Bearer <access_token>
```

또는 로그인 시 자동으로 설정되는 쿠키 사용 (프론트에서 `credentials: 'include'` 또는 axios `withCredentials: true` 필요)

### 엔드포인트
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | /api/v1/auth/signup | 회원가입 |
| POST | /api/v1/auth/login | 로그인 |
| POST | /api/v1/auth/refresh | 토큰 재발급 |
| POST | /api/v1/auth/logout | 로그아웃 (쿠키 삭제) |
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

## MongoDB 컬렉션

| 컬렉션 | 설명 |
|---|---|
| users | 회원 정보 |
| total_trading_signals | 종목별 일별 예측 신호 + 수익률 (ret_1d, ret_5d, ret_20d, ret_60d) |
| model_train_history | XGBoost 모델 학습 이력 |
| model_performance_monthly | 월별 신호 성능 집계 (매수/매도/관망 승률, 평균 수익률) |
| candles_5m | 5분봉 데이터 |

---

## MLOps 파이프라인

서버 내부에서 자체적으로 학습, 예측, 평가까지 수행합니다. `collect_data/jungho` 폴더의 스크립트에 의존하지 않습니다.

### 흐름

```
서버 최초 실행
    ↓
XGBoost 모델 자동 학습 (yfinance로 KOSPI 50종목 2년치 수집)
    ↓ /app/models/xgb_model.json 저장
매일 KST 16:30 (UTC 07:30)
    ↓
전 종목 예측 → total_trading_signals upsert
    ↓
매일 UTC 08:00
    ↓
수익률 계산 (total_trading_signals 내에서 +1/5/20/60일 후 종가 비교)
    ↓
월별 성능 집계 → model_performance_monthly 저장
    ↓
매주 수요일 성능 체크
    ↓
매수 신호 2개월 정확도 50% 미만이면 자동 재학습
    ↓
매주 일요일 정기 재학습
```

### XGBoost 모델 피처
| 피처 | 설명 |
|---|---|
| ma5_20_ratio | 5일선 / 20일선 비율 |
| ma20_60_ratio | 20일선 / 60일선 비율 |
| close_ma60_ratio | 종가 / 60일선 비율 |
| vol_change | 거래량 전일 대비 변화율 |
| macd | MACD 값 |
| stoch_k / stoch_d | 스토캐스틱 K/D |
| obv | OBV |
| macd_change | MACD 전일 대비 변화 |
| stoch_k_change | 스토캐스틱 K 전일 대비 변화 |
| sp500_ma_ratio | S&P500 / 20일선 비율 (거시 지표) |
| vix_value | VIX 지수 (공포 지수) |

### 신호 레이블
| 값 | 의미 |
|---|---|
| 0 | 매도 |
| 1 | 매수 |
| 2 | 관망 |

### 스케줄러 (UTC 기준)
| 스케줄 | 설명 |
|---|---|
| 월~금 매 5분 | 5분봉 수집 |
| 월~금 07:30 | 전 종목 예측 |
| 매일 08:00 | 수익률 계산 + 월별 집계 |
| 매주 수요일 09:00 | 성능 체크 후 필요시 자동 재학습 |
| 매주 일요일 23:00 | 정기 모델 재학습 |

---

## MLOps 대시보드

관리자용 대시보드: `/mlops` (로그인 필요, 프론트 Vercel 배포 후 활성화)

- 모델 현황 (모델 존재 여부, 마지막 정확도, 수익률 계산 진행 상황)
- 기간별 신호 성능 (30/60/90/180일, 매수/매도/관망 승률 및 평균 수익률)
- 월별 성능 테이블 (월별 승률 + 5일 평균 수익률)
- 학습 이력
- 최근 신호 목록 (1일/5일/20일 수익률 포함)

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

## 배포 환경

### 인프라 구성
- 서버: Mac M1 Mini (홈 서버)
- 외부 접근: Cloudflare Tunnel
- 컨테이너: Docker + colima (Mac ARM64)

### 서비스 주소
| 서비스 | 주소 |
|---|---|
| API 서버 | https://richclub.efforthye.dev |
| API 문서 | https://richclub.efforthye.dev/docs |
| Jenkins | https://jenkins.efforthye.dev |
| 프론트엔드 | https://rich-club-front-end.vercel.app |

### Docker 이미지
- DockerHub: `efforthye/richclub-api:latest`
- 멀티 플랫폼 빌드: `linux/amd64`, `linux/arm64`
- 모델 저장 경로 (컨테이너 내부): `/app/models/xgb_model.json`

### 수동 빌드 및 배포 (Windows)

```powershell
cd web_server

# 멀티 플랫폼 빌드 및 DockerHub 푸시
docker buildx build --platform linux/amd64,linux/arm64 -t efforthye/richclub-api:latest --push .
```

### Mac M1 미니에서 수동 재배포

```bash
docker pull efforthye/richclub-api:latest
docker stop richclub-api
docker rm richclub-api
docker run -d \
  --name richclub-api \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /Users/nadeko/Desktop/programs/study/RichClub/web_server/.env \
  efforthye/richclub-api:latest
```

---

## CI/CD

Jenkins + Poll SCM 방식으로 자동 배포

### 흐름

```
코드 수정
    ↓
git push (efforthye 브랜치)
    ↓
Jenkins Poll SCM (1분마다 감지)
    ↓
Docker 빌드
    ↓
DockerHub push (efforthye/richclub-api)
    ↓
기존 컨테이너 교체 배포
    ↓
https://richclub.efforthye.dev 에 반영
```

### Jenkins Credentials 설정
| ID | Kind | 설명 |
|---|---|---|
| github-token | Secret text | GitHub Personal Access Token |
| dockerhub-credentials | Username with password | DockerHub 계정 및 토큰 |

### Cloudflare Tunnel 서비스 등록 (Mac M1 미니)

```bash
# 서비스 설치 (재부팅 시 자동 실행) 
sudo cloudflared service install 

# 서비스 상태 확인
sudo launchctl list | grep cloudflared

# 로그 확인
sudo cat /Library/Logs/com.cloudflare.cloudflared.err.log | tail -20
```
