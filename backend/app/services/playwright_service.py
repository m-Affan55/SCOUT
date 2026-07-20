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

    async def navigate(self, url: str):
        # Check if the page is missing OR if the user manually closed the browser window
        if not self.page or self.page.is_closed():
            await self.start()
        
        try:
            await self.page.goto(url)
            await self.restore_window()
        except Exception as e:
            # Fallback if the connection was lost just before navigating
            print(f"[PlaywrightService] Connection error during goto, restarting browser: {e}")
            await self.start()
            await self.page.goto(url)
            await self.restore_window()

    async def fill_input(self, selector: str, text: str):
        await self.page.fill(selector, text)

    async def click_element(self, selector: str):
        await self.page.click(selector)
    
    async def capture_screenshot(self, path: str = "screenshot.png"):
        await self.page.screenshot(path=path)

    async def minimize_window(self):
        """Minimize the browser window so the React app becomes visible to the user."""
        try:
            cdp = await self.context.new_cdp_session(self.page)
            window = await cdp.send("Browser.getWindowForTarget")
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window["windowId"],
                "bounds": {"windowState": "minimized"}
            })
            await cdp.detach()
            print("[PlaywrightService] Browser window minimized.")
        except Exception as e:
            print(f"[PlaywrightService] Could not minimize window: {e}")

    async def restore_window(self):
        """Restore the browser window and bring it to the front so the user can watch."""
        try:
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
