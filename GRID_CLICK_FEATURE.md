# Grid 클릭 기능 추가 완료

**작성일:** 2025-11-14
**작업 내용:** Grid 상태에서 텍스트로 행 찾아 신청 버튼 클릭하는 기능 구현

---

## 📋 기능 개요

백엔드에서 `state: "grid"`가 포함된 액션이 오면, 화면의 grid에서 특정 텍스트를 찾아 해당 행의 **신청 버튼**을 자동으로 클릭하는 기능이 추가되었습니다.

---

## 🎯 사용 사례

### 백엔드에서 전달되는 액션 예시

```json
{
  "action": {
    "name": "click",
    "args": {
      "selector": "[name='[성적]이수구분변경신청']"
    },
    "state": "grid"
  }
}
```

### 동작 순서

1. `state: "grid"` 감지
2. `selector`에서 텍스트 추출: `"[성적]이수구분변경신청"`
3. Grid에서 해당 텍스트를 포함한 셀 찾기
4. 셀의 `aria-label`에서 행/열 번호 파싱 (예: "3행 5열 [성적]이수구분변경신청")
5. 같은 행의 2열(신청 버튼 열)에 있는 버튼 클릭

---

## 🔧 구현 내용

### 1. 새로운 함수: `click_apply_for_text()`

**위치:** `execution_web_service_gpt.py` (38~86줄)

**기능:**
- Grid에서 특정 텍스트를 포함한 셀 찾기
- aria-label에서 행/열 번호 파싱
- 같은 행의 신청 버튼 클릭

**코드:**
```python
async def click_apply_for_text(page: Page, target_text: str):
    """
    Grid에서 특정 텍스트를 찾아 해당 행의 '신청' 버튼을 클릭하는 함수
    """
    # 1. 텍스트를 가진 gridcell 찾기
    text_cell = page.get_by_role(
        "gridcell",
        name=re.compile(re.escape(target_text))
    ).first

    # 2. aria-label에서 행/열 번호 파싱
    aria_label = await text_cell.get_attribute("aria-label")
    m = re.search(r"(\d+)행\s+(\d+)열", aria_label)
    row_index = m.group(1)
    apply_col_index = "2"  # 신청 버튼은 2열에 위치

    # 3. 같은 행의 신청 버튼 찾아서 클릭
    apply_button = page.get_by_role(
        "button",
        name=re.compile(rf"{row_index}행\s+{apply_col_index}열")
    ).first

    await apply_button.click()
```

---

### 2. 액션 실행 로직 수정

**위치:** `execute_trajectory_in_browser()` 함수 (478~513줄)

**변경 내용:**
- 각 액션에서 `state` 필드 추출
- `state == "grid"` && `name == "click"` 조건 체크
- 조건 만족 시 `click_apply_for_text()` 호출
- 그 외에는 기존 `executor.run()` 실행

**코드:**
```python
for idx, step in enumerate(actions):
    action_def = step.get("action", {})
    action_name = action_def.get("name")
    action_args = action_def.get("args", {})
    action_state = action_def.get("state")  # ← state 필드 추출

    try:
        # state가 "grid"이고 click 액션인 경우 특수 처리
        if action_state == "grid" and action_name == "click":
            selector = action_args.get("selector", "")
            # selector에서 name 속성 값 추출
            name_match = re.search(r"\[name=['\"](.+?)['\"]\]", selector)
            if name_match:
                target_text = name_match.group(1)
                await click_apply_for_text(page, target_text)
            else:
                # 파싱 실패 시 일반 실행으로 폴백
                await executor.run(action_def)
        else:
            # 일반 액션 실행
            await executor.run(action_def)
    except Exception as e:
        print(f"[오류] 액션 실행 실패: {e}")
```

---

### 3. Import 추가

**위치:** 파일 상단 (8~19줄)

```python
import re
from playwright.async_api import Page
```

---

## 📊 실행 흐름

### 일반 클릭 액션
```
백엔드 → 실행 웹
{
  "action": {
    "name": "click",
    "args": {"selector": "#button"}
  }
}
↓
executor.run(action_def) 실행
```

### Grid 클릭 액션
```
백엔드 → 실행 웹
{
  "action": {
    "name": "click",
    "args": {"selector": "[name='[성적]이수구분변경신청']"},
    "state": "grid"  ← 이 필드가 있으면!
  }
}
↓
1. selector에서 텍스트 추출: "[성적]이수구분변경신청"
2. click_apply_for_text(page, "[성적]이수구분변경신청") 호출
3. Grid에서 해당 텍스트 셀 찾기
4. aria-label 파싱: "3행 5열 [성적]이수구분변경신청"
5. 3행 2열의 버튼 클릭
```

---

## 🧪 테스트 시나리오

### 테스트 1: Grid 클릭 (정상 케이스)

