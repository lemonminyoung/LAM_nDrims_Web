# 실행 웹 폴링 서비스

실행 웹이 백엔드와 통신하여 nDRIMS 자동화를 실행합니다.

---

## 📋 역할

```
프롬프트 웹 (React)
    ↓ POST /login
백엔드 API (Mock Server)
    ↓ GET /command (폴링)
실행 웹 (Python Playwright) ← 이 프로그램
    ↓ POST /state
백엔드 API
    ↓ GET /login-status (폴링)
프롬프트 웹 (로그인 완료)
```

---

## 🚀 설치 및 실행

### 1. Python 패키지 설치
```bash
cd C:\Users\김민영\Desktop\JONG2
pip install -r requirements.txt
```

### 2. Playwright 브라우저 설치
```bash
playwright install chromium
```

### 3. 실행 웹 서비스 시작
```bash
python execution_web_service.py
```

---

## 📂 파일 구조

```
JONG2/
├── execution_web_service.py    # 폴링 서비스 (새로 추가)
├── explaywright.py              # Playwright 실행기
├── trajectory_student_check.json # 로그인 시나리오
├── main_trajectory.py           # (기존 파일, 사용 안함)
└── requirements.txt             # Python 패키지
```

---

## 🔄 전체 실행 순서

### 터미널 1: Mock 백엔드 서버
```bash
cd C:\Users\김민영\my-chat-ui
npm run server
```

### 터미널 2: 실행 웹 서비스
```bash
cd C:\Users\김민영\Desktop\JONG2
python execution_web_service.py
```

### 터미널 3: 프롬프트 웹
```bash
cd C:\Users\김민영\my-chat-ui
npm run dev
```

### 브라우저
```
http://localhost:5173
```

---

## ✅ 테스트 시나리오

1. 브라우저에서 `http://localhost:5173` 접속
2. 학번: `2019123456`, 비밀번호: `test1234` 입력
3. 로그인 버튼 클릭
4. **실행 웹 터미널에서 로그 확인**:
   ```
   [명령 수신] 로그인 요청
     - 학번: 2019123456
   [실행] Playwright 로그인 시작...
   [성공] 로그인 완료
   [전송 완료] 상태 전송 성공
   ```
5. **프롬프트 웹에서 로딩 화면 → 채팅 화면 전환 확인**

---

## 🐛 문제 해결

### 백엔드 연결 오류
```
[오류] 백엔드 서버에 연결할 수 없습니다.
```
→ Mock 서버가 실행 중인지 확인: `npm run server`

### trajectory 파일 없음
```
[오류] trajectory 파일을 찾을 수 없습니다
```
→ `trajectory_student_check.json` 파일이 JONG2 폴더에 있는지 확인

### Playwright 실행 오류
```
playwright._impl._api_types.Error: Executable doesn't exist
```
→ Playwright 브라우저 설치: `playwright install chromium`

---

## 📊 로그 확인

### 실행 웹 로그
```
[명령 수신] 로그인 요청
  - 학번: 2019123456
  - 토큰: mock-token-2019123456
[실행] Playwright 로그인 시작...
[LOG] [STEP] unknown_step
[1] goto
[2] type
[3] type
[4] click
...
[성공] 로그인 완료
[전송 완료] 상태 전송 성공
```

### Mock 백엔드 로그
```
로그인 시도: { student_id: '2019123456', password: 'test1234' }
로그인 요청 접수: 홍길동 (token: mock-token-2019123456)
[명령 큐] 로그인 명령 추가: 2019123456
[명령 큐] 명령 전달: type=login, id=1234567890
[실행 웹] 상태 수신: { loginSuccess: true, message: '로그인 성공' }
[로그인 완료] token=mock-token-2019123456
```

---

## 🎯 다음 단계

1. **실제 백엔드 연동**
   - Mock 서버 → 실제 백엔드 API URL로 변경
   - `execution_web_service.py`의 `BACKEND_URL` 수정

2. **프롬프트 처리 추가**
   - `/command`에서 `type: "prompt"` 명령 처리
   - Gemini AI 통합

3. **에러 처리 강화**
   - 재시도 로직
   - 타임아웃 처리

---

## 💡 참고

- **폴링 간격**: 기본 5초 (`POLLING_INTERVAL` 변수로 조정 가능)
- **헤드리스 모드**: `explaywright.py:141`에서 `headless=True`로 변경 가능
- **로그 레벨**: 현재 모든 로그 출력 (필요시 조정)
