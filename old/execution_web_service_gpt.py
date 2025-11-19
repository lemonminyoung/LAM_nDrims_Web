"""
실행 웹 폴링 서비스
- 백엔드에서 명령을 폴링
- Playwright로 nDRIMS 자동화 실행
- 결과를 백엔드로 전송
"""

import time
import json
import requests
import base64
import asyncio
from pathlib import Path

from explaywright_gpt import run_trajectory, ActionExecutor
from scrape import scrape_current_ui_state, scrape_current_page
import playwright_client

# 백엔드 API URL
BACKEND_URL = "https://ndrims-project-lam.onrender.com"

# 폴링 간격 (초)
POLLING_INTERVAL = 5

# 브라우저 객체 저장 (가비지 컬렉션 방지)
ACTIVE_BROWSERS = []

# 로그인 상태 저장
LOGIN_STATUS = {
    "logged_in": False,
    "student_id": None,
    "last_url": None,
}


async def poll_commands():
    print("\n" + "=" * 60)
    print("실행 웹 폴링 서비스 시작")
    print("=" * 60)
    print(f"백엔드 URL: {BACKEND_URL}")
    print(f"폴링 간격: {POLLING_INTERVAL}초")
    print("=" * 60 + "\n")

    # 시작 시 백엔드에 초기화 신호 전송 + 로컬 상태 초기화
    LOGIN_STATUS["logged_in"] = False
    LOGIN_STATUS["student_id"] = None
    LOGIN_STATUS["last_url"] = None

    try:
        print("[초기화] 백엔드에 실행웹 시작 신호 전송...")
        init_response = requests.post(
            f"{BACKEND_URL}/execution_web/init",
            json={"status": "started"},
            timeout=5,
        )
        if init_response.status_code == 200:
            print("[초기화] 백엔드 초기화 완료")
        else:
            print(f"[경고] 백엔드 초기화 실패: {init_response.status_code}")
    except Exception as e:
        print(f"[경고] 백엔드 초기화 신호 전송 실패: {e}")

    while True:
        try: 
            if ACTIVE_BROWSERS: # 브라우저 닫힘 감시
                for b in ACTIVE_BROWSERS[:]:
                    page = b.get("page")
                    if page and page.is_closed():
                        print("[모니터링] 브라우저 창이 닫혔습니다. 세션 정리 중...")
                        await cleanup_browsers()
                        try:
                            requests.post(f"{BACKEND_URL}/logout", timeout=5)
                            print("[모니터링] 백엔드에 로그아웃 요청 전송 완료")
                        except Exception as e:
                            print(f"[모니터링] 백엔드 로그아웃 요청 실패: {e}")
                        # 한 번 감지되면 추가 감지 방지
                        break
                
            # 현재 브라우저 상태를 함께 전달
            browser_count = len(ACTIVE_BROWSERS)
            browser_running = browser_count > 0

            response = requests.get(
                f"{BACKEND_URL}/command",
                params={
                    "browser_running": str(browser_running).lower(),
                    "browser_count": browser_count,
                },
                timeout=10,
            )
            command = response.json()

            cmd_type = command.get("type")

            # 명령 없음
            if command.get("has_task") is False or cmd_type == "none":
                await asyncio.sleep(POLLING_INTERVAL)
                continue

            # 로그인
            if cmd_type == "login":
                print("\n[명령 수신] 로그인 요청")
                print(f"  - 학번: {command['student_id']}")
                if "token" in command:
                    print(f"  - 토큰: {command['token']}")
                await execute_login_and_send_result(
                    command["student_id"], command["password"]
                )

            # 상태 / 프롬프트
            elif cmd_type == "state":
                prompt = command.get("prompt_text", "")
                print("\n[명령 수신] 프롬프트 명령")
                print(f"  - 프롬프트: {prompt}")
                await execute_prompt_and_send_state(prompt)
                print("\n[명령 수신] 액션 명령 요청")
                await execute_action_command()
            
                print("\n[여기까진 왔어]")

            # 액션 실행
            elif cmd_type == "action":
                print("\n[명령 수신] 액션 명령 요청")
                await execute_action_command()

            # 브라우저 종료
            elif cmd_type in ("shutdown","logout"):
                print("\n[명령 수신] 브라우저 닫기({cmd_type})")
                print(f"[디버그] 현재 ACTIVE_BROWSERS 개수: {len(ACTIVE_BROWSERS)}")

                await cleanup_browsers()

                print("[완료] 브라우저 닫기 완료")
                print(f"[디버그] 정리 후 ACTIVE_BROWSERS 개수: {len(ACTIVE_BROWSERS)}")

            else:
                print(f"[경고] 알 수 없는 명령: {cmd_type}")

        except requests.exceptions.ConnectionError:
            print("[오류] 백엔드 서버에 연결할 수 없습니다.")
            print("  → 백엔드 서버가 실행 중인지 확인하세요.")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[오류] 폴링 중 예외 발생: {e}")
            import traceback

            traceback.print_exc()
            await asyncio.sleep(POLLING_INTERVAL)




