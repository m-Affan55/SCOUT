import asyncio
from playwright.async_api import async_playwright

class PlaywrightService:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

    async def start(self):
        # If there's an existing instance, try to close it first to avoid memory leaks
        try:
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        try:
            await self.page.bring_to_front()
        except Exception:
            pass

    async def navigate(self, url: str, bring_to_front: bool = False):
        # Check if the page is missing OR if the user manually closed the browser window
        if not self.page or self.page.is_closed():
            await self.start()
        
        try:
            if bring_to_front:
                await self.restore_window()
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            # Fallback if the connection was lost just before navigating
            print(f"[PlaywrightService] Connection error during goto, restarting browser: {e}")
            await self.start()
            if bring_to_front:
                await self.restore_window()
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

    async def fill_input(self, selector: str, text: str, iframe_index: int = None):
        if iframe_index is not None:
            await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).fill(text, timeout=3000)
        else:
            await self.page.fill(selector, text, timeout=3000)

    async def check_element(self, selector: str, iframe_index: int = None):
        if iframe_index is not None:
            await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).check(timeout=3000)
        else:
            await self.page.check(selector, timeout=3000)

    async def click_element(self, selector: str, iframe_index: int = None):
        if iframe_index is not None:
            await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).click(timeout=5000)
        else:
            await self.page.click(selector, timeout=5000)

    async def select_option(self, selector: str, label: str, iframe_index: int = None):
        if iframe_index is not None:
            await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).select_option(label=label, timeout=3000)
        else:
            await self.page.select_option(selector, label=label, timeout=3000)

    async def minimize_window(self):
        """Minimize the browser window so the React app becomes visible to the user."""
        if not self.context or not self.page:
            return

        minimized = False
        try:
            cdp = await self.context.new_cdp_session(self.page)
            window = await cdp.send("Browser.getWindowForTarget")
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window["windowId"],
                "bounds": {"windowState": "minimized"}
            })
            await cdp.detach()
            minimized = True
            print("[PlaywrightService] Browser window minimized.")
        except Exception as e:
            print(f"[PlaywrightService] CDP minimize failed: {e}")

        if not minimized:
            # Fallback: move the window off-screen when CDP minimize is unavailable
            try:
                cdp = await self.context.new_cdp_session(self.page)
                window = await cdp.send("Browser.getWindowForTarget")
                await cdp.send("Browser.setWindowBounds", {
                    "windowId": window["windowId"],
                    "bounds": {
                        "left": -32000,
                        "top": -32000,
                        "width": 800,
                        "height": 600,
                        "windowState": "normal",
                    }
                })
                await cdp.detach()
                print("[PlaywrightService] Browser moved off-screen as minimize fallback.")
            except Exception as e:
                print(f"[PlaywrightService] Could not hide browser window: {e}")

    async def yield_to_user(self):
        """Hide the browser and give the user a moment to switch back to the Scout app."""
        await self.minimize_window()
        await asyncio.sleep(0.3)

    async def restore_window(self):
        """Restore the browser window and bring it to the front so the user can watch."""
        try:
            if not self.context or not self.page:
                return
            cdp = await self.context.new_cdp_session(self.page)
            window = await cdp.send("Browser.getWindowForTarget")
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window["windowId"],
                "bounds": {"windowState": "normal"}
            })
            await cdp.detach()
            await self.page.bring_to_front()
            print("[PlaywrightService] Browser window restored.")
        except Exception as e:
            print(f"[PlaywrightService] Could not restore window: {e}")

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            print(f"[PlaywrightService] Error closing browser: {e}")
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self._playwright = None

playwright_service = PlaywrightService()
