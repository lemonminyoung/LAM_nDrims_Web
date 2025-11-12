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

        # 기존 탭패널 감지
        tabpanels = await page.locator('[role="tabpanel"]').all()
        visible_panels = [p for p in tabpanels if await p.is_visible()]
        # role=tabpanel이 없는 경우 → cl-form-placeholder 사용
        if not visible_panels:
            placeholders = await page.locator("div.cl-form-placeholder").all()
            visible_panels = [p for p in placeholders if await p.is_visible()]
            if visible_panels:
                print("[INFO] 일반 탭패널 미발견 → cl-form-placeholder 감지")
            else:
                current_page["title"] = "활성 탭패널/placeholder 인식 실패"
                return current_page

        panel = visible_panels[0]

        # 제목 탐색 로직 강화
        title_el = panel.locator("h1, h2, h3, [role=heading]").first
        if await title_el.count() > 0:
            current_page["title"] = (await title_el.inner_text()).strip()
        else:
            # 학적부 구조: div.cl-text 안에 제목 존재
            cl_text_el = page.locator("div.cl-text").first
            if await cl_text_el.count() > 0:
                text_val = (await cl_text_el.inner_text()).strip()
                # 너무 일반적인 div.cl-text 방지: 짧고 의미 있는 텍스트만 제목으로 인정
                if len(text_val) < 30 and all(k not in text_val for k in ["닫기", "조회", "검색"]):
                    current_page["title"] = text_val
                    print(f"[INFO] cl-text 제목 감지: {text_val}")
                else:
                    current_page["title"] = "제목 인식 실패"
            else:
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