async def execute_login_and_send_result(student_id, password):
    """
    Playwright로 로그인 실행하고 결과를 즉시 백엔드로 전송
    """
    global ACTIVE_BROWSERS, LOGIN_STATUS


    # 기존 브라우저 정리
    if ACTIVE_BROWSERS:
        print("[정리] 기존 브라우저 정리 중...")
        await cleanup_browsers()

    print("[실행] Playwright 로그인 시작...")

    try:
        trajectory_file = Path(__file__).parent / "trajectory_login_only.json"

        if not trajectory_file.exists():
            print(f"[오류] trajectory 파일을 찾을 수 없습니다: {trajectory_file}")
            result = {
                "loginSuccess": False,
                "message": "trajectory 파일을 찾을 수 없습니다.",
            }
            send_state(result)
            return

        actions = json.loads(trajectory_file.read_text(encoding="utf-8"))
        context = {"DG_USERNAME": student_id, "DG_PASSWORD": password}

        try:
            login_success, page, browser, ctx = await run_trajectory(
                actions, context, keep_browser_open=True
            )

            if login_success and page and browser and ctx:
                print("[성공] 로그인 완료")

                LOGIN_STATUS["logged_in"] = True
                LOGIN_STATUS["student_id"] = student_id
                try:
                    LOGIN_STATUS["last_url"] = page.url
                except Exception:
                    LOGIN_STATUS["last_url"] = "nDRIMS 메인 페이지"

                send_state(
                    {
                        "loginSuccess": True,
                        "message": "로그인 성공",
                        "student_id": student_id,
                        "last_url": LOGIN_STATUS["last_url"],
                    }
                )
                print("[완료] 로그인 성공 → 백엔드로 전송 완료\n")

                # 로그인 성공한 세션만 유지
                ACTIVE_BROWSERS.append(
                    {"page": page, "browser": browser, "context": ctx}
                )
                print("[INFO] 브라우저를 열어둔 채로 유지합니다.")
            else:
                print("[실패] 로그인 실패 (메인 페이지로 이동하지 않음)")
                await cleanup_browsers()
                send_state(
                    {
                        "loginSuccess": False,
                        "message": "로그인 실패: 인증 정보가 올바르지 않거나, 메인 페이지로 이동하지 않았습니다.",
                    }
                )
                print("[완료] 로그인 실패 → 백엔드로 전송 완료\n")

        except Exception as inner_e:
            error_msg = str(inner_e)
            print(f"[실패] 로그인 오류: {error_msg}")
            await cleanup_browsers()

            if "Timeout" in error_msg or "waiting for" in error_msg:
                msg = "로그인 실패: 응답 지연 또는 잘못된 인증 정보"
            else:
                msg = f"로그인 실패: {error_msg}"

            send_state({"loginSuccess": False, "message": msg})
            print("[완료] 로그인 실패 → 백엔드로 전송 완료\n")

    except Exception as e:
        print(f"[실패] 로그인 처리 중 예외: {e}")
        await cleanup_browsers()
        send_state(
            {
                "loginSuccess": False,
                "message": f"로그인 실패: {str(e)}",
            }
        )
        print("[완료] 로그인 실패 → 백엔드로 전송 완료\n")


