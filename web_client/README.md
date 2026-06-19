# RichClub Web Client

React + TypeScript 기반 웹 클라이언트입니다.

## 시작하기

### 의존성 설치

```bash
npm install
```

### 개발 서버 실행

```bash
npm start
```

### 프로덕션 빌드

```bash
npm run build
```

---

## 디렉토리 구조

```
src/
  api/              # axios 인스턴스, 인터셉터, API 함수
  components/       # 재사용 가능한 UI 컴포넌트 (Button, Header)
  containers/       # 비즈니스 로직을 포함하는 컨테이너 컴포넌트
  pages/            # 라우트에 대응하는 페이지 컴포넌트
  router/           # 라우팅 설정
  styles/           # 글로벌 스타일
  types/            # 공유 타입 정의
```

## 라우트

| 경로    | 페이지          |
|---------|-----------------|
| /       | 메인 페이지     |
| /auth   | 로그인/회원가입 |
| /chart  | 차트 페이지     |

## 환경 변수

`.env` 파일을 프로젝트 루트에 생성하세요.

```
REACT_APP_API_BASE_URL=http://localhost:8000
```
