import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright

class PlaywrightService:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._previous_pages = []  # Track previous pages for popup handling

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
        
        # Stealth: launch with flags that reduce bot-detection fingerprinting
        self.browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ],
        )
        
        # Stealth: create context with realistic browser properties
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
        )
        
        # Expose the submit function to the browser context
        await self.context.expose_binding("scoutSubmitInput", self._handle_overlay_submit)
        
        self.page = await self.context.new_page()
        
        # Stealth: remove navigator.webdriver flag that WAFs use to detect automation
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
        """)
        
        # Register listener for new pages/popups
        self.context.on("page", self._handle_new_page)
        
        try:
            await self.page.bring_to_front()
        except Exception:
            pass

    async def _handle_new_page(self, page):
        """Handle new pages/tabs opened by the browser."""
        try:
            # Fix 3: Add timeout and try/except for hanging popups
            await page.wait_for_load_state(timeout=5000)
            
            # Same-origin check
            if self.page and not self.page.is_closed():
                current_host = urlparse(self.page.url).netloc
                new_host = urlparse(page.url).netloc
                
                # Check root domains (e.g. nu.edu.pk)
                if current_host and new_host:
                    current_root = '.'.join(current_host.split('.')[-2:])
                    new_root = '.'.join(new_host.split('.')[-2:])
                    if current_root != new_root:
                        print(f"[PlaywrightService] Ignoring irrelevant popup from {new_host}")
                        await page.close()
                        return
            
            # Fix 3: Handle self-closing popups
            page.on("close", self._handle_popup_close)
            
            # Keep reference to previous page
            if self.page:
                self._previous_pages.append(self.page)
            
            # Set new page as current
            self.page = page
            
            # Close old pages if we exceed the cap (keep last 3)
            while len(self._previous_pages) > 3:
                old_page = self._previous_pages.pop(0)
                try:
                    if not old_page.is_closed():
                        await old_page.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[PlaywrightService] Popup failed to load or timed out: {e}")
            try:
                if not page.is_closed():
                    await page.close()
            except:
                pass

    async def _handle_popup_close(self, page):
        """Revert to previous page if the current popup closes."""
        if self.page == page:
            if self._previous_pages:
                self.page = self._previous_pages.pop()
                print(f"[PlaywrightService] Popup closed, reverting to: {self.page.url}")
            else:
                self.page = None

    async def _handle_overlay_submit(self, source, thread_id, value):
        from app.registry import workflow_manager
        workflow_manager.resolve_input_future(thread_id, value)

    async def show_input_overlay(self, message: str, input_type: str, thread_id: str):
        if not self.page or self.page.is_closed():
            return
            
        await self.restore_window()
        
        # Escape single quotes and backticks in message
        safe_message = message.replace('`', '\\`').replace('$', '\\$')
        
        overlay_html = f"""
            (() => {{
                document.getElementById('scout-overlay')?.remove();
                
                const overlay = document.createElement('div');
                overlay.id = 'scout-overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '20px';
                overlay.style.right = '20px';
                overlay.style.zIndex = '2147483647';
                overlay.style.backgroundColor = 'rgba(15, 23, 42, 0.95)';
                overlay.style.color = 'white';
                overlay.style.padding = '20px';
                overlay.style.borderRadius = '8px';
                overlay.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.5)';
                overlay.style.fontFamily = 'system-ui, sans-serif';
                overlay.style.maxWidth = '350px';
                overlay.style.border = '1px solid #334155';
                
                let inputHtml = '';
                if ('{input_type}' !== 'continue_only') {{
                    inputHtml = '<input type="text" id="scout-input" style="width: 100%; padding: 8px; margin: 10px 0; border-radius: 4px; border: 1px solid #475569; background: #1e293b; color: white; box-sizing: border-box;" />';
                }}
                
                overlay.innerHTML = `
                    <div style="font-weight: 600; margin-bottom: 8px; color: #38bdf8;">Scout Action Required</div>
                    <div style="font-size: 14px; margin-bottom: 12px; line-height: 1.4;">` + `{safe_message}` + `</div>
                    ${{inputHtml}}
                    <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 15px;">
                        <button id="scout-submit" style="background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: 500;">Submit</button>
                    </div>
                `;
                
                document.body.appendChild(overlay);
                
                if ('{input_type}' !== 'continue_only') {{
                    const input = document.getElementById('scout-input');
                    if(input) input.focus();
                }}
                
                document.getElementById('scout-submit').onclick = () => {{
                    const inputEl = document.getElementById('scout-input');
                    const val = inputEl ? inputEl.value : 'continue';
                    // We must use the exposed binding
                    window.scoutSubmitInput('{thread_id}', val);
                }};
            }})();
        """
        try:
            await self.page.evaluate(overlay_html)
        except Exception as e:
            print(f"[PlaywrightService] Error showing overlay: {{e}}")

    async def hide_input_overlay(self):
        if not self.page or self.page.is_closed():
            return
        try:
            await self.page.evaluate("document.getElementById('scout-overlay')?.remove()")
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
        try:
            if iframe_index is not None:
                await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).click(timeout=5000)
            else:
                await self.page.click(selector, timeout=5000)
        except Exception as e:
            print(f"[PlaywrightService] Standard click failed, attempting forced click: {e}")
            try:
                if iframe_index is not None:
                    await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).click(timeout=2000, force=True)
                else:
                    await self.page.click(selector, timeout=2000, force=True)
            except Exception as e2:
                print(f"[PlaywrightService] Forced click failed, attempting JS click: {e2}")
                try:
                    if iframe_index is not None:
                        await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).evaluate("el => el.click()")
                    else:
                        await self.page.locator(selector).first.evaluate("el => el.click()")
                except Exception as e3:
                    print(f"[PlaywrightService] All click attempts failed: {e3}")
                    raise

    async def select_option(self, selector: str, label: str, iframe_index: int = None):
        if iframe_index is not None:
            await self.page.locator('iframe').nth(iframe_index).content_frame.locator(selector).select_option(label=label, timeout=3000)
        else:
            await self.page.select_option(selector, label=label, timeout=3000)

    async def minimize_window(self):
        """Minimize the browser window so the React app becomes visible to the user."""
        if not self.context or not self.page:
            return

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
            print(f"[PlaywrightService] CDP minimize failed: {e}")

    async def yield_to_user(self):
        """No-op: keep browser visible for now during verification."""
        pass

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