async def capture_ui_state(page):
    """
    현재 페이지의 스크린샷과 UI 상태를 캡처
    """
    print("[캡처 시작] 스크린샷과 UI 상태 수집 중...")

    try:
        if page.is_closed():
            print("[오류] 페이지가 이미 닫혔습니다")
            return None

        # 스크린샷
        #screenshot_bytes = await page.screenshot(full_page=True)
        #screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        #print("[캡처 완료] 스크린샷 캡처 성공")

        # UI 상태
        ui_state = await scrape_current_ui_state(page)
        print("[캡처 완료] UI 상태 수집 성공")

        return {
            #"screenshot": screenshot_base64,
            "ui_state": ui_state,
        }
    except Exception as e:
        print(f"[캡처 오류] 스크린샷/상태 캡처 실패: {e}")
        import traceback

        traceback.print_exc()
        return None


async def execute_prompt_and_send_state(prompt_text: str):
    """
    프롬프트 명령 처리 + 현재 UI 상태를 백엔드로 전송
    (스크린샷 제거 버전)
    """
    global LOGIN_STATUS, ACTIVE_BROWSERS

    print(f"[실행] 프롬프트 처리 시작: {prompt_text}")

    try:
        #  로그인 여부 확인
        if not ACTIVE_BROWSERS:
            print("[경고] 브라우저가 없습니다. 로그인이 필요합니다.")
            send_state(
                {
                    "success": False,
                    "needs_login": True,
                    "message": "브라우저가 닫혔습니다. 다시 로그인하세요.",
                    "prompt": prompt_text,
                }
            )
            return

        if not LOGIN_STATUS["logged_in"]:
            print("[경고] 로그인되지 않았습니다.")
            send_state(
                {
                    "success": False,
                    "needs_login": True,
                    "message": "먼저 로그인하세요.",
                    "prompt": prompt_text,
                }
            )
            return

        #  상태 출력
        print(f"[상태] 로그인됨 - 학번: {LOGIN_STATUS['student_id']}")
        print(f"[상태] 마지막 URL: {LOGIN_STATUS.get('last_url', '알 수 없음')}")

        #  현재 페이지 UI 상태 수집
        page = ACTIVE_BROWSERS[-1]["page"]
        try:
            ui_state = await scrape_current_ui_state(page)
            print("[상태] UI 상태 수집 성공")
        except Exception as e:
            print(f"[오류] UI 상태 수집 실패: {e}")
            import traceback
            traceback.print_exc()
            ui_state = None

        #  백엔드로 전송할 데이터 구성 (스크린샷 제거됨)
        state_data = {
            "success": True,
            "prompt": prompt_text,
            "student_id": LOGIN_STATUS["student_id"],
            "logged_in": LOGIN_STATUS["logged_in"],
            "last_url": LOGIN_STATUS.get("last_url", "알 수 없음"),
            "message": f"프롬프트 '{prompt_text}'를 수신했습니다. nDRIMS에 로그인된 상태입니다.",
            "ui_state": ui_state,
        }

        #  전송 로그
        if ui_state:
            print("[상태] UI 상태를 포함하여 백엔드로 전송 중...")
        else:
            print("[경고] UI 상태가 비어있습니다. 기본 정보만 전송합니다.")

        #  백엔드로 상태 전송
        send_state(state_data)
        print("[완료] 프롬프트 처리 완료\n")

    except Exception as e:
        print(f"[실패] 프롬프트 처리 오류: {e}")
        import traceback
        traceback.print_exc()

        send_state(
            {
                "success": False,
                "message": f"프롬프트 처리 실패: {str(e)}",
                "prompt": prompt_text,
            }
        )
        print("[완료] 프롬프트 처리 실패 → 백엔드로 전송 완료\n")