**백엔드 액션:**
```json
{
  "action": {
    "name": "click",
    "args": {
      "selector": "[name='[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)']"
    },
    "state": "grid"
  }
}
```

**기대 결과:**
1. Grid에서 "[학적]휴학신청..." 텍스트가 포함된 셀 찾기
2. 해당 행의 신청 버튼 클릭 성공

**로그 예시:**
```
  ▶ [3/5] click: {'selector': "[name='[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)']"}
     [State] grid
     [Grid 모드] '[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)' 텍스트로 신청 버튼 찾기 시작
[Grid] 텍스트 '[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)'를 포함한 셀 찾기...
[Grid] 발견된 셀의 aria-label: 3행 5열 [학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)
[Grid] 파싱된 위치: 3행, 신청 버튼은 2열에 위치
[Grid] 3행 2열의 신청 버튼 클릭...
[Grid] 신청 버튼 클릭 완료!
```

---

### 테스트 2: 일반 클릭 (state 없음)

**백엔드 액션:**
```json
{
  "action": {
    "name": "click",
    "args": {
      "selector": "#submitButton"
    }
  }
}
```

**기대 결과:**
- `state` 필드가 없으므로 기존 `executor.run()` 실행
- 정상 클릭 동작

---

### 테스트 3: selector 파싱 실패 (폴백)

**백엔드 액션:**
```json
{
  "action": {
    "name": "click",
    "args": {
      "selector": ".some-class"  ← name 속성 없음
    },
    "state": "grid"
  }
}
```

**기대 결과:**
- selector에서 `[name='...']` 패턴을 찾을 수 없음
- 경고 로그 출력
- 일반 `executor.run()`으로 폴백
- 정상 클릭 시도

**로그 예시:**
```
     [Grid 경고] selector에서 name 속성을 파싱할 수 없음: .some-class
```

---

## ⚙️ 설정

### 신청 버튼 열 번호 변경

현재 신청 버튼은 **2열**에 있다고 가정하고 있습니다. 만약 다른 열에 있다면:

**수정 위치:** `click_apply_for_text()` 함수 (73줄)

```python
# 신청 버튼이 있는 열 번호 (현재: 2열)
apply_col_index = "2"  # ← 이 값을 변경
```

---

## 🚨 주의사항

### 1. aria-label 형식 의존성

이 기능은 nDRIMS Grid의 `aria-label` 형식에 의존합니다:
- 형식: `"{행}행 {열}열 {텍스트}"`
- 예: `"3행 5열 [학적]휴학신청(...)"`

만약 형식이 다르면 파싱이 실패합니다.

### 2. 신청 버튼 위치

현재 신청 버튼이 **2열**에 있다고 가정합니다. nDRIMS 업데이트로 위치가 변경되면 `apply_col_index` 값을 수정해야 합니다.

### 3. 텍스트 일치

`target_text`는 **정확히 일치**해야 합니다. 백엔드에서 전달하는 텍스트가 Grid의 실제 텍스트와 다르면 찾을 수 없습니다.

---

## 📂 수정된 파일

```
nDrimsWeb/
└── execution_web_service_gpt.py  ✅ 수정됨
    ├── Import 추가 (re, Page)
    ├── click_apply_for_text() 함수 추가 (38~86줄)
    └── execute_trajectory_in_browser() 수정 (478~513줄)
```

---

## 🎯 다음 단계

### 필수 테스트
- [ ] Grid 클릭 액션 테스트 (성적 관련 메뉴)
- [ ] 일반 클릭 액션이 여전히 작동하는지 확인
- [ ] selector 파싱 실패 시 폴백 동작 확인

### 개선 사항 (선택)
- [ ] 신청 버튼 열 번호를 동적으로 찾기
- [ ] Grid가 아닌 다른 상태(state) 추가 지원
- [ ] 에러 핸들링 강화 (셀을 찾을 수 없는 경우 등)

---

## 📞 문제 해결

### 문제 1: "Grid 오류: aria-label을 읽을 수 없음"
**원인:** 텍스트를 포함한 셀을 찾을 수 없음
**해결:**
1. 백엔드에서 전달한 텍스트가 정확한지 확인
2. Grid가 로드되었는지 확인 (페이지 대기 시간 추가)

### 문제 2: "Grid 오류: 행/열 정보를 파싱할 수 없음"
**원인:** aria-label 형식이 예상과 다름
**해결:**
1. 실제 aria-label 형식 확인
2. 정규식 패턴 수정 (`r"(\d+)행\s+(\d+)열"`)

### 문제 3: 신청 버튼을 찾을 수 없음
**원인:** 신청 버튼이 2열에 없음
**해결:**
1. 실제 버튼 위치 확인
2. `apply_col_index` 값 변경

---

**Grid 클릭 기능 추가 완료! 🎉**

이제 백엔드에서 `state: "grid"`를 포함한 액션을 보내면 자동으로 Grid에서 텍스트를 찾아 신청 버튼을 클릭합니다.
