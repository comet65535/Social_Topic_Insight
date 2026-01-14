from DrissionPage import ChromiumPage, ChromiumOptions
import datetime
import random
from core.logger import logger
from modules.crawler.base import BaseCrawler

class DouyinCrawler(BaseCrawler):
    def __init__(self):
        super().__init__()
        co = ChromiumOptions()
        # 复用手动浏览器 (9555端口)
        co.set_address('127.0.0.1:9555') 
        self.page = ChromiumPage(co)

    def get_hot_search_list(self):
        logger.info("--- [Douyin] Fetching Hot Search List ---")
        hot_keywords = []
        try:
            self.page.listen.start('web/hot/search/list')
            self.page.get('https://www.douyin.com/hot')
            res = self.page.listen.wait(timeout=10)
            if res:
                json_data = res.response.body
                word_list = json_data.get('data', {}).get('word_list', [])
                for item in word_list:
                    word = item.get('word', '').strip()
                    if word:
                        hot_keywords.append(word)
            
            self.page.listen.stop()
            logger.info(f"Got {len(hot_keywords)} hot keywords from Douyin.")
            return hot_keywords
        except Exception as e:
            logger.error(f"[Douyin] Failed to fetch hot list: {e}")
            try: self.page.listen.stop() 
            except: pass
            return []

    def crawl(self, keyword, sort_type="hot"):
        logger.info(f"--- [Douyin] Crawling: {keyword} (Mode: {sort_type}) ---")
        
        try:
            self.page.listen.start('aweme/v1/web/search/item')
            
            # sort_type=2最新, 0综合
            dy_sort_param = "&sort_type=2" if sort_type == "time" else "&sort_type=0"
            url = f"https://www.douyin.com/search/{keyword}?source=switch_tab&type=video{dy_sort_param}"
            
            self.page.get(url)
            
            res = self.page.listen.wait(timeout=15)
            if not res:
                logger.warning("[Douyin] No data packet captured.")
                return
            
            json_data = res.response.body
            video_list = json_data.get('data', [])
            
            count = 0 
            for item in video_list:
                if count >= 5: break
                
                if item.get('type') != 1: continue
                aweme_info = item.get('aweme_info', {})
                if not aweme_info: continue
                
                post_data = self.parse_douyin_video(aweme_info, keyword)
                if post_data:
                    self.save_data(post_data)
                    count += 1
            
            logger.info(f"   >>> [Douyin] '{keyword}' Saved: {count}")
            self.page.listen.stop()

        except Exception as e:
            logger.error(f"[Douyin] Crawl error: {e}")
            try: self.page.listen.stop() 
            except: pass

    def parse_douyin_video(self, data, keyword):
        try:
            aweme_id = data.get('aweme_id')
            desc = data.get('desc', '')
            create_time = data.get('create_time')
            publish_time = datetime.datetime.fromtimestamp(create_time) if create_time else datetime.datetime.now()

            stats = data.get('statistics', {})
            metrics = {
                'likes': stats.get('digg_count', 0),
                'comments': stats.get('comment_count', 0),
                'shares': stats.get('share_count', 0)
            }
            
            provinces = ["北京", "广东", "上海", "江苏", "浙江", "四川"]
            final_location = random.choice(provinces)

            social_post = {
                "platform": "douyin",
                "post_id": f"dy_{aweme_id}",
                "url": f"https://www.douyin.com/video/{aweme_id}",
                "content": desc,
                "clean_content": "",
                "publish_time": publish_time,
                "crawl_time": datetime.datetime.now(),
                "author_info": {
                    "user_id": data.get('author', {}).get('uid', ''),
                    "nickname": data.get('author', {}).get('nickname', '用户'),
                    "location": final_location,
                },
                "metrics": metrics,
                "ip_location": final_location,
                "process_status": 0,
                "topic_ref_id": None,
                "sentiment_score": None,
                "keywords": [],
                "embedding": None
            }
            return social_post
        except:
            return None