def extract_expected_page_title(actions):
    """
    액션 리스트에서 예상 페이지 제목 추출
    (마지막 click의 text= 또는 name= 기반)
    """
    import re

    for action_item in reversed(actions):
        action_def = action_item.get("action", {})
        action_name = action_def.get("name")

        if action_name == "click":
            selector = action_def.get("args", {}).get("selector", "")

            text_match = re.search(r"text=([^\]]+)", selector)
            if text_match:
                title = text_match.group(1).strip()
                print(f"[추출] 예상 페이지 제목: '{title}' (text= 패턴)")
                return title

            name_match = re.search(r"name=['\"]([^'\"]+)['\"]", selector)
            if name_match:
                title = name_match.group(1).strip()
                print(f"[추출] 예상 페이지 제목: '{title}' (name= 패턴)")
                return title

    print("[추출] 예상 페이지 제목을 찾을 수 없음")
    return None


async def execute_trajectory_in_browser(actions, action_description, browser_info, verification=None):
    """
    이미 열린 브라우저에서 trajectory 액션 실행 + 결과 검증
    """
    page = browser_info["page"]

    if page.is_closed():
        print("[경고] 페이지가 닫혀 있어 액션을 실행할 수 없습니다.")
        send_state(
            {
                "action_success": False,
                "message": "페이지 세션이 종료되었습니다. 다시 로그인해주세요.",
                "needs_login": True,
                "action_description": action_description,
            }
        )
        return

    print("=" * 60)
    print(f"[실행] trajectory 시작: '{action_description}'")
    print(f"[INFO] 실행할 액션 수: {len(actions)}")
    print("=" * 60)

    executor = ActionExecutor(page, {})

    success_count = 0
    fail_count = 0

    for idx, step in enumerate(actions):
        action_def = step.get("action", {})
        action_name = action_def.get("name")
        action_args = action_def.get("args", {})

        print(f"  ▶ [{idx+1}/{len(actions)}] {action_name}: {action_args}")

        try:
            await executor.run(action_def)
            success_count += 1
        except Exception as e:
            print(f"    [오류] 액션 실행 실패: {e}")
            import traceback
            traceback.print_exc()
            fail_count += 1

    if fail_count > 0:
        print(f"[완료] Trajectory 액션 실행 완료 (성공: {success_count}, 실패: {fail_count})")
    else:
        print(f"[성공] Trajectory 액션 실행 완료 ({success_count}개 액션 모두 성공)")

    print("=" * 60)
    print("[검증 단계] trajectory 실행 후 페이지 상태 확인 시작")
    print("=" * 60)

    # 검증 로직
    try:
        is_success = False
        verification_message = ""

        # 예상 제목 결정
        if verification:
            expected_title = verification.get("expected_text", "") or ""
            print(f"[검증] verification 지정 예상 제목: '{expected_title}'")
        else:
            expected_title = extract_expected_page_title(actions)
            print(f"[검증] trajectory 내부에서 예상 제목 추출: '{expected_title}'")

        # 🔍 검증 시작 로그 추가
        print("[검증] ---- scrape_current_page() 호출 시작 ----")
        current_page_info = await scrape_current_page(page)
        print("[검증] ---- scrape_current_page() 호출 완료 ----")

        actual_title = current_page_info.get("title", "")
        print(f"[검증] 실제 페이지/팝업 제목: '{actual_title}'")

        # 비교
        if expected_title:
            # 빈 문자열 처리: actual_title이 비어있으면 불일치로 처리
            if actual_title and (expected_title in actual_title or actual_title in expected_title):
                is_success = True
                verification_message = f"'{expected_title}' 페이지 로드 완료"
                print("[검증] ✓ 제목 일치")
            else:
                is_success = fail_count == 0
                verification_message = f"'{expected_title}' 페이지 도달 실패 (현재: '{actual_title}')"
                print("[검증] ✗ 제목 불일치")
        else:
            print("[검증] 예상 제목 없음 - 액션 실행 성공 여부로 판단")
            is_success = fail_count == 0
            verification_message = "액션 실행 완료" if is_success else "일부 액션 실행 실패"

        # 결과 전송
        if is_success:
            print(f"[성공] 액션 목적 달성: '{action_description}'")
            result = {
                "action_success": True,
                "action_description": action_description,
                "message": f"액션 성공: {verification_message}",
                "verified": True,
            }
        else:
            print(f"[실패] 액션 목적 미달성: '{action_description}'")
            result = {
                "action_success": False,
                "action_description": action_description,
                "message": f"액션 실패: {verification_message}",
                "verified": False,
            }

        print("[검증] ---- 상태 전송 시작 ----")
        send_state(result)
        print("[검증] ---- 상태 전송 완료 ----")

    except Exception as e:
        print(f"[오류] 페이지 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        send_state(
            {
                "action_success": False,
                "action_description": action_description,
                "message": f"검증 중 오류 발생: {e}",
            }
        )

    print("=" * 60)
    print("[검증 단계 종료]")
    print("=" * 60)


