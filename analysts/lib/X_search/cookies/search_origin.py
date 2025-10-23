import asyncio
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigManager:
    """Configuration manager that centralizes Config access."""
    _config = None
    
    @classmethod
    def _load_config(cls):
        if cls._config is None:
            try:
                try:
                    from .config import Config
                except ImportError:
                    from config import Config
                cls._config = Config
            except ImportError:
                cls._config = type("Config", (), {})()
    
    @classmethod
    def get(cls, key: str, default=None):
        cls._load_config()
        return getattr(cls._config, key, default)

class TwitterStockScraper:
    def __init__(self, headless: bool = None, delay_range: tuple = None):
        """Twitter stock information crawler"""
        self.headless = headless if headless is not None else ConfigManager.get('HEADLESS', True)
        self.delay_range = delay_range if delay_range is not None else ConfigManager.get('DELAY_RANGE', (1, 3))
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None
        self._playwright = None
        self.last_page_counts: Optional[List[int]] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_browser()
        
    async def start_browser(self):
        """Start browser"""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled', 
                  '--disable-web-security', '--disable-features=VizDisplayCompositor']
        )
        
        # Create context, prioritize storage_state
        storage_state_path = ConfigManager.get('STORAGE_STATE_PATH')
        if storage_state_path and Path(storage_state_path).exists():
            self.context = await self.browser.new_context(storage_state=storage_state_path)
        else:
            self.context = await self.browser.new_context()
            await self._load_cookies()

        self.page = await self.context.new_page()
        await self.page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Decide whether to disable image and video loading based on config
        if ConfigManager.get('DISABLE_MEDIA', True):
            await self.page.route("**/*.{png,jpg,jpeg,gif,webp,svg,bmp,ico,mp4,webm,ogg,avi,mov,wmv,flv,3gp}", lambda route: route.abort())
        
        await self.ensure_logged_in()
    
    async def _load_cookies(self):
        """Load cookie file"""
        cookies_path = ConfigManager.get('COOKIES_JSON_PATH', 'X_cookies.json')
        cookie_file = Path(__file__).parent / cookies_path if not Path(cookies_path).exists() else Path(cookies_path)
        
        if not cookie_file.exists():
            return
            
        try:
            with cookie_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            cookie_sets = []
            if isinstance(data, dict):
                cookie_sets = data.get('primary') or data.get('backup') or []
            
            if not cookie_sets:
                return
                
            cookies = []
            for c in cookie_sets:
                if not (c.get('name') and c.get('value')):
                    continue
                cookies.append({
                    'name': c.get('name'),
                    'value': c.get('value'),
                    'domain': c.get('domain', '.x.com'),
                    'path': c.get('path', '/'),
                    'httpOnly': bool(c.get('httpOnly')),
                    'secure': bool(c.get('secure', True)),
                    'sameSite': c.get('sameSite', 'Lax'),
                })
            
            if cookies:
                await self.context.add_cookies(cookies)
                logger.info(f'Loaded {len(cookies)} cookies')
        except Exception as e:
            logger.warning(f'Loading Cookies failed: {e}')
        
    async def close_browser(self):
        """Close browser"""
        for obj, attr in [(self.page, 'page'), (self.context, 'context'), 
                         (self.browser, 'browser'), (self._playwright, '_playwright')]:
            if obj:
                try:
                    await obj.close() if attr != '_playwright' else await obj.stop()
                except Exception:
                    pass
                finally:
                    setattr(self, attr, None)
            
    async def is_logged_in(self) -> bool:
        """Check if logged in"""
        try:
            # Check auth_token cookie
            cookies = await self.page.context.cookies()
            if any(c.get('name') == 'auth_token' for c in cookies):
                return True
            
            # Check page login element
            selectors = ['[data-testid="SideNav_AccountSwitcher_Button"]',
                        '[data-testid="AppTabBar_Home_Link"]', 
                        'a[href="/compose/tweet"]',
                        '[data-testid^="tweetTextarea"]']
            return any(await self.page.query_selector(sel) for sel in selectors)
        except Exception:
            return False

    async def ensure_logged_in(self):
        """Ensure user is logged in"""
        # Visit home page
        try:
            await self.page.goto('https://x.com/home', wait_until='domcontentloaded')
        except Exception:
            pass

        if await self.is_logged_in():
            logger.info('Detected logged in X/Twitter')
            return

        if self.headless:
            raise RuntimeError('Login not detected, please login manually after running in visual mode')

        logger.warning('Login not detected, please login manually in browser window')
        try:
            await self.page.goto('https://x.com/i/flow/login', wait_until='domcontentloaded')
        except Exception:
            pass

        # Wait for login to complete
        for _ in range(300):  # 10 minutes
            if await self.is_logged_in():
                # Save login state
                storage_state_path = ConfigManager.get('STORAGE_STATE_PATH')
                if storage_state_path:
                    try:
                        Path(storage_state_path).parent.mkdir(parents=True, exist_ok=True)
                        await self.context.storage_state(path=storage_state_path)
                        logger.info(f'Login state saved to {storage_state_path}')
                    except Exception:
                        pass
                logger.info('Login completed')
                return
            await asyncio.sleep(2)

        raise TimeoutError('Login timeout')
        
    async def search_stock_tweets_parallel(self, stock_symbol: str, max_tweets: int = None, num_pages: int = None) -> List[Dict]:
        """Parallel search for tweets"""
        try:
            # Use default values from config file
            if max_tweets is None:
                max_tweets = ConfigManager.get('MAX_TWEETS_PER_STOCK', 50)
            if num_pages is None:
                num_pages = ConfigManager.get('PARALLEL_PAGES', 3)
            
            query = self.build_query(stock_symbol)

            # Prepare pages
            pages = [self.page] if self.page else [await self.context.new_page()]
            extra_pages = []
            for _ in range(num_pages - 1):
                p = await self.context.new_page()
                pages.append(p)
                extra_pages.append(p)

            try:
                # Shared collection container: no limit on single page quota, stop when total is reached
                collected: List[Dict] = []
                seen_global = set()
                lock = asyncio.Lock()
                stop_event = asyncio.Event()
                
                page_counts: List[int] = [0] * num_pages
                async def worker(page: Page, worker_index: int) -> List[Dict]:
                    local_results = []  # Local results for each page
                    try:
                        # First half pages search top, second half pages search latest
                        half = max(1, num_pages // 2)
                        is_latest = worker_index >= half
                        f_param = '&f=live' if is_latest else ''
                        search_url = f"https://x.com/search?q={query}&src=typed_query{f_param}"
                        await page.goto(search_url, wait_until='networkidle')
                        await page.wait_for_timeout(600)

                        # Pre-scroll: different pages start from different positions
                        for _ in range(worker_index * 4):
                            try:
                                await page.mouse.wheel(0, 3000)
                                await page.wait_for_timeout(100)
                            except Exception:
                                pass

                        # Wait for tweets to load
                        tweet_selector = 'article[data-testid="tweet"], [data-testid="tweet"]'
                        try:
                            await page.wait_for_selector(tweet_selector, timeout=9000)
                        except Exception:
                            logger.warning(f"Page {worker_index} could not load tweet elements")

                        max_scroll = ConfigManager.get('MAX_SCROLL_ATTEMPTS', 20)

                        for _ in range(max_scroll):
                            if stop_event.is_set() or len(collected) >= max_tweets:
                                break
                                
                            items = await page.query_selector_all(tweet_selector)
                            if not items:
                                continue
                            
                            # Batch extract tweet data
                            batch_data = await self._extract_batch_tweets(items)
                            
                            # Filter valid data
                            valid_tweets = []
                            for data in batch_data:
                                if data and self._meets_online_filters(data):
                                    valid_tweets.append(data)
                            
                            if not valid_tweets:
                                try:
                                    await page.mouse.wheel(0, 3000)
                                    await page.wait_for_timeout(600)
                                except Exception:
                                    pass
                                continue
                            
                            # Batch processing: reduce lock contention
                            async with lock:
                                if stop_event.is_set() or len(collected) >= max_tweets:
                                    break
                                
                                for data in valid_tweets:
                                    if len(collected) >= max_tweets:
                                        stop_event.set()
                                        break
                                    
                                    key = (data.get('username'), data.get('timestamp'), (data.get('content') or '')[:100])
                                    if key not in seen_global:
                                        seen_global.add(key)
                                        collected.append(data)
                                        local_results.append(data)

                            try:
                                await page.mouse.wheel(0, 3000)
                                await page.wait_for_timeout(600)
                            except Exception:
                                pass

                        # Update page counts
                        async with lock:
                            page_counts[worker_index] = len(local_results)
                        logger.info(f"Page {worker_index} completed, collected {len(local_results)} tweets")
                        return local_results
                    except Exception as e:
                        logger.error(f"Page {worker_index} crawling failed: {e}")
                        # Ensure that when failed, the count is updated to 0
                        async with lock:
                            page_counts[worker_index] = 0
                        return []  # Return empty list, don't affect other pages

                # Execute parallel tasks
                tasks = [asyncio.create_task(worker(p, idx)) for idx, p in enumerate(pages)]
                # Wait for all tasks to complete, don't pre-cancel
                results = await asyncio.gather(*tasks, return_exceptions=True)
                

                

                # Quality filter
                merged = self.filter_tweets(collected,
                    min_likes=ConfigManager.get('MIN_LIKES', 0),
                    min_retweets=ConfigManager.get('MIN_RETWEETS', 0),
                    min_replies=ConfigManager.get('MIN_REPLIES', 0),
                    min_text_len=ConfigManager.get('MIN_TEXT_LEN', 0))

                logger.info(f"Parallel crawling completed, merged to {len(merged)} tweets")
                return merged[:max_tweets]
            finally:
                
                all_pages_to_close = pages  # Close all pages
                for i, p in enumerate(all_pages_to_close):
                    try:
                        await p.close()
                        logger.debug(f"Page {i} closed")
                    except Exception as e:
                        logger.warning(f"Failed to close page {i}: {e}")
               

        except Exception as e:
            logger.error(f"Error in parallel search: {e}")
            return []

    def filter_tweets(self, tweets: List[Dict], min_likes: int = 0, min_retweets: int = 0, 
                     min_replies: int = 0, min_text_len: int = 0) -> List[Dict]:
        """Filter tweets by minimum interaction and text length"""
        def is_valid(t: Dict) -> bool:
            return (len((t.get('content') or '').strip()) >= min_text_len and
                   (t.get('likes') or 0) >= min_likes and
                   (t.get('retweets') or 0) >= min_retweets and
                   (t.get('replies') or 0) >= min_replies)
        return [t for t in tweets if is_valid(t)]

    def _meets_online_filters(self, t: Dict) -> bool:
        """Online filter check"""
        if ConfigManager.get('EXCLUDE_RETWEETS', False) and t.get('is_retweet'):
            return False
        if ConfigManager.get('EXCLUDE_REPLIES', False) and t.get('is_reply'):
            return False
        return (
            (t.get('likes') or 0) >= ConfigManager.get('MIN_LIKES', 0) and
            (t.get('retweets') or 0) >= ConfigManager.get('MIN_RETWEETS', 0) and
            (t.get('replies') or 0) >= ConfigManager.get('MIN_REPLIES', 0) and
            len((t.get('content') or '').strip()) >= ConfigManager.get('MIN_TEXT_LEN', 0)
        )

    async def _get_metric(self, element, testid: str) -> int:
        """Get interaction metrics"""
        try:
            btn = await element.query_selector(f'[data-testid="{testid}"]')
            if not btn and testid == 'retweet':
                for alt in ('repost', 'unretweet'):
                    btn = await element.query_selector(f'[data-testid="{alt}"]')
                    if btn:
                        break
            if not btn:
                return 0

            # aria-label priority
            label = await btn.get_attribute('aria-label')
            if label:
                m = re.search(r'(\d+[\d,.]*\s*[KMBkmb]?)', label)
                if m:
                    return self.parse_number(m.group(1))

            # Common containers and text
            for sel in (
                '[data-testid="app-text-transition-container"]',
                'span[aria-hidden="true"]',
                'span',
            ):
                for sp in await btn.query_selector_all(sel):
                    txt = (await sp.inner_text()) or ''
                    m = re.search(r'(\d+[\d,.]*\s*[KMBkmb]?)', txt)
                    if m:
                        return self.parse_number(m.group(1))

            inner = await btn.inner_text()
            m = re.search(r'(\d+[\d,.]*\s*[KMBkmb]?)', inner or '')
            return self.parse_number(m.group(1)) if m else 0
        except Exception:
            return 0

    def build_query(self, stock_symbol: str) -> str:
        """Build search query"""
        # Get keywords
        search_keywords = ConfigManager.get('SEARCH_KEYWORDS', {})
        base_terms = search_keywords.get(stock_symbol, [f"${stock_symbol}", stock_symbol])
        fin_terms = ConfigManager.get('FINANCE_KEYWORDS', [])[:8]  # Limit length
        
        # URL encoding
        def encode(s: str) -> str:
            return s.replace(' ', '%20').replace('#', '%23').replace('$', '%24').replace('\n', '%0A')
        
        # Build query
        base_part = '(' + '%20OR%20'.join(encode(t) for t in base_terms) + ')'
        fin_part = '%20(' + '%20OR%20'.join(encode(t) for t in fin_terms) + ')' if fin_terms else ''
        query = base_part + fin_part
        
        # Add optional parameters
        for param in ['LANG', 'SINCE', 'UNTIL']:
            value = ConfigManager.get(param)
            if value:
                query += f"%20{param.lower()}:{encode(value)}"
        
        return query
    
    async def _extract_batch_tweets(self, tweet_elements) -> List[Dict]:
        """Batch extract tweet data"""
        if not tweet_elements:
            return []
        
        # Create parallel extraction tasks
        tasks = [self._extract_single_tweet(el) for el in tweet_elements]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid results
        valid_tweets = []
        for result in results:
            if isinstance(result, dict) and result:
                valid_tweets.append(result)
        
        return valid_tweets
    
    async def _extract_single_tweet(self, tweet_element) -> Optional[Dict]:
        """Extract single tweet data"""
        try:
            # User information
            user_link = await tweet_element.query_selector('[data-testid="User-Name"] a')
            username = await user_link.inner_text() if user_link else "Unknown user"
            user_id = await user_link.get_attribute('href') if user_link else ""
            if user_id.startswith('/'):
                user_id = user_id[1:]
            
            # Tweet content
            content_element = await tweet_element.query_selector('[data-testid="tweetText"]')
            content = await content_element.inner_text() if content_element else ""

            # Time
            time_element = await tweet_element.query_selector('time')
            tweet_time = await time_element.get_attribute('datetime') if time_element else ""
            
            # Interaction data
            likes = await self._get_metric(tweet_element, 'like')
            retweets = await self._get_metric(tweet_element, 'retweet')
            replies = await self._get_metric(tweet_element, 'reply')

            # Check retweet/reply
            is_retweet = bool(await tweet_element.query_selector('div:has-text("Retweeted")'))
            is_reply = bool(await tweet_element.query_selector('div[aria-label*="Replying to"], div:has-text("Replying to")'))
            
            return {
                'username': username, 'user_id': user_id, 'content': content,
                'timestamp': tweet_time, 'likes': likes, 'retweets': retweets, 
                'replies': replies, 'is_retweet': is_retweet, 'is_reply': is_reply
            }
            
        except Exception as e:
            logger.warning(f"Failed to extract tweet data: {e}")
            return None

    async def extract_tweet_data(self, tweet_element) -> Optional[Dict]:
        """Extract data from tweet element (keep backwards compatibility)"""
        return await self._extract_single_tweet(tweet_element)
    
    def parse_number(self, text: str) -> int:
        """Parse number text (e.g. '1.2K' -> 1200)"""
        if not text:
            return 0
        
        text = text.replace(',', '').upper()
        multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}
        
        for suffix, multiplier in multipliers.items():
            if suffix in text:
                try:
                    return int(float(text.replace(suffix, '')) * multiplier)
                except ValueError:
                    return 0
        
        try:
            return int(text)
        except ValueError:
            return 0
    
    async def save_to_json(self, data: List[Dict], filename: str):
        """Save data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Data saved to {filename}")
    

async def main():
    """Example usage"""
    # Use stock list from config file, use default values if not provided
    stocks =['TSLA']
    
    async with TwitterStockScraper(headless=False) as scraper:
        for stock in stocks:
            logger.info(f"Starting to scrape tweets for {stock}...")
            # Only use parallel mode
            tweets = await scraper.search_stock_tweets_parallel(stock)
            if scraper.last_page_counts:
                logger.info(f"Page counts: {scraper.last_page_counts}")
            
            if tweets:
                json_filename = f"{stock}_tweets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                await scraper.save_to_json(tweets, json_filename)
                
                total_likes = sum(tweet['likes'] for tweet in tweets)
                total_retweets = sum(tweet['retweets'] for tweet in tweets)
                
                logger.info(f"{stock} tweets: {len(tweets)} tweets, {total_likes} likes, {total_retweets} retweets")
            else:
                logger.warning(f"No tweets found for {stock}")
        
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
