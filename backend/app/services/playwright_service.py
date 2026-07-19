import asyncio
from playwright.async_api import async_playwright

class PlaywrightService:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def navigate(self, url: str):
        if not self.page:
            await self.start()
        await self.page.goto(url)

    async def fill_input(self, selector: str, text: str):
        await self.page.fill(selector, text)

    async def click_element(self, selector: str):
        await self.page.click(selector)
    
    async def capture_screenshot(self, path: str = "screenshot.png"):
        await self.page.screenshot(path=path)

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

playwright_service = PlaywrightService()
