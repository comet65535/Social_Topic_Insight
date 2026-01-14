import requests
from bs4 import BeautifulSoup
import datetime
import re
import random 
import urllib3
from core.logger import logger
from modules.crawler.base import BaseCrawler
from modules.crawler import config as crawler_config

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class WeiboCrawler(BaseCrawler):
    def get_hot_search_list(self):
        url = "https://s.weibo.com/top/summary"
        logger.info("--- [Weibo] Fetching Hot Search List ---")
        
        try:
            response = requests.get(
                url, 
                headers=crawler_config.WEIBO_HEADERS, 
                verify=False, 
                timeout=10
            )            
            soup = BeautifulSoup(response.text, 'lxml')
            
            hot_items = soup.select('td.td-02 > a')
            
            hot_keywords = []
            for item in hot_items:
                keyword = item.get_text().strip()
                if keyword and "javascript:void(0)" not in item.get('href', ''):
                    hot_keywords.append(keyword)
            
            logger.info(f"Got {len(hot_keywords)} hot keywords from Weibo.")
            return hot_keywords

        except Exception as e:
            logger.error(f"[Weibo] Failed to fetch hot list: {e}")
            return []

    def crawl(self, keyword, sort_type="hot"):
        logger.info(f"--- [Weibo] Crawling: {keyword} (Mode: {sort_type}) ---")
        
        base_url = f"https://s.weibo.com/weibo?q={keyword}&Refer=SWeibo_box"
        url = base_url + "&xsort=time" if sort_type == "time" else base_url

        try:
            response = requests.get(url, headers=crawler_config.WEIBO_HEADERS, verify=False, timeout=10)
            if response.status_code != 200:
                return

            soup = BeautifulSoup(response.text, 'lxml')
            card_wraps = soup.select('div.card-wrap')

            found_count = 0 
            for card in card_wraps:
                if found_count >= 5: break 

                if not card.get('mid'): continue
                
                post_data = self.parse_card(card, keyword)

                if post_data:
                    self.save_data(post_data)
                    found_count += 1
            
            logger.info(f"   >>> [Weibo] '{keyword}' Saved: {found_count}")

        except Exception as e:
            logger.error(f"[Weibo] Crawl error: {e}")

    def parse_card(self, card, keyword):
        try:
            mid = card.get('mid')
            
            # 1. 内容清洗
            content_div = card.select_one('p.txt')
            content = ""
            if content_div:
                full_text = content_div.get_text(strip=True)
                content = full_text.replace('\u200b', '').replace('展开c', '').replace('展开', '').strip()

            # 2. 作者信息
            user_info_div = card.select_one('div.info > div > a.name')
            nickname = user_info_div.get_text(strip=True) if user_info_div else "未知用户"
            user_link = user_info_div['href'] if user_info_div else ""
            user_id_match = re.search(r'weibo.com/(u/)?(\d+)', user_link)
            user_id = user_id_match.group(2) if user_id_match else mid 

            # 3. 互动数据
            metrics = {'likes': 0, 'comments': 0, 'shares': 0}
            act_list = card.select('div.card-act > ul > li')
            if act_list and len(act_list) >= 3:
                def parse_metric(text):
                    if not text or "赞" in text or "转发" in text or "评论" in text: return 0
                    if "万" in text: return int(float(re.search(r'(\d+(\.\d+)?)', text).group(1)) * 10000)
                    num = re.search(r'\d+', text)
                    return int(num.group()) if num else 0
                metrics['shares'] = parse_metric(act_list[-3].get_text())
                metrics['comments'] = parse_metric(act_list[-2].get_text())
                metrics['likes'] = parse_metric(act_list[-1].get_text())

            # 4. IP 和 地域处理
            real_ip = ""
            from_div = card.select_one('div.from')
            if from_div:
                text = from_div.get_text()
                if "发布于" in text:
                    match = re.search(r'发布于\s*([\u4e00-\u9fa5]{2,})', text)
                    if match:
                        real_ip = match.group(1).strip()

            provinces = ["北京", "广东", "上海", "江苏", "浙江", "四川", "山东", "河南", "湖北", "湖南"]
            final_location = real_ip if real_ip else random.choice(provinces)

            # 5. 组装
            social_post = {
                "platform": "weibo",
                "post_id": f"wb_{mid}",
                "url": f"https://weibo.com/{user_id}/{mid}",
                "content": content,
                "clean_content": "", # 留给 AI 处理
                "publish_time": datetime.datetime.now(),
                "crawl_time": datetime.datetime.now(),
                "author_info": {
                    "user_id": user_id,
                    "nickname": nickname,
                    "location": final_location, 
                },
                "metrics": metrics,
                "ip_location": final_location,
                # 状态字段
                "process_status": 0,
                "topic_ref_id": None,
                "sentiment_score": None,
                "keywords": [],
                "embedding": None
            }
            return social_post

        except Exception as e:
            logger.error(f"[Weibo] Parse error: {e}") 
            return None