import json
from pathlib import Path
from playwright_client import get_browser
import asyncio


class ActionExecutor:
    def __init__(self, page, context):
        self.page = page
        self.ctx = context

    async def goto(self, args):
        await self.page.goto(args["url"])

    async def click(self, args):
        await self.page.locator(args["selector"]).click()

    async def type(self, args):
        text = args["text"]
        # 컨텍스트 변수 치환
        for k, v in self.ctx.items():
            text = text.replace("${" + k + "}", v)
        await self.page.locator(args["selector"]).fill(text)

    async def select(self, args):
        if args.get("by") == "label":
            await self.page.locator(args["selector"]).select_option(label=args["option"])
        else:
            await self.page.locator(args["selector"]).select_option(value=args["option"])

    async def wait_for(self, args):
        event = args["event"]

        if event == "nav":
            await self.page.wait_for_load_state("networkidle")

        elif event == "dom_ready":
            await self.page.wait_for_load_state("domcontentloaded")

        elif event == "selector":
            await self.page.wait_for_selector(
                args["selector"], timeout=args.get("timeout_ms", 5000)
            )

        elif event == "url_change":
            expected_url = args.get("expected_url", "")
            timeout_ms = args.get("timeout_ms", 5000)
            await self.page.wait_for_url(f"**/*{expected_url}*", timeout=timeout_ms)

        elif event == "download":
            # 다음 액션을 expect_download로 감싸서 처리하므로 여기서는 pass
            pass

    async def download_confirm(self, args):
        # 다운로드 확인용 액션 (실제 저장 경로 검사는 필요 시 구현)
        print(f"[INFO] 다운로드 확인 (폴더: {args.get('dir', '')})")

    async def sleep(self, args):
        ms = args.get("timeout_ms", 1000)
        await self.page.wait_for_timeout(ms)

    async def log(self, args):
        # log 액션 처리
        print(f"[LOG] {args.get('message', '')}")

    async def run(self, act):
        name = act["name"]
        method = getattr(self, name, None)
        if method:
            await method(act["args"])
        else:
            print(f"[WARN] 알 수 없는 액션: {name}")


