import asyncio
from playwright.async_api import async_playwright

async def execute_real_tiktok_warmup(keywords_str: str):
    """Реально запускает браузер Playwright для взаимодействия с TikTok."""
    keywords = [kw.strip() for kw in keywords_str.split(",")]
    logs = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            for kw in keywords:
                logs.append(f"🔍 Поиск в TikTok по ключевой фразе: `{kw}`")
                await page.goto(f"https://www.tiktok.com/search?q={kw.replace(' ', '%20')}", timeout=60000)
                await page.wait_for_timeout(5000)
                
                videos = await page.locator('div[data-e2e="search-card-video"]').all()
                if videos:
                    await videos[0].click()
                    logs.append(f"▶️ Открыто первое видео по запросу `{kw}`")
                    await page.wait_for_timeout(4000)
                    
                    try:
                        like_btn = page.locator('button[data-e2e="browse-like-icon"]').first()
                        if await like_btn.count() > 0:
                            await like_btn.click()
                            logs.append(f"❤️ Поставлен лайк")
                    except Exception:
                        pass
                else:
                    logs.append(f"⚠️ Видео по запросу `{kw}` не найдены.")
                await asyncio.sleep(2)
        except Exception as e:
            logs.append(f"❌ Ошибка Playwright: {str(e)}")
        finally:
            await browser.close()
            
    return True, "\n".join(logs)
