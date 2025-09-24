import asyncio
import json
import csv
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TwitterStockScraper:
    def __init__(self, headless: bool = True, delay_range: tuple = (1, 3)):
        """
        推特股票信息爬虫
        
        Args:
            headless: 是否无头模式运行
            delay_range: 请求间隔时间范围（秒）
        """
        # 若调用方未显式传参，则从 config 读取默认
        try:
            try:
                from .config import Config as Cfg
            except Exception:
                from config import Config as Cfg
        except Exception:
            Cfg = type("Cfg", (), {})  # type: ignore

        self.headless = headless if headless is not None else getattr(Cfg, 'HEADLESS', True)
        self.delay_range = delay_range if delay_range is not None else getattr(Cfg, 'DELAY_RANGE', (1, 3))
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None
        self._playwright = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close_browser()
        
    async def start_browser(self):
        """启动浏览器"""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        # 创建新页面并设置用户代理
        # 创建上下文，优先载入 storage_state（若存在）
        storage_state_path = None
        try:
            try:
                from .config import Config as Cfg
            except Exception:
                from config import Config as Cfg
            storage_state_path = getattr(Cfg, 'STORAGE_STATE_PATH', None)
        except Exception:
            storage_state_path = None

        if storage_state_path and Path(storage_state_path).exists():
            self.context = await self.browser.new_context(storage_state=storage_state_path)
        else:
            self.context = await self.browser.new_context()

            # 若无 storage_state，则尝试载入 Cookies JSON（优先 primary，回退 backup）
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                cookies_path = getattr(Cfg, 'COOKIES_JSON_PATH', 'X_cookies.json')
            except Exception:
                cookies_path = 'X_cookies.json'

            try:
                p = Path(__file__).parent / cookies_path if not Path(cookies_path).exists() else Path(cookies_path)
                if p.exists():
                    with p.open('r', encoding='utf-8') as f:
                        data = json.load(f)
                    cookie_sets = []
                    if isinstance(data, dict):
                        if isinstance(data.get('primary'), list) and data['primary']:
                            cookie_sets = data['primary']
                        elif isinstance(data.get('backup'), list) and data['backup']:
                            cookie_sets = data['backup']
                    if cookie_sets:
                        # 适配 x.com / twitter.com 双域名
                        def adapt(c):
                            return {
                                'name': c.get('name'),
                                'value': c.get('value'),
                                'domain': c.get('domain') or '.x.com',
                                'path': c.get('path') or '/',
                                'httpOnly': bool(c.get('httpOnly')),
                                'secure': bool(c.get('secure', True)),
                                'sameSite': c.get('sameSite', 'Lax'),
                            }

                        cookies = [adapt(c) for c in cookie_sets if c.get('name') and c.get('value')]
                        # 复制一份 twitter.com 域名（若仅提供 .x.com）
                        dup = []
                        for c in cookies:
                            if c.get('domain') and 'x.com' in c['domain']:
                                c2 = dict(c)
                                c2['domain'] = '.twitter.com'
                                dup.append(c2)
                        cookies.extend(dup)
                        await self.context.add_cookies(cookies)
                        logger.info(f'已从 Cookies 文件加载 {len(cookies)} 条 cookie: {p}')
            except Exception as e:
                logger.warning(f'载入 Cookies JSON 失败，将继续无 Cookies：{e}')

        self.page = await self.context.new_page()
        await self.page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        # 登录检测与处理
        await self.ensure_logged_in()
        
    async def close_browser(self):
        """关闭浏览器"""
        try:
            # 先关页面
            if self.page:
                try:
                    await self.page.close()
                except Exception:
                    pass
                finally:
                    self.page = None

            # 再关上下文
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass
                finally:
                    self.context = None

            # 再关浏览器
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
                finally:
                    self.browser = None
        finally:
            # 最后停止 Playwright 运行时
            if getattr(self, '_playwright', None):
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                finally:
                    self._playwright = None
            
    async def random_delay(self):
        """随机延迟"""
        delay = random.uniform(*self.delay_range)
        await asyncio.sleep(delay)

    async def is_logged_in(self) -> bool:
        """检查是否已登录：优先依据 auth_token Cookie，其次检查典型已登录页面元素"""
        try:
            # 尝试通过 Cookie 判断
            context = self.page.context if self.page else None
            if context:
                cookies = await context.cookies()
                for c in cookies:
                    if c.get('name') == 'auth_token':
                        return True
        except Exception:
            pass

        # Fallback：检查页面特征元素（侧边栏账号按钮或发帖入口）
        try:
            # 已登录通常能看到侧边栏账号切换按钮
            el = await self.page.query_selector('[data-testid="SideNav_AccountSwitcher_Button"]')
            if el:
                return True
            # 或者能看到发帖/消息按钮等
            el2 = await self.page.query_selector('[data-testid="AppTabBar_Home_Link"], a[href="/compose/tweet"], [data-testid^="tweetTextarea"]')
            return el2 is not None
        except Exception:
            return False

    async def ensure_logged_in(self):
        """确保用户已登录。未登录时：
        - 若为无头模式：抛出异常提示切换到可视化模式
        - 若为可视化模式：引导用户手动登录并等待直到登录完成
        """
        try:
            # 访问主页，若未登录通常会跳到 /login 流程
            await self.page.goto('https://x.com/home', wait_until='domcontentloaded')
        except Exception:
            # 退回 twitter.com 域名
            try:
                await self.page.goto('https://twitter.com/home', wait_until='domcontentloaded')
            except Exception:
                pass

        # 初步判定
        if await self.is_logged_in():
            logger.info('检测到已登录 X/Twitter。')
            return

        # 未登录
        if self.headless:
            raise RuntimeError('未检测到登录态。请以可视化模式(headless=False)运行后先手动登录一次。')

        logger.warning('未检测到登录态。请在弹出的浏览器窗口中完成登录，然后我会继续。')
        # 导航到登录页
        try:
            await self.page.goto('https://x.com/i/flow/login', wait_until='domcontentloaded')
        except Exception:
            pass

        # 轮询等待用户登录完成（最多10分钟）
        total_wait_s = 600
        interval_s = 2
        waited = 0
        while waited < total_wait_s:
            try:
                if await self.is_logged_in():
                    # 登录完成，保存 storage_state 以便下次复用
                    try:
                        try:
                            from .config import Config as Cfg
                        except Exception:
                            from config import Config as Cfg
                        storage_state_path = getattr(Cfg, 'STORAGE_STATE_PATH', None)
                        if storage_state_path:
                            p = Path(storage_state_path)
                            p.parent.mkdir(parents=True, exist_ok=True)
                            await self.context.storage_state(path=storage_state_path)
                            logger.info(f'登录态已保存到 {storage_state_path}')
                    except Exception:
                        pass
                    logger.info('登录完成，继续执行。')
                    return
            except Exception:
                pass
            await asyncio.sleep(interval_s)
            waited += interval_s

        raise TimeoutError('等待登录超时。请重试并确保完成登录。')
        
    async def search_stock_tweets(self, stock_symbol: str, max_tweets: int = 50) -> List[Dict]:
        """
        搜索特定股票的推文
        
        Args:
            stock_symbol: 股票代码，如 'AAPL', 'TSLA'
            max_tweets: 最大爬取推文数量
            
        Returns:
            推文数据列表
        """
        try:
            # 若配置开启多页面并行，则走并行抓取
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                parallel_pages = max(1, int(getattr(Cfg, 'PARALLEL_PAGES', 1)))
                max_parallel_pages = max(1, int(getattr(Cfg, 'MAX_PARALLEL_PAGES', 10)))
            except Exception:
                parallel_pages = 1
                max_parallel_pages = 10

            if parallel_pages >= 2:
                return await self.search_stock_tweets_parallel(
                    stock_symbol,
                    max_tweets=max_tweets,
                    num_pages=min(parallel_pages, max_parallel_pages)
                )

            # 构建增强查询（简洁语法）：(cashtag/别名) + 基础财经词 + 可选语言/日期
            query = self.build_query(stock_symbol)
            # Tab 切换：'top' -> 无 f 参数 或 f=top；'latest' -> f=live
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                tab = getattr(Cfg, 'SEARCH_TAB', 'top')
            except Exception:
                tab = 'top'

            f_param = ''
            if tab == 'latest':
                f_param = '&f=live'
            elif tab == 'top':
                f_param = ''  # Top 无需附加，保留默认排序

            search_url = f"https://twitter.com/search?q={query}&src=typed_query{f_param}"
            logger.info(f"正在搜索股票: {stock_symbol}")
            
            # 访问搜索页面
            await self.page.goto(search_url, wait_until='networkidle')
            await self.random_delay()
            
            # 等待页面加载（更稳健的选择器），必要时触发多次滚动再重试
            found = False
            try:
                await self.page.wait_for_selector('article[data-testid="tweet"], [data-testid="tweet"]', timeout=12000)
                found = True
            except Exception:
                # 初次未命中则滚动-重试若干次
                for _ in range(3):
                    try:
                        await self.page.mouse.wheel(0, 2500)
                    except Exception:
                        try:
                            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        except Exception:
                            pass
                    await self.page.wait_for_timeout(1200)
                    try:
                        await self.page.wait_for_selector('article[data-testid="tweet"], [data-testid="tweet"]', timeout=4000)
                        found = True
                        break
                    except Exception:
                        continue
            
            tweets = []
            scroll_attempts = 0
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                max_scroll_attempts = getattr(Cfg, 'MAX_SCROLL_ATTEMPTS', 20)
            except Exception:
                max_scroll_attempts = 20
            
            seen_keys = set()
            while len(tweets) < max_tweets and scroll_attempts < max_scroll_attempts:
                # 获取当前页面的推文（兼容多种 DOM）
                tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')

                # 若仍未识别到推文则先滚动一段距离再继续
                if not tweet_elements:
                    try:
                        await self.page.mouse.wheel(0, 2500)
                    except Exception:
                        try:
                            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        except Exception:
                            pass
                    await self.page.wait_for_timeout(1000)
                    tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')

                for tweet_element in tweet_elements:
                    if len(tweets) >= max_tweets:
                        break
                        
                    try:
                        tweet_data = await self.extract_tweet_data(tweet_element)
                        if not tweet_data:
                            continue

                        # 在线过滤：转推/回复与质量阈值
                        if not self._meets_online_filters(tweet_data):
                            continue

                        # 去重：使用 (username, timestamp, content前50)
                        key = None
                        key = (tweet_data.get('username'), tweet_data.get('timestamp'), (tweet_data.get('content') or '')[:50])
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        tweets.append(tweet_data)
                        logger.info(f"已爬取 {len(tweets)} 条推文")
                    except Exception as e:
                        logger.warning(f"提取推文数据时出错: {e}")
                        continue
                
                # 滚动加载更多内容
                try:
                    await self.page.mouse.wheel(0, 3000)
                except Exception:
                    try:
                        await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    except Exception:
                        pass
                await self.page.wait_for_timeout(1200)
                scroll_attempts += 1
                
            logger.info(f"搜索完成，共获取 {len(tweets)} 条推文")
            # 应用质量过滤（如果配置了阈值）
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                tweets = self.filter_tweets(
                    tweets,
                    min_likes=getattr(Cfg, 'MIN_LIKES', 0),
                    min_retweets=getattr(Cfg, 'MIN_RETWEETS', 0),
                    min_replies=getattr(Cfg, 'MIN_REPLIES', 0),
                    min_text_len=getattr(Cfg, 'MIN_TEXT_LEN', 0),
                )
                logger.info(f"质量过滤后剩余 {len(tweets)} 条推文")
            except Exception:
                pass
            # 抓取评论（可选）
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                if getattr(Cfg, 'FETCH_REPLIES', False) and tweets:
                    enriched = []
                    for t in tweets:
                        detail_url = None
                        # 本版本不再携带 urls，无法可靠还原详情地址；跳过
                        # 若解析不到，尝试构造
                        if not detail_url and t.get('user_id') and t.get('timestamp'):
                            # 无法可靠构造，保持 None
                            pass
                        if detail_url:
                            replies = await self.fetch_replies_for_tweet(
                                detail_url,
                                max_replies=getattr(Cfg, 'MAX_REPLIES_PER_TWEET', 10),
                                min_len=getattr(Cfg, 'REPLIES_MIN_TEXT_LEN', 0),
                            )
                            t['replies_detail'] = replies
                        enriched.append(t)
                    tweets = enriched
            except Exception as e:
                logger.warning(f"抓取评论失败（将继续返回主贴）: {e}")
            return tweets
            
        except Exception as e:
            logger.error(f"搜索推文时出错: {e}")
            return []

    async def search_stock_tweets_parallel(self, stock_symbol: str, max_tweets: int = 50, num_pages: int = 3) -> List[Dict]:
        """并行开启多个页面抓取，减少单页滚动带来的等待时间与重复。

        策略：
        - 第1个页面直接开始采集；
        - 第2/3个页面在进入搜索页后先向下滚动一定距离再开始采集，以降低重叠；
        - 采集结束后在内存中去重并按质量过滤（遵循 config）。
        """
        try:
            # 查询参数与 tab
            query = self.build_query(stock_symbol)
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
                tab = getattr(Cfg, 'SEARCH_TAB', 'top')
                max_scroll_attempts_cfg = getattr(Cfg, 'MAX_SCROLL_ATTEMPTS', 20)
                min_likes_cfg = getattr(Cfg, 'MIN_LIKES', 0)
                min_retweets_cfg = getattr(Cfg, 'MIN_RETWEETS', 0)
                min_replies_cfg = getattr(Cfg, 'MIN_REPLIES', 0)
                min_text_len_cfg = getattr(Cfg, 'MIN_TEXT_LEN', 0)
            except Exception:
                tab = 'top'
                max_scroll_attempts_cfg = 20
                min_likes_cfg = 0
                min_retweets_cfg = 0
                min_replies_cfg = 0
                min_text_len_cfg = 0

            f_param = ''
            if tab == 'latest':
                f_param = '&f=live'

            search_url = f"https://twitter.com/search?q={query}&src=typed_query{f_param}"

            # 准备页面：第一个用 self.page，其余新开
            pages = []
            if self.page is None:
                # 兜底：未初始化就开一个
                self.page = await self.context.new_page()
            pages.append(self.page)
            extra_pages = []
            try:
                for _ in range(max(0, num_pages - 1)):
                    p = await self.context.new_page()
                    pages.append(p)
                    extra_pages.append(p)

                async def worker(page: Page, worker_index: int) -> List[Dict]:
                    # 导航
                    await page.goto(search_url, wait_until='networkidle')
                    await page.wait_for_timeout(600)

                    # 预滚动：按页面索引递增，index 0 不滚，其余每页多滚 3 次，封顶 24 次
                    pre_scroll_times = min(max(0, worker_index * 3), 24)

                    for _ in range(pre_scroll_times):
                        try:
                            await page.mouse.wheel(0, 2500)
                        except Exception:
                            try:
                                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                            except Exception:
                                pass
                        await page.wait_for_timeout(900)

                    # 等待初次推文出现
                    found = False
                    try:
                        await page.wait_for_selector('article[data-testid="tweet"], [data-testid="tweet"]', timeout=9000)
                        found = True
                    except Exception:
                        for _ in range(2):
                            try:
                                await page.mouse.wheel(0, 2500)
                            except Exception:
                                try:
                                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                                except Exception:
                                    pass
                            await page.wait_for_timeout(900)
                            try:
                                await page.wait_for_selector('article[data-testid="tweet"], [data-testid="tweet"]', timeout=4000)
                                found = True
                                break
                            except Exception:
                                continue

                    results: List[Dict] = []
                    seen_local = set()
                    scroll_attempts = 0

                    while len(results) < max_tweets and scroll_attempts < max_scroll_attempts_cfg:
                        items = await page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')
                        if not items:
                            try:
                                await page.mouse.wheel(0, 2500)
                            except Exception:
                                try:
                                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                                except Exception:
                                    pass
                            await page.wait_for_timeout(900)
                            items = await page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')

                        for el in items:
                            if len(results) >= max_tweets:
                                break
                            try:
                                data = await self.extract_tweet_data(el)
                                if not data:
                                    continue
                                if not self._meets_online_filters(data):
                                    continue
                                key = (data.get('username'), data.get('timestamp'), (data.get('content') or '')[:50])
                                if key in seen_local:
                                    continue
                                seen_local.add(key)
                                results.append(data)
                            except Exception:
                                continue

                        try:
                            await page.mouse.wheel(0, 3000)
                        except Exception:
                            try:
                                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                            except Exception:
                                pass
                        await page.wait_for_timeout(1000)
                        scroll_attempts += 1

                    return results

                tasks = [asyncio.create_task(worker(p, idx)) for idx, p in enumerate(pages[:num_pages])]
                all_results_nested = await asyncio.gather(*tasks, return_exceptions=False)

                # 合并去重
                merged: List[Dict] = []
                seen_global = set()
                for lst in all_results_nested:
                    for t in lst:
                        key = (t.get('username'), t.get('timestamp'), (t.get('content') or '')[:50])
                        if key in seen_global:
                            continue
                        seen_global.add(key)
                        merged.append(t)

                # 质量过滤
                merged = self.filter_tweets(
                    merged,
                    min_likes=min_likes_cfg,
                    min_retweets=min_retweets_cfg,
                    min_replies=min_replies_cfg,
                    min_text_len=min_text_len_cfg,
                )

                # 可选抓取评论（沿用原逻辑，默认关闭）
                try:
                    try:
                        from .config import Config as Cfg
                    except Exception:
                        from config import Config as Cfg
                    if getattr(Cfg, 'FETCH_REPLIES', False) and merged:
                        enriched = []
                        for t in merged:
                            # 无可靠详情 URL，保持原样
                            enriched.append(t)
                        merged = enriched
                except Exception:
                    pass

                return merged[:max_tweets]
            finally:
                # 关闭额外创建的页面
                for p in extra_pages:
                    try:
                        await p.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"并行搜索推文时出错: {e}")
            return []

    def filter_tweets(
        self,
        tweets: List[Dict],
        min_likes: int = 0,
        min_retweets: int = 0,
        min_replies: int = 0,
        min_text_len: int = 0,
    ) -> List[Dict]:
        """按最小互动与文本长度过滤，保留更可能“有价值”的讨论"""
        def ok(t: Dict) -> bool:
            try:
                if min_text_len and len((t.get('content') or '').strip()) < min_text_len:
                    return False
                if min_likes and (t.get('likes') or 0) < min_likes:
                    return False
                if min_retweets and (t.get('retweets') or 0) < min_retweets:
                    return False
                if min_replies and (t.get('replies') or 0) < min_replies:
                    return False
                return True
            except Exception:
                return False
        return [t for t in tweets if ok(t)]

    def _meets_online_filters(self, t: Dict) -> bool:
        """在采集循环中进行的快速过滤，减少不必要解析与保存"""
        try:
            try:
                from .config import Config as Cfg
            except Exception:
                from config import Config as Cfg

            if getattr(Cfg, 'EXCLUDE_RETWEETS', False) and t.get('is_retweet'):
                return False
            if getattr(Cfg, 'EXCLUDE_REPLIES', False) and t.get('is_reply'):
                return False

            if (t.get('likes') or 0) < getattr(Cfg, 'MIN_LIKES', 0):
                return False
            if (t.get('retweets') or 0) < getattr(Cfg, 'MIN_RETWEETS', 0):
                return False
            if (t.get('replies') or 0) < getattr(Cfg, 'MIN_REPLIES', 0):
                return False
            if len((t.get('content') or '').strip()) < getattr(Cfg, 'MIN_TEXT_LEN', 0):
                return False

            # 本版本不再检查外链域名（不采集 urls）
            return True
        except Exception:
            return True

    async def fetch_replies_for_tweet(self, tweet_url: str, max_replies: int = 10, min_len: int = 0) -> List[Dict]:
        """进入详情页抓取评论，尽量简单稳健
        返回字段：username, user_id, content, timestamp, likes, retweets, replies
        """
        try:
            page = await self.context.new_page()
            await page.goto(tweet_url, wait_until='networkidle')
            await page.wait_for_timeout(1200)
            results: List[Dict] = []
            seen = set()
            scrolls = 0
            while len(results) < max_replies and scrolls < 15:
                # 评论通常也是 tweet article，但需要排除首贴本身（含 status id 与主内容）
                items = await page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')
                for el in items:
                    try:
                        # 复用提取，但不需要 urls/is_retweet/is_reply
                        text_el = await el.query_selector('div[data-testid="tweetText"]')
                        content = (await text_el.inner_text()).strip() if text_el else ''
                        if min_len and len(content) < min_len:
                            continue

                        time_el = await el.query_selector('time')
                        ts = await time_el.get_attribute('datetime') if time_el else None

                        user_link = await el.query_selector('[data-testid="User-Name"] a')
                        user_name = await user_link.inner_text() if user_link else None
                        user_id = await user_link.get_attribute('href') if user_link else None
                        if user_id and user_id.startswith('/'):
                            user_id = user_id[1:]

                        # 排除首贴：首贴通常与详情 URL 的 status id 一致，可通过首个包含状态链接的 a 来判断
                        # 简化处理：以 content+ts 作为去重键
                        key = (content[:80], ts)
                        if key in seen or not content:
                            continue
                        seen.add(key)

                        # 点赞/转推/回复
                        def get_metric(testid: str) -> int:
                            try:
                                btn = el.query_selector(f'[data-testid="{testid}"]')
                                if not btn:
                                    return 0
                                label = btn.get_attribute('aria-label') or btn.inner_text()
                                return self.parse_number(label or '')
                            except Exception:
                                return 0

                        item = {
                            'username': user_name,
                            'user_id': user_id,
                            'content': content,
                            'timestamp': ts,
                            'likes': get_metric('like'),
                            'retweets': get_metric('retweet'),
                            'replies': get_metric('reply'),
                        }
                        results.append(item)
                        if len(results) >= max_replies:
                            break
                    except Exception:
                        continue

                if len(results) >= max_replies:
                    break

                try:
                    await page.mouse.wheel(0, 3000)
                except Exception:
                    try:
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    except Exception:
                        pass
                await page.wait_for_timeout(1000)
                scrolls += 1

            await page.close()
            return results[:max_replies]
        except Exception:
            return []

    def build_query(self, stock_symbol: str) -> str:
        """基于 config 的简洁增强查询
        规则：
        - 关键词：优先使用 SEARCH_KEYWORDS 中的数组，否则 [$SYMBOL, SYMBOL]
        - 拼接基础财经关键词（用 OR，保持简洁）
        - 可选 lang/since/until 直接拼接
        """
        try:
            # 延迟导入，避免相对导入问题
            try:
                from .config import Config as Cfg
            except Exception:
                from config import Config as Cfg

            base_terms = []
            if hasattr(Cfg, 'SEARCH_KEYWORDS') and isinstance(Cfg.SEARCH_KEYWORDS, dict) and stock_symbol in Cfg.SEARCH_KEYWORDS:
                base_terms = Cfg.SEARCH_KEYWORDS[stock_symbol]
            else:
                base_terms = [f"${stock_symbol}", stock_symbol]

            # 简洁财经词
            fin_terms = getattr(Cfg, 'FINANCE_KEYWORDS', []) or []

            # 组装：(term1 OR term2) (kw1 OR kw2)
            def enc(s: str) -> str:
                return (
                    s.replace(' ', '%20')
                     .replace('#', '%23')
                     .replace('$', '%24')
                     .replace('\n', '%0A')
                )

            base_part = '(' + '%20OR%20'.join([enc(t) for t in base_terms]) + ')'
            fin_part = ''
            if fin_terms:
                fin_part = '%20(' + '%20OR%20'.join([enc(t) for t in fin_terms[:8]]) + ')'  # 控制长度，避免过复杂

            q = base_part + fin_part

            # 语言 & 日期（若配置了再拼）
            lang = getattr(Cfg, 'LANG', None)
            if lang:
                q += f"%20lang:{enc(lang)}"
            since = getattr(Cfg, 'SINCE', None)
            if since:
                q += f"%20since:{enc(since)}"
            until = getattr(Cfg, 'UNTIL', None)
            if until:
                q += f"%20until:{enc(until)}"

            return q
        except Exception:
            # 兜底仅用 cashtag
            return f"%24{stock_symbol}"
    
    async def extract_tweet_data(self, tweet_element) -> Optional[Dict]:
        """
        从推文元素中提取数据
        
        Args:
            tweet_element: 推文DOM元素
            
        Returns:
            推文数据字典
        """
        try:
            # 提取用户名
            username_element = await tweet_element.query_selector('[data-testid="User-Name"] a')
            username = await username_element.inner_text() if username_element else "未知用户"
            
            # 提取用户ID
            user_id_element = await tweet_element.query_selector('[data-testid="User-Name"] a')
            user_id = await user_id_element.get_attribute('href') if user_id_element else ""
            if user_id.startswith('/'):
                user_id = user_id[1:]
            
            # 提取推文内容
            content_element = await tweet_element.query_selector('[data-testid="tweetText"]')
            content = await content_element.inner_text() if content_element else ""

            # 提取时间
            time_element = await tweet_element.query_selector('time')
            tweet_time = ""
            if time_element:
                tweet_time = await time_element.get_attribute('datetime')
            
            # 提取互动数据（点赞、转发等）
            like_element = await tweet_element.query_selector('[data-testid="like"]')
            likes = 0
            if like_element:
                like_text = await like_element.inner_text()
                likes = self.parse_number(like_text)
            
            retweet_element = await tweet_element.query_selector('[data-testid="retweet"]')
            retweets = 0
            if retweet_element:
                retweet_text = await retweet_element.inner_text()
                retweets = self.parse_number(retweet_text)
            
            reply_element = await tweet_element.query_selector('[data-testid="reply"]')
            replies = 0
            if reply_element:
                reply_text = await reply_element.inner_text()
                replies = self.parse_number(reply_text)

            # 判断是否为转推/回复（尽力而为，DOM可能调整）
            is_retweet = False
            is_reply = False
            try:
                # 转推通常包含 "Retweeted" 或上方有包含 retweeted 提示的元素
                rt_hint = await tweet_element.query_selector('div:has-text("Retweeted")')
                if rt_hint:
                    is_retweet = True
            except Exception:
                pass
            try:
                # 回复通常链接里会含有 /status/<id>? 底下有 reply 提示
                rp_hint = await tweet_element.query_selector('div[aria-label*="Replying to"], div:has-text("Replying to")')
                if rp_hint:
                    is_reply = True
            except Exception:
                pass
            
            return {
                'username': username,
                'user_id': user_id,
                'content': content,
                'timestamp': tweet_time,
                'likes': likes,
                'retweets': retweets,
                'replies': replies,
                'is_retweet': is_retweet,
                'is_reply': is_reply,
                # 不返回 URL 与爬虫元数据
            }
            
        except Exception as e:
            logger.warning(f"提取推文数据失败: {e}")
            return None
    
    def parse_number(self, text: str) -> int:
        """解析数字文本（如 '1.2K' -> 1200）"""
        if not text:
            return 0
        
        text = text.replace(',', '').upper()
        
        if 'K' in text:
            return int(float(text.replace('K', '')) * 1000)
        elif 'M' in text:
            return int(float(text.replace('M', '')) * 1000000)
        elif 'B' in text:
            return int(float(text.replace('B', '')) * 1000000000)
        else:
            try:
                return int(text)
            except ValueError:
                return 0
    
    async def save_to_json(self, data: List[Dict], filename: str):
        """保存数据到JSON文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"数据已保存到 {filename}")
    
    async def save_to_csv(self, data: List[Dict], filename: str):
        """保存数据到CSV文件"""
        if not data:
            return
            
        fieldnames = data[0].keys()
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"数据已保存到 {filename}")

# 使用示例
async def main():
    """主函数示例"""
    # 要搜索的股票列表
    #stocks = ['AAPL', 'TSLA', 'GOOGL', 'MSFT', 'AMZN']
    stocks = ['TSLA']
    
    async with TwitterStockScraper(headless=False) as scraper:
        for stock in stocks:
            logger.info(f"开始爬取 {stock} 的推文...")
            
            # 搜索推文
            tweets = await scraper.search_stock_tweets(stock, max_tweets=10)
            
            if tweets:
                # 保存数据
                json_filename = f"{stock}_tweets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                await scraper.save_to_json(tweets, json_filename)
                
                # 打印统计信息
                total_likes = sum(tweet['likes'] for tweet in tweets)
                total_retweets = sum(tweet['retweets'] for tweet in tweets)
                
                logger.info(f"{stock} 推文统计:")
                logger.info(f"  总推文数: {len(tweets)}")
                logger.info(f"  总点赞数: {total_likes}")
                logger.info(f"  总转发数: {total_retweets}")
            else:
                logger.warning(f"未找到 {stock} 的相关推文")
            
            # 在搜索不同股票之间添加延迟
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
