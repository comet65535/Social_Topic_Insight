import os
import random
from dotenv import load_dotenv

load_dotenv()

# === 微博配置 ===
# 建议：生产环境中，Cookie 最好放在 .env 文件中读取，这里为了保持你原有的逻辑暂时写死
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "")
WEIBO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cookie": WEIBO_COOKIE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer" : "https://s.weibo.com/",
    "Host": "s.weibo.com"
}

# === 舆情监控种子库 ===
OPINION_KEYWORDS = [
    "突发", "曝光", "回应", "通报", "致歉", "辟谣", "热议", "吐槽", "避雷", "网传", "实锤"
]

DOMAIN_KEYWORDS = {
    "livelihood": ["医院", "学校", "烂尾", "裁员", "欠薪", "停课", "医保", "社保", "停水", "停电", "物业纠纷"],
    "tech": ["发布会", "测评", "漏洞", "bug", "下架", "封号", "隐私泄露", "遥遥领先", "显卡", "大模型"],
    "entertainment": ["塌房", "官宣", "解约", "抵制", "停播", "延播", "口碑翻车", "假唱", "耍大牌"],
    "society": ["失联", "坠亡", "火灾", "车祸", "爆炸", "冲突", "救助", "霸座", "碰瓷", "诈骗"],
    "finance": ["维权", "退款难", "暴雷", "逾期", "烂尾", "降息", "理财亏损", "杀猪盘", "大数据杀熟"],
    "education": ["考研", "复试", "调剂", "分数线", "霸凌", "预制菜", "休学", "违规补课"]
}

TIME_TRIGGERS = ["最新", "刚刚", "今日", "目前", "紧急", "深夜"]

def get_smart_seeds(count=3):
    """
    智能生成本轮关键词
    """
    seeds = []
    # 1. 拿一个强舆情词
    seeds.append(random.choice(OPINION_KEYWORDS))
    
    # 2. 随机选一个领域，再从该领域抽 2 个词
    selected_domain = random.choice(list(DOMAIN_KEYWORDS.keys()))
    domain_words = random.sample(DOMAIN_KEYWORDS[selected_domain], 2)
    seeds.extend(domain_words)
    
    # 3. 组合逻辑
    final_queries = []
    for word in seeds:
        if random.random() < 0.3:
            trigger = random.choice(TIME_TRIGGERS)
            final_queries.append(f"{trigger} {word}")
        else:
            final_queries.append(word)
            
    return final_queries