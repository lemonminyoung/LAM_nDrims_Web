# Grid 클릭 기능 통합 완료 (최종)

**작성일:** 2025-11-14
**작업 내용:** Grid 상태에서 텍스트로 행 찾아 신청 버튼 클릭하는 기능을 `ActionExecutor`에 통합

---

## 📋 변경 사항 요약

기존에 `execution_web_service_gpt.py`에 독립 함수로 추가했던 `click_apply_for_text()`를 **`ActionExecutor` 클래스의 메서드로 이동**하여 완전히 통합했습니다.

---

## 🎯 작동 방식

### 백엔드에서 전달되는 액션

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

### 실행 흐름

```
1. execution_web_service_gpt.py (실행 웹)
   ├─ state: "grid" 감지
   ├─ action name을 "click" → "click_grid"로 변경
   └─ executor.run({"name": "click_grid", "args": {...}})

2. explaywright_gpt.py (ActionExecutor)
   ├─ ActionExecutor.click_grid() 호출
   ├─ args["selector"]에서 텍스트 추출
   ├─ Grid에서 텍스트 셀 찾기
   ├─ aria-label에서 행 번호 파싱
   └─ 같은 행의 2열 신청 버튼 클릭
```

---

## 🔧 수정된 파일

### 1. `explaywright_gpt.py`

**파일 경로:** `C:\Users\김민영\Desktop\nDrims-project\nDrimsWeb\explaywright_gpt.py`

#### 변경 1: Import 추가 (2줄)
```python
import re
```

#### 변경 2: `ActionExecutor.click_grid()` 메서드 추가 (67~123줄)

```python
async def click_grid(self, args):
    """
    Grid에서 특정 텍스트를 찾아 해당 행의 '신청' 버튼을 클릭하는 액션

    Args:
        args: {
            "selector": "[name='[성적]이수구분변경신청']",  # selector에서 텍스트 추출
            "target_text": "[성적]이수구분변경신청"  # 또는 직접 텍스트 전달
        }
    """
    # target_text가 직접 주어지지 않으면 selector에서 추출
    target_text = args.get("target_text")
    if not target_text:
        selector = args.get("selector", "")
        # selector에서 name 속성 값 추출: "[name='텍스트']" → "텍스트"
        name_match = re.search(r"\[name=['\"](.+?)['\"]\]", selector)
        if name_match:
            target_text = name_match.group(1)
        else:
            raise ValueError(f"[Grid 오류] target_text가 없고 selector에서도 추출 불가: {selector}")

    print(f"[Grid] 텍스트 '{target_text}'를 포함한 셀 찾기...")

    # 1. 텍스트를 가진 gridcell 찾기 (aria-label 안에 텍스트 포함)
    text_cell = self.page.get_by_role(
        "gridcell",
        name=re.compile(re.escape(target_text))
    ).first

    # 셀의 aria-label 읽기: 예) "1행 3열 [학적]휴학신청(…)"
    aria_label = await text_cell.get_attribute("aria-label")
    if not aria_label:
        raise RuntimeError(f"[Grid 오류] aria-label을 읽을 수 없음")

    print(f"[Grid] 발견된 셀의 aria-label: {aria_label}")

    # 2. "1행 3열 ..." 에서 행/열 번호 파싱
    m = re.search(r"(\d+)행\s+(\d+)열", aria_label)
    if not m:
        raise RuntimeError(f"[Grid 오류] 행/열 정보를 파싱할 수 없음: {aria_label}")

    row_index = m.group(1)
    # 신청 버튼이 있는 열 번호 (2열이라고 가정)
    apply_col_index = "2"

    print(f"[Grid] 파싱된 위치: {row_index}행, 신청 버튼은 {apply_col_index}열에 위치")

    # 3. 같은 행(row_index), 신청 버튼 셀의 aria-label 패턴 만들기
    apply_button = self.page.get_by_role(
        "button",
        name=re.compile(rf"{row_index}행\s+{apply_col_index}열")
    ).first

    # 4. 클릭
    print(f"[Grid] {row_index}행 {apply_col_index}열의 신청 버튼 클릭...")
    await apply_button.click()
    print(f"[Grid] 신청 버튼 클릭 완료!")
```

---

### 2. `execution_web_service_gpt.py`

**파일 경로:** `C:\Users\김민영\Desktop\nDrims-project\nDrimsWeb\execution_web_service_gpt.py`

#### 변경 1: 불필요한 Import 제거
```python
# 제거됨: import re, from playwright.async_api import Page
```

#### 변경 2: `click_apply_for_text()` 함수 제거
- 독립 함수였던 `click_apply_for_text()` 완전히 제거됨

#### 변경 3: `execute_trajectory_in_browser()` 수정 (478~507줄)

```python
for idx, step in enumerate(actions):
    action_def = step.get("action", {})
    action_name = action_def.get("name")
    action_args = action_def.get("args", {})
    action_state = action_def.get("state")  # state 필드 추출

    print(f"  ▶ [{idx+1}/{len(actions)}] {action_name}: {action_args}")
    if action_state:
        print(f"     [State] {action_state}")

    try:
        # state가 "grid"이고 click 액션인 경우 액션 이름을 click_grid로 변경
        if action_state == "grid" and action_name == "click":
            print(f"     [Grid 모드] click 액션을 click_grid로 변경")
            # 액션 이름을 click_grid로 변경하여 실행
            modified_action = {
                "name": "click_grid",
                "args": action_args
            }
            await executor.run(modified_action)
            success_count += 1
        else:
            # 일반 액션 실행
            await executor.run(action_def)
            success_count += 1
    except Exception as e:
        print(f"    [오류] 액션 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        fail_count += 1
```

