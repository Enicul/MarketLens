import asyncio
import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import quote

from playwright.async_api import Page, async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Tweet:
    username: str
    user_id: str
    content: str
    timestamp: str
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    is_retweet: bool = False
    is_reply: bool = False

    def __post_init__(self):
        self.content = self.content.strip()

    @property
    def engagement_score(self) -> int:
        return self.likes + self.retweets * 2 + self.replies

    @property
    def unique_key(self) -> Tuple[str, str, str]:
        return (self.username, self.timestamp, self.content[:100])


@dataclass
class ScraperConfig:
    headless: bool = True
    max_tweets: int = 50
    parallel_pages: int = 4
    max_scroll_attempts: int = 20
    min_likes: int = 0
    min_retweets: int = 0
    min_replies: int = 0
    min_text_length: int = 10
    disable_media: bool = True
    exclude_retweets: bool = False
    exclude_replies: bool = False
    delay_range: Tuple[int, int] = (1, 3)

    # File paths
    cookies_path: str = "X_cookies.json"
    storage_state_path: Optional[str] = "state.json"  # persist full session by default

    # Search parameters
    finance_keywords: List[str] = None
    language: str = "en"

    def __post_init__(self):
        if self.finance_keywords is None:
            self.finance_keywords = ["stock", "trading", "bullish", "bearish", "buy", "sell"]


