import base64
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
COOKIE_PATH = os.path.join(BASE_DIR, "douyin_cookie.txt")
DEFAULT_SAVE_DIR = os.path.join(BASE_DIR, "downloads")
LOGIN_PAGE_URL = "https://www.douyin.com/user/self"


def cookies_to_header(cookies: list[dict[str, Any]]) -> str:
    parts = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def has_login_cookies(cookies: list[dict[str, Any]]) -> bool:
    names = {cookie.get("name") for cookie in cookies}
    if "sessionid" in names and ("sid_tt" in names or "uid_tt" in names):
        return True

    for cookie in cookies:
        if cookie.get("name") == "passport_auth_status" and cookie.get("value") == "1":
            return True

    return False


def load_config() -> dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}

    return {}


def save_config(data: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_saved_cookie() -> str:
    config = load_config()
    cookie = (config.get("cookie") or "").lstrip("﻿").strip()
    if cookie:
        return cookie

    if os.path.exists(COOKIE_PATH):
        with open(COOKIE_PATH, "r", encoding="utf-8") as file:
            legacy_cookie = file.read().lstrip("﻿").strip()
        if legacy_cookie:
            save_cookie(legacy_cookie, save_dir=config.get("save_dir") or DEFAULT_SAVE_DIR)
            try:
                os.remove(COOKIE_PATH)
            except OSError:
                pass
            return legacy_cookie

    return ""


def save_cookie(cookie: str, save_dir: str | None = None) -> None:
    config = load_config()
    data = {
        "cookie": cookie,
        "save_dir": save_dir or config.get("save_dir") or DEFAULT_SAVE_DIR,
    }
    save_config(data)


def clear_cookie() -> None:
    if os.path.exists(CONFIG_PATH):
        save_config({"save_dir": DEFAULT_SAVE_DIR})


@dataclass
class LoginSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "initializing"
    message: str = "正在初始化登录会话"
    qr_image: str | None = None
    cookie: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._qr_ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def wait_for_qr(self, timeout: float = 30) -> bool:
        return self._qr_ready.wait(timeout)

    def snapshot(self, include_qr: bool = False) -> dict[str, Any]:
        with self._lock:
            data = {
                "session_id": self.session_id,
                "status": self.status,
                "message": self.message,
                "has_cookie": bool(self.cookie),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
            if self.error:
                data["error"] = self.error
            if include_qr and self.qr_image:
                data["qr_image"] = self.qr_image
            return data

    def _set_state(
        self,
        status: str,
        message: str,
        *,
        qr_image: str | None = None,
        cookie: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self.status = status
            self.message = message
            self.updated_at = time.time()
            if qr_image is not None:
                self.qr_image = qr_image
            if cookie is not None:
                self.cookie = cookie
            if error is not None:
                self.error = error

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self._set_state(
                "failed",
                "缺少 playwright，请先安装依赖并执行 playwright install chromium",
                error="playwright_not_available",
            )
            self._qr_ready.set()
            return

        browser = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=False)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
                page = context.new_page()

                self._set_state("initializing", "打开抖音登录页")
                page.goto(LOGIN_PAGE_URL, wait_until="domcontentloaded", timeout=30000)

                self._switch_to_qr_login(page)

                qr_element = self._find_qr_element(page)
                if qr_element is None:
                    self._set_state("failed", "未找到二维码，请确认网络可访问抖音", error="qr_not_found")
                    self._qr_ready.set()
                    return

                qr_src = qr_element.get_attribute("src") or ""
                if qr_src.startswith("data:image"):
                    qr_image = qr_src
                else:
                    img_bytes = qr_element.screenshot()
                    qr_image = "data:image/png;base64," + base64.b64encode(img_bytes).decode("ascii")
                self._set_state("waiting", "等待扫码登录", qr_image=qr_image)
                self._qr_ready.set()

                login_request_detected = False
                navigation_occurred = False

                def on_request(request):
                    nonlocal login_request_detected
                    if any(
                        key in request.url
                        for key in (
                            "/aweme/v1/web/user/",
                            "/aweme/v1/web/im/user/info/",
                        )
                    ):
                        login_request_detected = True

                def on_navigation(frame):
                    nonlocal navigation_occurred
                    if frame == page.main_frame:
                        navigation_occurred = True

                page.on("request", on_request)
                page.on("framenavigated", on_navigation)

                original_url = page.url
                last_cookie_count = 0
                for index in range(300):
                    cookies = context.cookies()
                    cookie_count = len(cookies)
                    cookie_increased = cookie_count > last_cookie_count
                    last_cookie_count = cookie_count

                    if has_login_cookies(cookies):
                        self._finish_login(context, browser)
                        return

                    qr_gone = self._is_qr_gone(page, qr_element)
                    current_url = page.url
                    url_changed = (
                        current_url != original_url
                        and "login" not in current_url.lower()
                        and "passport" not in current_url.lower()
                        and "auth" not in current_url.lower()
                    )
                    is_homepage = (
                        "douyin.com" in current_url
                        and current_url != original_url
                        and "passport" not in current_url.lower()
                        and "login" not in current_url.lower()
                    )
                    login_text = self._has_login_success_text(page)

                    if (
                        is_homepage
                        or (qr_gone and url_changed)
                        or login_text
                        or login_request_detected
                        or (qr_gone and cookie_increased and cookie_count >= 10)
                        or (qr_gone and navigation_occurred and cookie_increased)
                    ):
                        page.wait_for_timeout(4000)
                        cookies = context.cookies()
                        if has_login_cookies(cookies):
                            self._finish_login(context, browser)
                            return

                    if index % 10 == 0:
                        self._set_state("waiting", f"等待扫码登录... ({index // 10 + 1}/30)")
                    page.wait_for_timeout(1000)

                self._set_state("expired", "登录超时，请重新创建扫码会话", error="login_timeout")
        except Exception as exc:
            self._set_state("failed", f"获取登录状态失败: {exc}", error=str(exc))
            self._qr_ready.set()
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    def _finish_login(self, context, browser) -> None:
        cookies = context.cookies()
        cookie = cookies_to_header(cookies)
        save_cookie(cookie)
        self._set_state("logged_in", "登录成功，Cookie 已保存到本机", cookie=cookie)
        try:
            browser.close()
        except Exception:
            pass

    @staticmethod
    def _safe_page_content(page) -> str:
        try:
            return page.content()
        except Exception:
            return ""

    @staticmethod
    def _switch_to_qr_login(page) -> None:
        try:
            login_btn = page.query_selector("#NPj2H93w > button")
            if login_btn:
                login_btn.click()
                page.wait_for_timeout(2000)
            for text in ("扫码登录", "二维码登录", "二维码", "扫码"):
                button = page.query_selector(f"text={text}")
                if button:
                    button.click()
                    page.wait_for_timeout(1000)
                    return
        except Exception:
            return

    @staticmethod
    def _find_qr_element(page):
        selectors = [
            "#animate_qrcode_container > div.XI37I0dP > img",
            "#animate_qrcode_container > div.qrcode-vz0gH7 > img",
            'img[role="img"][aria-label="二维码"]',
            "img[aria-label*='二维码']",
            "img[src^='data:image/png;base64']",
            "img[src*='qrcode']",
            "img[src*='qr']",
            "img[alt*='二维码']",
            "[class*=qrcode] img",
        ]
        for _ in range(40):
            for selector in selectors:
                element = LoginSession._query_visible_qr(page, selector)
                if element:
                    return element
            page.wait_for_timeout(500)

        for frame in page.frames:
            for selector in selectors:
                element = LoginSession._query_visible_qr(frame, selector)
                if element:
                    return element
        return None

    @staticmethod
    def _query_visible_qr(page_or_frame, selector: str):
        try:
            element = page_or_frame.query_selector(selector)
            if not element:
                return None
            box = element.bounding_box()
            if box and box["width"] >= 120 and box["height"] >= 120:
                return element
        except Exception:
            return None
        return None

    @staticmethod
    def _is_qr_gone(page, element) -> bool:
        try:
            if element and not element.is_visible():
                return True
            if element:
                element.bounding_box()
        except Exception:
            return True

        try:
            for selector in ('img[role="img"][aria-label="二维码"]', "img[aria-label*='二维码']", "img[src*='qrcode']", "img[src*='qr']"):
                if page.query_selector(selector):
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def _has_login_success_text(page) -> bool:
        content = LoginSession._safe_page_content(page)
        return any(
            text in content
            for text in (
                "扫码成功",
                "已登录",
                "登录成功",
                "登录完成",
                "确认登录",
                "登录验证成功",
                "验证通过",
                "授权成功",
            )
        )


class LoginManager:
    def __init__(self) -> None:
        self._sessions: dict[str, LoginSession] = {}
        self._lock = threading.RLock()

    def create_session(self, qr_timeout: float = 30) -> LoginSession:
        session = LoginSession()
        with self._lock:
            self._sessions[session.session_id] = session
        session.start()
        session.wait_for_qr(qr_timeout)
        return session

    def get_session(self, session_id: str) -> LoginSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_cookie(self, session_id: str | None = None) -> str:
        if session_id:
            session = self.get_session(session_id)
            if session and session.cookie:
                return session.cookie
        return load_saved_cookie()
