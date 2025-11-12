"""
Playwright 비동기 싱글톤 인스턴스
"""

from playwright.async_api import async_playwright

_playwright_instance = None
_browser = None

async def get_playwright():
    """Playwright 싱글톤 인스턴스 반환"""
    global _playwright_instance
    if _playwright_instance is None:
        print("[Playwright] 비동기 인스턴스 생성 중...")
        _playwright_instance = await async_playwright().start()
        print("[Playwright] 비동기 인스턴스 생성 완료")
    return _playwright_instance

async def get_browser():
    """브라우저 인스턴스 반환 (재사용)"""
    global _browser
    pw = await get_playwright()

    # 브라우저가 없거나 연결이 끊어졌으면 새로 생성
    needs_new_browser = False
    if _browser is None:
        needs_new_browser = True
    else:
        try:
            if not _browser.is_connected():
                needs_new_browser = True
        except Exception:
            needs_new_browser = True

    if needs_new_browser:
        print("[Browser] 새 브라우저 시작...")
        # 환경변수로 headless 모드 제어 (서버: True, 로컬: False)
        import os
        headless_mode = os.getenv("HEADLESS", "False").lower() == "true"
        _browser = await pw.chromium.launch(headless=headless_mode)

    return _browser

async def close_all():
    """모든 리소스 정리"""
    global _browser, _playwright_instance
    import asyncio

    if _browser:
        try:
            await _browser.close()
            print("[Playwright] 브라우저 종료 완료")
        except asyncio.CancelledError:
            print("[Playwright] 브라우저 종료 중 취소됨 (정상)")
            pass
        except Exception as e:
            print(f"[Playwright] 브라우저 종료 오류: {e}")
        finally:
            _browser = None

    if _playwright_instance:
        try:
            await _playwright_instance.stop()
            print("[Playwright] 인스턴스 정리 완료")
        except asyncio.CancelledError:
            print("[Playwright] 인스턴스 정리 중 취소됨 (정상)")
            pass
        except Exception as e:
            print(f"[Playwright] 인스턴스 정리 오류: {e}")
        finally:
            _playwright_instance = None

    print("[Playwright] 모든 리소스 정리 완료")