async def execute_action_command():
    """
    백엔드에서 액션 명령을 가져와서 trajectory 타입이면 실행
    """
    global ACTIVE_BROWSERS
    print("[실행] 액션 명령 가져오기 시작...")

    try:
        response = requests.get(f"{BACKEND_URL}/action", timeout=10)

        if response.status_code == 404:
            print("[경고] state.json 파일이 없습니다.")
            return

        if response.status_code != 200:
            print(f"[오류] 액션 가져오기 실패: {response.status_code}")
            return

        action_data = response.json()
        print(
            f"[액션 수신] {json.dumps(action_data, ensure_ascii=False, indent=2)}"
        )

        generated_action = action_data.get("generated_action")
        if not generated_action:
            print("[경고] generated_action이 없습니다.")
            return

        # trajectory 타입 액션이면 실행
        if generated_action.get("type") == "trajectory":
            actions_file = generated_action.get("actions_file")
            original_description = generated_action.get("description", "")

            print(f"[실행] Trajectory 액션 실행: {actions_file}")
            if original_description:
                print(f"[원본 목적] {original_description}")

            trajectory_path = Path(__file__).parent / actions_file

            if not trajectory_path.exists():
                print(
                    f"[오류] Trajectory 파일을 찾을 수 없습니다: {trajectory_path}"
                )
                return

            trajectory_data = json.loads(
                trajectory_path.read_text(encoding="utf-8")
            )

            # 새 형식/구 형식 모두 지원
            if isinstance(trajectory_data, dict):
                actions = trajectory_data.get("actions", [])
                verification = trajectory_data.get("verification")
                print("[INFO] Trajectory 새 형식 감지 (검증 정보 포함)")
            else:
                actions = trajectory_data
                verification = None
                print("[INFO] Trajectory 구 형식 감지 (검증 정보 없음)")

            # 마지막 액션에서 실제 목적 추출 (더 정확함)
            extracted_title = extract_expected_page_title(actions)
            action_description = extracted_title if extracted_title else original_description
            print(f"[실제 목적] {action_description}")

            if ACTIVE_BROWSERS:
                print("[INFO] 이미 열려있는 브라우저에서 액션 실행")
                browser_info = ACTIVE_BROWSERS[-1]
                await execute_trajectory_in_browser(
                    actions, action_description, browser_info, verification
                )
            else:
                print("[경고] 열려있는 브라우저가 없습니다. 먼저 로그인하세요.")
                send_state(
                    {
                        "action_success": False,
                        "needs_login": True,
                        "message": "브라우저가 닫혔습니다. 다시 로그인하세요.",
                        "action_description": action_description,
                    }
                )

        else:
            print(
                f"[INFO] 액션 타입 '{generated_action.get('type')}'는 아직 구현되지 않았습니다."
            )

        print("[완료] 액션 명령 처리 완료\n")

    except Exception as e:
        print(f"[실패] 액션 명령 처리 오류: {e}")
        import traceback

        traceback.print_exc()


