from .spiders.weibo import WeiboCrawler
from .spiders.douyin import DouyinCrawler
from .spiders.bilibili import BilibiliCrawler

class CrawlerFactory:
    @staticmethod
    def create_crawler(platform_type):
        if platform_type == "weibo":
            return WeiboCrawler()
        elif platform_type == "douyin":
            return DouyinCrawler()
        elif platform_type == "bilibili":
            return BilibiliCrawler()
        else:
            raise ValueError(f"Unknown platform: {platform_type}")