---

## 📊 기존 방식 vs 통합 방식 비교

### ❌ 기존 방식 (문제점)
```
execution_web_service_gpt.py
├─ click_apply_for_text(page, target_text) 독립 함수
│  ├─ page 객체를 직접 받음
│  └─ ActionExecutor와 분리됨
│
└─ execute_trajectory_in_browser()
   └─ if state == "grid":
       └─ click_apply_for_text(page, text) 직접 호출
```

**문제:**
- `ActionExecutor`의 다른 액션들과 일관성 없음
- `page` 객체를 별도로 전달해야 함
- 확장성 낮음

---

### ✅ 통합 방식 (현재)
```
explaywright_gpt.py
└─ ActionExecutor
   ├─ async def click(self, args)
   ├─ async def type(self, args)
   ├─ async def click_grid(self, args)  ← 새로 추가!
   └─ async def run(self, act)
      └─ getattr(self, name)() 호출

execution_web_service_gpt.py
└─ execute_trajectory_in_browser()
   └─ if state == "grid":
       └─ executor.run({"name": "click_grid", ...})
          └─ ActionExecutor.click_grid() 자동 호출
```

**장점:**
- ✅ 모든 액션이 `ActionExecutor`에 통합
- ✅ `executor.run()` 메커니즘 활용
- ✅ `self.page` 사용으로 일관성 유지
- ✅ 확장성 높음 (다른 state 추가 가능)

---

## 🧪 테스트 시나리오

### 테스트 1: Grid 클릭 (정상)

**입력:**
```json
{
  "action": {
    "name": "click",
    "args": {"selector": "[name='[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)']"},
    "state": "grid"
  }
}
```

**기대 로그:**
```
  ▶ [3/5] click: {'selector': "[name='[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)']"}
     [State] grid
     [Grid 모드] click 액션을 click_grid로 변경
[Grid] 텍스트 '[학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)'를 포함한 셀 찾기...
[Grid] 발견된 셀의 aria-label: 3행 5열 [학적]휴학신청(군휴학/임신출산육아휴학/질병휴학)
[Grid] 파싱된 위치: 3행, 신청 버튼은 2열에 위치
[Grid] 3행 2열의 신청 버튼 클릭...
[Grid] 신청 버튼 클릭 완료!
```

---

### 테스트 2: 일반 클릭 (state 없음)

**입력:**
```json
{
  "action": {
    "name": "click",
    "args": {"selector": "#button"}
  }
}
```

**동작:**
- `state` 필드 없음 → 일반 `click` 실행
- `ActionExecutor.click()` 호출

---

### 테스트 3: 다른 state 값

**입력:**
```json
{
  "action": {
    "name": "click",
    "args": {"selector": "#button"},
    "state": "popup"
  }
}
```

**동작:**
- `state == "popup"` → grid 조건 불만족
- 일반 `click` 실행

---

## ⚙️ 설정 변경

### 신청 버튼 열 번호 변경

**위치:** `explaywright_gpt.py` (110줄)

```python
# 현재: 2열
apply_col_index = "2"

# 변경 예시: 3열
apply_col_index = "3"
```

---

## 🎯 향후 확장 가능성

### 다른 state 추가 예시

#### `state: "popup"` 추가

**1. `explaywright_gpt.py`에 메서드 추가:**
```python
async def click_popup(self, args):
    # 팝업 내부에서 요소 클릭
    pass
```

**2. `execution_web_service_gpt.py` 수정:**
```python
if action_state == "grid" and action_name == "click":
    modified_action = {"name": "click_grid", "args": action_args}
elif action_state == "popup" and action_name == "click":
    modified_action = {"name": "click_popup", "args": action_args}
else:
    # 일반 실행
```

---

## 📂 파일 구조

```
nDrimsWeb/
├── explaywright_gpt.py              ✅ 수정됨
│   ├── import re 추가
│   └── ActionExecutor.click_grid() 추가
│
└── execution_web_service_gpt.py     ✅ 수정됨
    ├── 불필요한 import 제거
    ├── click_apply_for_text() 제거
    └── state 체크 로직 간소화
```

---

## 🚨 주의사항

### 1. 액션 이름 규칙

- 백엔드에서 `"name": "click"`로 보내도 됩니다
- `state: "grid"`가 있으면 자동으로 `click_grid`로 변환됩니다

### 2. args 전달

- `selector`만 전달하면 자동으로 텍스트 추출
- 또는 `target_text`를 직접 전달 가능:
  ```json
  {
    "action": {
      "name": "click_grid",
      "args": {
        "target_text": "[성적]이수구분변경신청"
      }
    }
  }
  ```

### 3. ActionExecutor 일관성

- 모든 커스텀 액션은 `ActionExecutor`에 메서드로 추가
- `async def` 형식 유지
- `self.page` 사용

---

## 📝 변경 이력

| 날짜 | 변경 내용 | 파일 |
|------|----------|------|
| 2025-11-14 (초기) | `click_apply_for_text()` 독립 함수 추가 | `execution_web_service_gpt.py` |
| 2025-11-14 (수정) | `ActionExecutor.click_grid()` 메서드로 이동 | `explaywright_gpt.py` |
| 2025-11-14 (최종) | 독립 함수 제거, import 정리 | `execution_web_service_gpt.py` |

---

**Grid 클릭 기능 완전 통합 완료! 🎉**

이제 `ActionExecutor`의 일부로 완벽하게 통합되어 다른 액션들과 동일한 방식으로 작동합니다.
