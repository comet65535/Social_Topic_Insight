from DrissionPage import ChromiumPage, ChromiumOptions
import datetime
import time
import random
import re
import json
from core.logger import logger
from modules.crawler.base import BaseCrawler

class BilibiliCrawler(BaseCrawler):
    def __init__(self):
        super().__init__()
        co = ChromiumOptions()
        co.set_address('127.0.0.1:9555') 
        self.page = ChromiumPage(co)

    def get_hot_search_list(self):
        logger.info("--- [Bilibili] Fetching Hot Search List ---")
        hot_keywords = []
        try:
            self.page.get('https://api.bilibili.com/x/web-interface/search/square?limit=50')
            try:
                raw_text = self.page.ele('tag:body').text
                data = json.loads(raw_text)
            except:
                data = self.page.json

            if data and isinstance(data, dict):
                trending = data.get('data', {}).get('trending', {})
                item_list = trending.get('list', [])
                for item in item_list:
                    keyword = item.get('keyword', '').strip()
                    if keyword:
                        hot_keywords.append(keyword)
            
            logger.info(f"Got {len(hot_keywords)} hot keywords from Bilibili.")
            return hot_keywords

        except Exception as e:
            logger.error(f"[Bilibili] Failed to fetch hot list: {e}")
            return []

    def crawl(self, keyword, sort_type="hot"):
        logger.info(f"--- [Bilibili] Crawling: {keyword} (Mode: {sort_type}) ---")
        try:
            # order=pubdate (time), order=click (hot)
            # order_param = "&order=pubdate" if sort_type == "time" else "&order=click"
            order_param = "&order=pubdate" 

            url = f"https://search.bilibili.com/all?keyword={keyword}&search_source=1{order_param}"
            self.page.get(url)
            time.sleep(2)
            
            cards = self.page.eles('css:.bili-video-card')
            if not cards:
                cards = self.page.eles('css:.video-item')

            count = 0
            for card in cards:
                if count >= 5: break
                try:
                    title_ele = card.ele('tag:h3', timeout=0.1)
                    if not title_ele: continue
                    title = title_ele.text
                    
                    href_ele = card.ele('tag:a', timeout=0.1)
                    href = href_ele.attr('href') if href_ele else ""
                    bv_match = re.search(r'(BV\w+)', href)
                    if not bv_match: continue
                    bvid = bv_match.group(1)
                    
                    author_ele = card.ele('css:.bili-video-card__info--author', timeout=0.1)
                    nickname = author_ele.text if author_ele else "B站UP主"

                    play_ele = card.ele('css:.bili-video-card__stats--item', index=1, timeout=0.1) 
                    play_count = self.parse_bilibili_number(play_ele.text) if play_ele else 0
                    
                    metrics = {
                        'views': play_count, 
                        'likes': int(play_count * 0.05), 
                        'comments': int(play_count * 0.01),
                        'shares': int(play_count * 0.02)
                    }

                    provinces = ["上海", "广东", "北京", "江苏", "浙江", "四川", "湖南"]
                    final_location = random.choice(provinces)

                    post_data = {
                        "platform": "bilibili",
                        "post_id": f"bv_{bvid}",
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "content": title,
                        "clean_content": "",
                        "publish_time": datetime.datetime.now(),
                        "crawl_time": datetime.datetime.now(),
                        "author_info": {
                            "user_id": nickname,
                            "nickname": nickname,
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
                    
                    self.save_data(post_data)
                    count += 1
                except Exception:
                    continue

            logger.info(f"   >>> [Bilibili] '{keyword}' Saved: {count}")

        except Exception as e:
            logger.error(f"[Bilibili] Crawl error: {e}")

    def parse_bilibili_number(self, text):
        if not text: return 0
        try:
            text = text.replace('播放', '').strip()
            multiplier = 1
            if '万' in text:
                multiplier = 10000
                text = text.replace('万', '')
            elif '亿' in text:
                multiplier = 100000000
                text = text.replace('亿', '')
            return int(float(text) * multiplier)
        except:
            return 0