async def run_trajectory(actions, context, keep_browser_open=True):
    """
    - record_1.json 처럼 'step' 안에 'state'와 'actions'가 있는 비평탄화 입력도 처리
    - flatten_steps_to_actions() 결과처럼 각 항목이 {'action': {...}}만 있는 평탄화 입력도 처리
    - 각 step/action 실행 전에 'ui_state'가 있으면 로컬 검사 함수로 상태 확인 (log 출력)
    - 'wait_for' + event=download 직후 다음 액션을 다운로드 트리거로 감싸서 expect_download 처리
    - '학적부열람' 텍스트가 role=tabpanel 내부 헤더 영역에서만 감지되면 성공 로그 출력

    Returns:
        (login_success: bool, page, browser, ctx)
        - keep_browser_open=True  : 브라우저/컨텍스트/페이지 유지해서 반환
        - keep_browser_open=False : 컨텍스트는 종료하고 page=None, ctx=None 반환
    """

    # === Playwright 실행 (비동기 싱글톤) ===
    browser = await get_browser()
    ctx = await browser.new_context(accept_downloads=True)
    page = await ctx.new_page()
    executor = ActionExecutor(page, context)

    print("\n[INFO] === Trajectory 실행 시작 ===")

    pending_download = False
    auto_probe_logged = False  # 현재 오토 프로브 로직은 주석 처리 상태

    # === 내부 헬퍼: 학적부열람 페이지 로드 여부 정확 검출 ===
    async def _is_academic_page_loaded(timeout_ms=1200) -> bool:
        try:
            locator = page.locator("role=tabpanel >> div.h3 >> text=학적부열람")
            if await locator.is_visible():
                print("[OK] 본문 헤더 감지 (role=tabpanel 내부 div.h3)")
                return True
        except Exception:
            pass

        try:
            locator = page.locator(
                "role=tabpanel >> div.cl-output.h3 >> div.cl-text",
                has_text="학적부열람",
            )
            if await locator.is_visible():
                print("[OK] 본문 헤더 감지 (cl-output.h3 구조)")
                return True
        except Exception:
            pass

        try:
            await page.wait_for_selector(
                "role=tabpanel >> div.h3 >> text=학적부열람",
                state="visible",
                timeout=timeout_ms,
            )
            print("[OK] 학적부열람 텍스트 대기 후 감지 완료")
            return True
        except Exception:
            return False

    # === 내부 헬퍼: 로컬 UI 상태 검사 ===
    async def _check_ui_state_local(label: str) -> bool:
        try:
            if label == "is_on_main_page":
                return "unis/index.do" in page.url

            elif label == "academic_menu_present":
                await _is_academic_page_loaded(400)
                return await page.locator("role=treeitem[name='학적/확인서']").count() > 0

            elif label == "academic_menu_open":
                await _is_academic_page_loaded(400)
                elem = page.locator("role=treeitem[name='학적/확인서']")
                count = await elem.count()
                expanded = await elem.first.get_attribute("aria-expanded")
                return count > 0 and expanded == "true"

            elif label == "academic_submenu_open":
                try:
                    expanded = await page.locator(
                        "role=treeitem[name='학적/확인서']"
                    ).first.get_attribute("aria-expanded")
                    if expanded == "true":
                        return True
                except Exception:
                    pass
                count = await page.locator(
                    "role=tab[aria-label*='학적부열람']"
                ).count()
                if count > 0:
                    print("학적부열람 탭 감지됨")
                    return True
                return False

            elif label == "graduation_menu_present":
                return await page.locator("role=treeitem[name='졸업']").count() > 0

            elif label == "graduation_menu_open":
                elem = page.locator("role=treeitem[name='졸업']")
                count = await elem.count()
                expanded = await elem.first.get_attribute("aria-expanded")
                return count > 0 and expanded == "true"

            else:
                return False
        except Exception as e:
            print(f"[WARN] check_ui_state 오류: {e}")
            return False

    # === 단일 액션 실행 ===
    async def _run_one_action(act, step_idx: int, sub_idx: int | None = None):
        nonlocal pending_download, auto_probe_logged

        name = act.get("name", "")
        args = act.get("args", {}) or {}
        idx_tag = (
            f"[STEP {step_idx}]"
            if sub_idx is None
            else f"[STEP {step_idx}.{sub_idx}]"
        )
        print(f"{idx_tag} {name}")

        # 직전 액션이 wait_for(download)였으면, 이번 액션을 다운로드 트리거로 처리
        if pending_download:
            try:
                async with page.expect_download() as dl_info:
                    await executor.run(act)
                download = await dl_info.value
                try:
                    print(
                        f"[SUCCESS] 다운로드 완료: {download.suggested_filename}"
                    )
                except Exception:
                    print("[SUCCESS] 다운로드 완료")
            finally:
                pending_download = False
            return

        # 다운로드 대기 설정
        if name == "wait_for" and args.get("event") == "download":
            pending_download = True
            print(f"{idx_tag} (다음 액션을 다운로드 트리거로 대기)")
            return

        # 기본 액션 실행
        await executor.run(act)

        # 오토 프로브 (현재 비활성화, 필요 시 활성화)
        # if not auto_probe_logged and name in ("goto", "click", "wait_for", "type", "select", "sleep"):
        #     try:
        #         if await _is_academic_page_loaded(600):
        #             print("[OK] '학적부열람' 헤더 감지 ✅ 페이지 로드 확인")
        #             auto_probe_logged = True
        #     except Exception:
        #         pass

    # === 입력 형식 판별 (평탄/비평탄) ===
    is_flat = all(
        (isinstance(item, dict) and "action" in item and isinstance(item["action"], dict))
        for item in actions
    )

    # 평탄 구조: 각 요소가 {"action": {...}, "state": ...} 형태
    if is_flat:
        for i, step in enumerate(actions, start=1):
            ui_state = (
                (step.get("state") or {}).get("ui_state")
                if isinstance(step, dict)
                else None
            )
            if ui_state:
                for label, expected in ui_state.items():
                    current = await _check_ui_state_local(label)
                    print(
                        f"[DEBUG] ({i}) UI상태 {label} → {current} (기대={expected})"
                    )
                    if current != expected:
                        print(
                            f"[WARN] ({i}) UI 상태 불일치: {label}"
                        )
            act = step["action"]
            await _run_one_action(act, i)

    # 비평탄 구조: 각 step 안에 state/actions 포함
    else:
        for i, step in enumerate(actions, start=1):
            if not isinstance(step, dict):
                continue

            sid = step.get("step_id", i)
            print(f"[LOG] [STEP] {sid}")

            ui_state = (step.get("state") or {}).get("ui_state")
            if ui_state:
                for label, expected in ui_state.items():
                    current = await _check_ui_state_local(label)
                    print(
                        f"[DEBUG] (step {sid}) UI상태 {label} → {current} (기대={expected})"
                    )
                    if current != expected:
                        print(
                            f"[WARN] (step {sid}) UI 상태 불일치: {label}"
                        )

            for j, a in enumerate(step.get("actions", []), start=1):
                if isinstance(a, dict) and "action" in a:
                    await _run_one_action(a["action"], i, j)
                elif (
                    isinstance(a, dict)
                    and "name" in a
                    and "args" in a
                ):
                    await _run_one_action(a, i, j)

    if pending_download:
        print(
            "[WARN] 마지막에 'wait_for download'가 있었지만 트리거 액션이 실행되지 않았습니다."
        )

    print("\n[INFO] === Trajectory 실행 완료 ===")

    # === 로그인 성공 여부 확인 (URL 기반) ===
    current_url = page.url
    print(f"[DEBUG] 최종 URL: {current_url}")

    login_success = "main/main.clx" in current_url

    if login_success:
        print("[OK] 로그인 성공 (메인 페이지 URL 확인)")
    else:
        print("[FAIL] 로그인 실패 (메인 페이지로 이동하지 않음)")

    # keep_browser_open 옵션 처리
    if keep_browser_open and login_success:
        # 로그인 성공 + 세션 유지: 호출 측에서 page/browser/ctx 관리
        return login_success, page, browser, ctx

    # 그 외에는 컨텍스트만 정리하고 최소 정보만 반환
    try:
        await ctx.close()
    except Exception:
        pass

    return login_success, None, browser, None


if __name__ == "__main__":
    # 예시 trajectory.json 로드 (로컬 테스트용)
    actions = json.loads(
        Path("trajectory_student_check.json").read_text(encoding="utf-8")
    )

    context = {
        "DG_USERNAME": "여기 입력 ㄱㄱ",
        "DG_PASSWORD": "",
    }

    asyncio.run(run_trajectory(actions, context))
