import subprocess
import time
from loguru import logger
from patchright.sync_api import sync_playwright

def ensure_patchright_chromium_installed():
    try:
        install_process = subprocess.run(
            ["patchright", "install", "chromium"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.error("Patchright 命令未找到. 请确定是否安装")
        raise
    except Exception as e:
        logger.error(f"Error ensuring Chromium installation: {e}")
        raise

def scrape_website_sync(url: str):
    logger.info("Scraping website...")
    with sync_playwright() as p:
        browser_args = [
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-web-security",
            "--disable-setuid-sandbox",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--single-process",
            "--window-size=1920x1080",
        ]
        logger.info("Starting browser...")
        browser = p.chromium.launch(
            headless=True,
            args=browser_args,
            slow_mo=50,
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Shanghai",
            permissions=["geolocation"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = context.new_page()
        try:
            logger.info(f"Visiting {url}...")
            response = page.goto(url, wait_until="domcontentloaded")

            if response:
                logger.info(f"http status: {response.status}")

            title = page.title()
            logger.info(f"Page Title: {title}")

            page_content = page.content()
            if "Just a moment" in title or "Checking your browser" in page_content:
                logger.info("Cloudflare challenge detected, waiting for it to complete...")

                try:
                    logger.info(f"Waiting for {url} title to change...")
                    page.wait_for_function("document.title != 'Just a moment...'", timeout=30000)
                    logger.info("Page title has changed")
                except Exception as e:
                    logger.error(f"Timeout waiting for title change: {e}")
                    try:
                        for selector in [
                            "input[type='checkbox']",
                            ".ray-button",
                            "#challenge-stage button",
                            "button:has-text('Verify')",
                            "button:has-text('Continue')",
                        ]:
                            if page.is_visible(selector):
                                logger.info(f"Found possible verification button: {selector}")
                                page.click(selector)
                                time.sleep(5)
                                break
                    except Exception as click_error:
                        logger.error(f"Failed to click verification button: {click_error}")

                logger.info("Extra wait of 10s to ensure challenge completion...")
                time.sleep(10)

            current_title = page.title()
            logger.info(f"Current page title: {current_title}")

            logger.info("Waiting for page content to load...")

            content_loaded = False
            for selector in [
                "h1",
                ".main-content",
                "#content",
                ".video-container",
                "article",
                "main",
            ]:
                try:
                    page.wait_for_selector(selector, timeout=10000)
                    logger.info(f"Found content element: {selector}")
                    content_loaded = True
                    break
                except Exception:
                    continue

            if not content_loaded:
                logger.info("No specific content element found, using fixed delay...")
                time.sleep(10)

            logger.info("Simulating page scroll...")
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
                time.sleep(1)

                page.evaluate("window.scrollBy(0, window.innerHeight / 4)")
                time.sleep(1)

            logger.info("Getting page content...")
            content = page.content()
            logger.info("Page content retrieved successfully.")

            return content
        except Exception as e:
            logger.error(f"Failed to scraping: {e}")
            return None
        finally:
            logger.info("Closing browser...")
            browser.close()