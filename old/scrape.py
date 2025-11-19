import json
import re
from playwright.async_api import Page


async def scrape_sidebar(page: Page):
    items = []
    nodes = await page.locator(".cl-tree-item").all()

    sidebar = []
    stack = []  # (level, item)

    for el in nodes:
        try:
            label_el = el.locator(":scope >> .cl-text").first  # label 추출
            label_count = await label_el.count()
            label = (await label_el.inner_text()).strip() if label_count > 0 else (await el.inner_text()).strip()

            level_attr = await el.get_attribute("aria-level") or ""  # 이 자식을 자식인척만 하고 사실 형제였음
            el_class = await el.get_attribute("class") or ""
            match = re.search(r"cl-level-(\d+)", el_class)
            level = int(level_attr) if level_attr.isdigit() else int(match.group(1)) if match else 1

            # expanded 여부
            expanded = "cl-expanded" in el_class
            # 선택 여부
            aria_selected = await el.get_attribute("aria-selected")
            checked = "cl-selected" in el_class or aria_selected == "true"

            node = {
                "label": label,
                "expanded": expanded,
                "checked": checked,
                "sub_items": []
            }

            while stack and stack[-1][0] >= level:  # subitem 으로 빼기 위해서 넣은 거얌.
                stack.pop()

            if stack:
                stack[-1][1]["sub_items"].append(node)
            else:
                sidebar.append(node)

            stack.append((level, node))
        except Exception as e:
            print(f"[WARN] sidebar item parse failed: {e}")
            continue

    return sidebar


async def scrape_current_page(page: Page):
    """
    현재 활성화된 탭패널(role=tabpanel) 또는 팝업창(.cl-dialog)을 감지해서 상태를 JSON으로 리턴
    """
    current_page = {"title": "", "detail_page": "", "form_fields": []}

    try:
        #팝업창 감지
        dialogs = await page.locator('.cl-dialog').all()
        visible_dialogs = [d for d in dialogs if await d.is_visible()]
        if visible_dialogs:
            print("[INFO] nDRIMS 팝업창(.cl-dialog) 감지")
            dialog = visible_dialogs[0]
            header = dialog.locator('.cl-dialog-header .cl-text').first
            if await header.count() > 0:
                current_page["title"] = (await header.inner_text()).strip()
            else:
                current_page["title"] = "팝업 제목 인식 실패"
            print(f"[INFO] 팝업 제목: {current_page['title']}")
            return current_page

        # 탭패널 감지 (이전 작동 버전의 로직)
        tabpanels = await page.locator('[role="tabpanel"]').all()
        if not tabpanels:
            current_page["title"] = "탭패널 없음"
            return current_page

        # display:none이거나 aria-hidden인 패널 제외, visible한 패널만
        visible_panels = [p for p in tabpanels if await p.is_visible()]
        if not visible_panels:
            current_page["title"] = "활성 탭패널 인식 실패"
            return current_page

        panel = visible_panels[0]  # 첫 번째 활성 탭패널

        # 제목 탐색 로직 (이전 작동 버전)
        try:
            title_el = panel.locator("h1, h2, h3, [role=heading]").first
            if await title_el.count() > 0:
                current_page["title"] = (await title_el.inner_text()).strip()
            else:
                # 없으면 inner_text 첫 줄
                raw_text = (await panel.inner_text()).strip().split("\n")[0]
                # 키워드 필터링: nDRIMS 페이지 제목에 포함될 법한 키워드
                if any(k in raw_text for k in ["조회", "등록", "관리", "신청", "확인", "열람", "출력", "발급"]):
                    current_page["title"] = raw_text
                    print(f"[INFO] 탭패널 첫 줄에서 제목 감지: {raw_text}")
                else:
                    current_page["title"] = "제목 인식 실패"
        except Exception as e:
            print(f"[ERROR] 제목 추출 실패: {e}")
            current_page["title"] = "제목 인식 실패"

        #form 필드 수집 (기존과 동일)
        form_fields = []
        inputs = await page.locator("input, select, textarea").all()
        for el in inputs:
            try:
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                input_type = await el.evaluate("el => el.type || 'text'")
                label = await el.evaluate(
                    """el => el.labels?.[0]?.innerText
                    || el.getAttribute('aria-label')
                    || el.placeholder
                    || ''"""
                )
                value = await el.evaluate("el => el.value || ''")
                fid_attr_id = await el.get_attribute("id")
                fid_attr_name = await el.get_attribute("name")
                fid = fid_attr_id or fid_attr_name or f"{tag}_{len(form_fields)}"
                form_fields.append({
                    "id": fid,
                    "label": (label or "").strip(),
                    "type": tag,
                    "input_type": input_type,
                    "value": (value or "").strip()
                })
            except Exception:
                continue

        current_page["form_fields"] = form_fields or "인식되지 않았다"

        print(json.dumps({"current_page": current_page}, ensure_ascii=False, indent=2))
        return current_page

    except Exception as e:
        print(f"[ERROR] scrape_current_page 오류: {e}")
        current_page["title"] = f"탭패널 감지 중 오류: {e}"
        current_page["form_fields"] = "인식되지 않았다"
        return current_page



async def scrape_current_ui_state(page: Page):
    """NDRIMS 전체 UI 상태를 수집"""
    result = {"url": page.url}

    try:
        result["sidebar"] = await scrape_sidebar(page)
    except Exception as e:
        print(f"[ERROR] sidebar 수집 실패: {e}")
        result["sidebar"] = []

    try:
        result["current_page"] = await scrape_current_page(page)
    except Exception as e:
        print(f"[ERROR] current_page 수집 실패: {e}")
        result["current_page"] = {"title": "(탭 감지 실패)", "form_fields": []}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