class TwitterScraper:
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        await self._start_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cleanup()

    async def _start_browser(self):
        """Initialize browser and context"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                "--no-sandbox",
                '--disable-blink-features=AutomationControlled',
                "--disable-web-security",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Load storage state or cookies
        context_kwargs = {}
        if self.config.storage_state_path and Path(self.config.storage_state_path).exists():
            context_kwargs["storage_state"] = self.config.storage_state_path

        self._context = await self._browser.new_context(**context_kwargs)

        # Sane defaults for SPA like X
        self._context.set_default_timeout(10_000)
        self._context.set_default_navigation_timeout(20_000)

        # Lighter pages = fewer timeouts
        await self._context.route(
            "**/*",
            lambda route, req: route.abort()
            if req.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )

        await self._context.set_extra_http_headers({"User-Agent": self.USER_AGENT})

        if not context_kwargs:  # Only load raw cookies if no storage state
            await self._load_cookies()

        await self._ensure_login()

    async def _load_cookies(self):
        """Load cookies from JSON file"""
        cookie_file = Path(self.config.cookies_path)
        if not cookie_file.exists():
            return

        try:
            with cookie_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            cookies_data = data if isinstance(data, list) else data.get("primary", [])
            if not cookies_data:
                return

            cookies = [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".x.com"),
                    "path": c.get("path", "/"),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", True),
                    "sameSite": c.get("sameSite", "Lax"),
                }
                for c in cookies_data
                if c.get("name") and c.get("value")
            ]

            if cookies:
                await self._context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies")

        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")

    async def _ensure_login(self):

        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)

            if await self._is_logged_in(page):
                logger.info("Already logged in")
                # persist state for future runs
                if self.config.storage_state_path:
                    await self._context.storage_state(path=self.config.storage_state_path)
                return

            if self.config.headless:
                raise RuntimeError("Not logged in. Run in non-headless mode first.")

            logger.warning("Please log in manually")
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=60_000)

            # Wait for login completion
            for _ in range(150):  # up to ~5 minutes
                if await self._is_logged_in(page):
                    if self.config.storage_state_path:
                        await self._context.storage_state(path=self.config.storage_state_path)
                        logger.info(f"Login state saved to {self.config.storage_state_path}")
                    logger.info("Login completed")
                    return
                await asyncio.sleep(2)

            raise TimeoutError("Login timeout")
        finally:
            await page.close()

    async def _is_logged_in(self, page: Page) -> bool:
        """Check if user is logged in"""
        try:
            cookies = await page.context.cookies()
            if any(c.get("name") == "auth_token" for c in cookies):
                return True

            selectors = [
                '[data-testid="SideNav_AccountSwitcher_Button"]',
                '[data-testid="AppTabBar_Home_Link"]',
                'a[href="/compose/tweet"]',
            ]
            for sel in selectors:
                if await page.locator(sel).first.is_visible():
                    return True
            return False
        except Exception:
            return False

    def _build_search_query(self, symbol: str) -> str:
        """Build search query and URL-encode it safely"""
        base = f"(${symbol} OR {symbol})"
        fin = f" ({' OR '.join(self.config.finance_keywords[:6])})" if self.config.finance_keywords else ""
        lang = f" lang:{self.config.language}" if self.config.language else ""
        # keep parentheses/colon; encode spaces
        return quote(base + fin + lang, safe=":() ")

    async def _navigate_and_wait(self, page: Page, url: str):
        """Navigate without networkidle and wait for tweet content"""
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # interstitial / error guards
        if await page.locator("text=Rate limit exceeded").first.is_visible():
            raise RuntimeError("X rate limited this session")
        if await page.locator("text=Something went wrong").first.is_visible():
            await page.reload(wait_until="domcontentloaded")

        # wait for actual tweets (selector-based)
        try:
            await page.wait_for_selector('article [data-testid="tweetText"]', timeout=15_000)
        except Exception:
            await page.wait_for_selector('main[role="main"] article', timeout=15_000)
            

#    async def scrape_stock_tweets(self, symbol: str) -> List[Tweet]:
#        """Main scraping method (sequential pages by default)"""
#        query = self._build_search_query(symbol)
#        collected_tweets: List[Tweet] = []
#        seen_keys: Set[Tuple[str, str, str]] = set()
#
#        # Create worker pages
#        pages = []
#        try:
#            for i in range(self.config.parallel_pages):
#                page = await self._context.new_page()
#                if self.config.disable_media:
#                    # extra safety at page level (context-level already blocks)
#                    await page.route(
#                        "**/*.{png,jpg,jpeg,gif,webp,mp4,webm}",
#                        lambda route: route.abort(),
#                    )
#                await page.set_extra_http_headers({"User-Agent": self.USER_AGENT})
#                pages.append(page)
#
#            # Run sequentially for stability on X
#            for i, page in enumerate(pages):
#                await self._scrape_page(page, i, query, seen_keys, collected_tweets)
#                await asyncio.sleep(0.8)
#
#        finally:
#            for page in pages:
#                try:
#                    await page.close()
#                except Exception:
#                    pass
#
#        # Filter and sort results
#        filtered_tweets = self._filter_tweets(collected_tweets)
#        sorted_tweets = sorted(filtered_tweets, key=lambda t: t.engagement_score, reverse=True)
#
#        logger.info(f"Scraped {len(sorted_tweets)} tweets for {symbol}")
#        return sorted_tweets[:self.config.max_tweets]


    async def scrape_stock_tweets(self, symbol: str) -> List[Tweet]:
        query = self._build_search_query(symbol)
        collected_tweets: List[Tweet] = []
        seen_keys: Set[Tuple[str, str, str]] = set()

        pages = []
        try:
            for _ in range(self.config.parallel_pages):
                page = await self._context.new_page()
                if self.config.disable_media:
                    await page.route(
                        "**/*.{png,jpg,jpeg,gif,webp,mp4,webm}",
                        lambda route: route.abort(),
                    )
                await page.set_extra_http_headers({"User-Agent": self.USER_AGENT})
                pages.append(page)

            async def worker(i: int, page: Page):
                # tiny jitter so all 4 don't hit at the exact same millisecond
                await asyncio.sleep(0.3 * i + random.uniform(0, 0.3))
                await self._scrape_page(page, i, query, seen_keys, collected_tweets)

            tasks = [asyncio.create_task(worker(i, p)) for i, p in enumerate(pages)]
            await asyncio.gather(*tasks, return_exceptions=True)

        finally:
            for page in pages:
                try:
                    await page.close()
                except:
                    pass

        filtered = self._filter_tweets(collected_tweets)
        return sorted(filtered, key=lambda t: t.engagement_score, reverse=True)[:self.config.max_tweets]

    async def _scrape_page(
        self,
        page: Page,
        page_idx: int,
        query: str,
        seen_keys: Set,
        collected_tweets: List[Tweet],
    ):
        """Scrape tweets from a single page"""
        try:
            # Alternate between top and latest
            search_type = "&f=live" if page_idx >= self.config.parallel_pages // 2 else ""
            url = f"https://x.com/search?q={query}&src=typed_query{search_type}"

            await self._navigate_and_wait(page, url)
            await page.wait_for_timeout(300)

            # Pre-scroll to different starting positions
            for _ in range(page_idx * 3):
                await page.mouse.wheel(0, 2000)
                await page.wait_for_timeout(200)

            tweet_selector = 'article:has([data-testid="tweetText"])'
            await page.wait_for_selector(tweet_selector, timeout=20_000)

            page_tweets = 0
            for scroll_attempt in range(self.config.max_scroll_attempts):
                if len(collected_tweets) >= self.config.max_tweets:
                    break

                elements = await page.query_selector_all(tweet_selector)
                if not elements:
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(400)
                    continue

                # Extract tweets in batch
                tweets = await self._extract_tweets_batch(elements)
                new_tweets = 0

                for tweet in tweets:
                    if not tweet or not self._meets_filters(tweet):
                        continue

                    if tweet.unique_key not in seen_keys:
                        seen_keys.add(tweet.unique_key)
                        collected_tweets.append(tweet)
                        new_tweets += 1
                        page_tweets += 1

                        if len(collected_tweets) >= self.config.max_tweets:
                            break

                if new_tweets == 0 and scroll_attempt > 5:
                    break

                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(400)

            logger.info(f"Page {page_idx} collected {page_tweets} tweets")

        except Exception as e:
            logger.error(f"Page {page_idx} scraping failed: {e}")

    async def _extract_tweets_batch(self, elements) -> List[Optional[Tweet]]:
        """Extract tweet data from elements in parallel"""
        if not elements:
            return []
        tasks = [self._extract_tweet_data(el) for el in elements]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, Tweet)]

    async def _extract_tweet_data(self, element) -> Optional[Tweet]:
        """Extract data from a single tweet element"""
        try:
            # User info
            user_link = await element.query_selector('[data-testid="User-Name"] a')
            username = (await user_link.inner_text()).strip() if user_link else "unknown"
            user_id = ""
            if user_link:
                href = await user_link.get_attribute("href")
                user_id = href.lstrip("/") if href and href.startswith("/") else href or ""

            # Content
            content_el = await element.query_selector('[data-testid="tweetText"]')
            content = (await content_el.inner_text()).strip() if content_el else ""

            # Timestamp
            time_el = await element.query_selector("time")
            timestamp = await time_el.get_attribute("datetime") if time_el else ""

            # Metrics
            likes = await self._extract_metric(element, "like")
            retweets = await self._extract_metric(element, ["retweet", "repost"])
            replies = await self._extract_metric(element, "reply")

            # Flags
            is_retweet = bool(
                await element.query_selector('[data-testid="socialContext"]:has-text("reposted")')
            )
            is_reply = bool(
                await element.query_selector('[data-testid="inReplyTo"], div:has-text("Replying to")')
            )

            return Tweet(
                username=username,
                user_id=user_id,
                content=content,
                timestamp=timestamp,
                likes=likes,
                retweets=retweets,
                replies=replies,
                is_retweet=is_retweet,
                is_reply=is_reply,
            )

        except Exception as e:
            logger.debug(f"Failed to extract tweet: {e}")
            return None

    async def _extract_metric(self, element, testids) -> int:
        """Extract engagement metrics"""
        if isinstance(testids, str):
            testids = [testids]

        try:
            for testid in testids:
                btn = await element.query_selector(f'[data-testid="{testid}"]')
                if not btn:
                    continue

                # Try aria-label first
                label = await btn.get_attribute("aria-label")
                if label:
                    match = re.search(r"(\d+(?:[,.]\d+)*)\s*[KMB]?", label, re.IGNORECASE)
                    if match:
                        return self._parse_number(match.group(1))

                # Try inner text
                text = await btn.inner_text()
                if text:
                    match = re.search(r"(\d+(?:[,.]\d+)*)\s*[KMB]?", text, re.IGNORECASE)
                    if match:
                        return self._parse_number(match.group(1))

            return 0

        except Exception:
            return 0

    def _parse_number(self, text: str) -> int:
        """Parse number with K/M/B suffixes"""
        if not text:
            return 0

        text = text.replace(",", "").upper()
        multipliers = {"K": 1000, "M": 1_000_000, "B": 1_000_000_000}

        for suffix, multiplier in multipliers.items():
            if suffix in text:
                try:
                    return int(float(text.replace(suffix, "")) * multiplier)
                except (ValueError, OverflowError):
                    return 0

        try:
            return int(float(text))
        except (ValueError, OverflowError):
            return 0

    def _meets_filters(self, tweet: Tweet) -> bool:
        """Check if tweet meets filtering criteria"""
        if self.config.exclude_retweets and tweet.is_retweet:
            return False
        if self.config.exclude_replies and tweet.is_reply:
            return False

        return (
            len(tweet.content) >= self.config.min_text_length
            and tweet.likes >= self.config.min_likes
            and tweet.retweets >= self.config.min_retweets
            and tweet.replies >= self.config.min_replies
        )

    def _filter_tweets(self, tweets: List[Tweet]) -> List[Tweet]:
        """Apply final filtering"""
        return [t for t in tweets if self._meets_filters(t)]

    async def save_tweets(self, tweets: List[Tweet], filename: str):
        """Save tweets to JSON file"""
        data = [asdict(tweet) for tweet in tweets]

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(tweets)} tweets to {filename}")

    async def _cleanup(self):
        """Clean up resources"""
        # close context and browser, then stop playwright
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass


async def main():
    """Example usage"""
    config = ScraperConfig(
        headless=False,
        storage_state_path="state.json",
        max_tweets=30,
        parallel_pages=4,
        min_likes=5,
    )

    stocks = ["TSLA"]

    async with TwitterScraper(config) as scraper:
        for stock in stocks:
            logger.info(f"Scraping tweets for {stock}")
            tweets = await scraper.scrape_stock_tweets(stock)

            if tweets:
                filename = f"{stock}_tweets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                await scraper.save_tweets(tweets, filename)

                total_engagement = sum(t.engagement_score for t in tweets)
                logger.info(f"{stock}: {len(tweets)} tweets, {total_engagement} total engagement")
            else:
                logger.warning(f"No tweets found for {stock}")


if __name__ == "__main__":
    asyncio.run(main())