def send_state(data: dict):
    """
    백엔드로 상태 전송
    """
    try:
        response = requests.post(
            f"{BACKEND_URL}/state",
            json={"data": data},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code == 200:
            print("[전송 완료] 상태 전송 성공")
        else:
            print(f"[전송 실패] 상태 코드: {response.status_code}")
    except Exception as e:
        print(f"[전송 오류] {e}")


async def cleanup_browsers():
    """모든 브라우저 인스턴스 종료 + 상태 초기화"""
    global ACTIVE_BROWSERS, LOGIN_STATUS

    print(f"[정리] 브라우저 종료 시작 (총 {len(ACTIVE_BROWSERS)}개)")

    if not ACTIVE_BROWSERS:
        print("[정리] 종료할 브라우저가 없습니다")
        try:
            await playwright_client.close_all()
        except asyncio.CancelledError:
            print("[정리] 브라우저 정리 중 취소됨 (정상)")
        except Exception as e:
            print(f"[정리] 브라우저 정리 오류: {e}")
    else:
        for idx, browser_info in enumerate(ACTIVE_BROWSERS):
            try:
                browser = browser_info.get("browser")
                context = browser_info.get("context")
                page = browser_info.get("page")

                print(f"[정리] 브라우저 #{idx+1} 종료 시작...")

                if page:
                    try:
                        await page.close()
                        print(f"[정리] 페이지 #{idx+1} 종료 완료")
                    except asyncio.CancelledError:
                        print(
                            f"[정리] 페이지 #{idx+1} 종료 중 취소됨 (정상)"
                        )
                    except Exception as e:
                        print(
                            f"[정리] 페이지 #{idx+1} 종료 실패: {e}"
                        )

                if context:
                    try:
                        await context.close()
                        print(f"[정리] 컨텍스트 #{idx+1} 종료 완료")
                    except asyncio.CancelledError:
                        print(
                            f"[정리] 컨텍스트 #{idx+1} 종료 중 취소됨 (정상)"
                        )
                    except Exception as e:
                        print(
                            f"[정리] 컨텍스트 #{idx+1} 종료 실패: {e}"
                        )

                # browser 자체는 싱글톤 핸들에서 닫으므로 여기선 패스
            except asyncio.CancelledError:
                print(
                    f"[정리] 브라우저 #{idx+1} 정리 중 취소됨 (정상)"
                )
            except Exception as e:
                print(f"[정리] 브라우저 #{idx+1} 정리 오류: {e}")

        ACTIVE_BROWSERS.clear()
        print("[정리] ACTIVE_BROWSERS 리스트 클리어 완료")

        try:
            await playwright_client.close_all()
            print("[정리] 모든 브라우저 정리 완료")
        except asyncio.CancelledError:
            print("[정리] Playwright 정리 중 취소됨 (정상)")
        except Exception as e:
            print(f"[정리] Playwright 정리 오류: {e}")

    # LOGIN_STATUS 초기화
    LOGIN_STATUS["logged_in"] = False
    LOGIN_STATUS["student_id"] = None
    LOGIN_STATUS["last_url"] = None
    print("[정리] LOGIN_STATUS 초기화 완료")


if __name__ == "__main__":
    try:
        asyncio.run(poll_commands())
    except Exception as e:
        print("\n\n[오류] 예상치 못한 오류:", e)
        import traceback

        traceback.print_exc()
