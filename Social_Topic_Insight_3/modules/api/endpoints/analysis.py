from fastapi import APIRouter
from core.database import db
from models.topic import AnalyzedTopic
from modules.api.utils import resp_200, resp_400
from bson import ObjectId
from collections import defaultdict
import math
from datetime import datetime, timedelta
import jieba.analyse
from collections import Counter # 记得引入


router = APIRouter()

# --- 辅助函数：情感映射 ---
def map_sentiment_to_stars(score):
    """将 -1~1 的情感分映射到 1~5 星"""
    if score is None: return 0
    # 线性映射: (-1 -> 1), (0 -> 3), (1 -> 5)
    stars = (score + 1) * 2 + 1
    # 限制范围并保留一位小数
    return round(max(1, min(5, stars)), 1)

@router.get("/hot-topics", response_model=dict)
async def get_hot_topics():
    collection = db.get_collection("analyzed_topics")
    cursor = collection.find().sort("total_heat", -1).limit(50)
    
    topics = []
    for doc in cursor:
        t = AnalyzedTopic(**doc)
        # 显式计算或从数据库取 (如果clustering存了的话)
        # 这里动态计算更保险，阈值 4000
        is_exp = t.total_heat > 4000 
        
        topics.append({
            "id": str(t.id),
            "topic": t.name,
            "hotScore": t.total_heat,
            "sentiment": round(t.avg_sentiment, 2),
            "isNew": t.is_burst,
            "isExplosive": is_exp, # 【修复】前端需要这个字段显示"爆"
            "keywords": t.keywords
        })
    return resp_200(data=topics)


# 2. 新增仪表盘图表接口
@router.get("/dashboard/charts", response_model=dict)
async def get_dashboard_charts():
    """获取仪表盘所需的图表数据：实时热度趋势 + 平台占比"""
    post_col = db.get_collection("social_posts")
    
    # === A. 平台占比 (Pie Chart) ===
    # MongoDB 聚合查询
    pipeline_platform = [
        {"$group": {"_id": "$platform", "count": {"$sum": 1}}}
    ]
    platform_data = list(post_col.aggregate(pipeline_platform))
    # 格式化为 ECharts 格式
    pie_data = [{"name": item["_id"], "value": item["count"]} for item in platform_data]
    
    # === B. 实时热度监控 (Line Chart - 过去24小时) ===
    # 既然是全量数据，用 Python 处理时间聚合可能比 Mongo 聚合稍微慢点但逻辑简单
    # 为了性能，我们只查最近 24 小时的数据
    
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    
    cursor = post_col.find(
        {"publish_time": {"$gte": yesterday}},
        {"publish_time": 1, "platform": 1} # 只取必要字段
    )
    
    # 初始化时间桶 (按小时)
    trend_map = defaultdict(int)
    # 也可以分平台统计，这里做总热度
    
    for doc in cursor:
        p_time = doc.get("publish_time")
        if p_time:
            # key: "14:00", "15:00"
            hour_str = p_time.strftime("%H:00")
            trend_map[hour_str] += 1
            
    # 排序时间轴 (为了图表连续性，最好补全缺失的小时，这里简化处理)
    # 构建最近24小时的完整 Key 列表
    line_x = []
    line_y = []
    
    current = yesterday
    while current <= now:
        hour_key = current.strftime("%H:00")
        line_x.append(hour_key)
        line_y.append(trend_map[hour_key])
        current += timedelta(hours=1)
        
    return resp_200(data={
        "pieData": pie_data,
        "lineData": {"x": line_x, "y": line_y}
    })

@router.get("/dashboard/stats", response_model=dict)
async def get_dashboard_stats():
    """获取仪表盘统计"""
    post_col = db.get_collection("social_posts")
    topic_col = db.get_collection("analyzed_topics")
    
    total_posts = post_col.count_documents({})
    total_topics = topic_col.count_documents({})
    negative_posts = post_col.count_documents({"sentiment_score": {"$lt": -0.3}})
    
    # 简单的环比模拟 (随机波动，为了演示好看)
    import random
    
    neg_rate = round((negative_posts / total_posts * 100), 1) if total_posts > 0 else 0
    
    stats = [
        {"title": '总帖子数', "value": f"{total_posts:,}", "icon": 'Document', "type": 'primary', "trend": 12.5},
        {"title": '活跃话题', "value": str(total_topics), "icon": 'ChatLineSquare', "type": 'success', "trend": 8.2},
        {"title": '突发热点', "value": str(topic_col.count_documents({"is_burst": True})), "icon": 'Lightning', "type": 'warning', "trend": -3.1},
        {"title": '负面舆情', "value": f"{neg_rate}%", "icon": 'Warning', "type": 'danger', "trend": 2.1}
    ]
    return resp_200(data=stats)

def map_sentiment_to_stars(score):
    """将情感分数映射为星级（示例实现，你可以替换为实际逻辑）"""
    if score >= 0.6:
        return 5
    elif score >= 0.2:
        return 4
    elif score >= -0.2:
        return 3
    elif score >= -0.6:
        return 2
    else:
        return 1

@router.get("/topic/{topic_id}", response_model=dict)
async def get_topic_detail(topic_id: str):
    """获取话题深度分析详情 (优化版：使用真实帖子关键词聚合词云)"""
    if not ObjectId.is_valid(topic_id):
        return resp_400(msg="无效的话题ID")

    t_oid = ObjectId(topic_id)
    topic_col = db.get_collection("analyzed_topics")
    post_col = db.get_collection("social_posts")
    trend_col = db.get_collection("topic_trends")

    topic_doc = topic_col.find_one({"_id": t_oid})
    if not topic_doc:
        return resp_400(msg="话题不存在")
    
    # === 1. 查询预计算的趋势数据 ===
    trend_cursor = trend_col.find({"topic_ref_id": t_oid}).sort("time_bucket", 1)
    trends = list(trend_cursor)
    
    # 构建图表数据
    dates = []
    values = []
    for t in trends:
        dates.append(t["time_bucket"]) 
        values.append(t["heat_value"])
    
    # === 2. 查 Post 表获取情感分布、关键词和最新帖子 (Top 100) ===
    posts_cursor = post_col.find(
        {"topic_ref_id": t_oid},
        {
            "content": 1, 
            "publish_time": 1, 
            "metrics": 1, 
            "sentiment_score": 1, 
            "platform": 1, 
            "author_info": 1,
            "keywords": 1  # 【新增】获取帖子的关键词字段
        }
    ).sort("metrics.likes", -1).limit(100)
    posts = list(posts_cursor)
    
    # 初始化情感分布和关键词列表
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    all_kws = []
    
    for p in posts:
        # 统计情感分布
        score = p.get("sentiment_score", 0) or 0
        if score > 0.3: 
            sentiment_dist["positive"] += 1
        elif score < -0.3: 
            sentiment_dist["negative"] += 1
        else: 
            sentiment_dist["neutral"] += 1
        
        # 【核心修复】收集所有帖子的关键词
        post_keywords = p.get("keywords", [])
        if isinstance(post_keywords, list) and post_keywords:
            all_kws.extend(post_keywords)

    # 【核心修复】统计关键词词频生成词云
    # 1. 统计前30个高频关键词
    kw_counts = Counter(all_kws).most_common(30)
    # 2. 过滤掉单字和纯数字的关键词，生成词云数据
    wordcloud = [
        {"name": kw, "value": count} 
        for kw, count in kw_counts 
        if len(kw) > 1 and not kw.isdigit()
    ]
    # 3. 回退机制：如果帖子关键词为空，使用话题的关键词（兼容原有逻辑）
    if not wordcloud:
        for idx, kw in enumerate(topic_doc.get("keywords", [])):
            wordcloud.append({"name": kw, "value": 100 - idx * 5})

    # 最新帖子 (Top 5)
    recent_posts = []
    for p in posts[:5]:
        recent_posts.append({
            "time": p.get("publish_time").strftime("%Y-%m-%d %H:%M") if p.get("publish_time") else "-",
            "platform": p.get("platform", "unknown"),
            "author": p.get("author_info", {}).get("nickname", "用户"),
            "content": p.get("content", "")[:40] + "...",
            "likes": p.get("metrics", {}).get("likes", 0)
        })

    # === 3. 传播路径 & 演化 ===
    sorted_by_time = sorted(posts, key=lambda x: x.get("publish_time") or datetime.min)
    first_post = sorted_by_time[0] if sorted_by_time else None
    top_post = posts[0] if posts else None
    
    timeline_events = []
    if first_post:
        timeline_events.append({
            "timestamp": first_post.get("publish_time").strftime("%Y-%m-%d %H:%M"),
            "content": "话题初现： " + (first_post.get("content", "")[:30] + "..."),
            "author": first_post.get("author_info", {}).get("nickname"),
            "platform": first_post.get("platform"),
            "type": "start"
        })
    if top_post and first_post and top_post["_id"] != first_post["_id"]:
        timeline_events.append({
            "timestamp": top_post.get("publish_time").strftime("%Y-%m-%d %H:%M"),
            "content": "舆论引爆： " + (top_post.get("content", "")[:30] + "..."),
            "author": top_post.get("author_info", {}).get("nickname"),
            "platform": top_post.get("platform"),
            "type": "peak"
        })

    # 演化数据
    evolution_data = None
    if len(posts) > 10:
        total_len = len(posts)
        p1, p2 = int(total_len * 0.3), int(total_len * 0.7)
        stages = [("起步期", posts[:p1]), ("爆发期", posts[p1:p2]), ("长尾期", posts[p2:])]
        
        all_text = " ".join([p.get("content", "") for p in posts])
        top_keywords = jieba.analyse.extract_tags(all_text, topK=5, allowPOS=('n', 'nr', 'ns', 'vn'))
        
        evolution_data = {"stages": [], "keywords": top_keywords}
        for stage_name, stage_posts in stages:
            stage_text = " ".join([p.get("content", "") for p in stage_posts])
            stage_stats = {"name": stage_name}
            for kw in top_keywords:
                stage_stats[kw] = stage_text.count(kw)
            evolution_data["stages"].append(stage_stats)

    raw_sentiment = topic_doc.get("avg_sentiment", 0)
    star_rating = map_sentiment_to_stars(raw_sentiment)

    # === 4. 组装返回数据 ===
    data = {
        "id": str(topic_doc["_id"]),
        "topic": topic_doc["name"],
        "hotScore": topic_doc["total_heat"],
        "sentimentScore": star_rating,
        "firstOccurTime": topic_doc["first_occur_time"].strftime("%Y-%m-%d %H:%M") if topic_doc.get("first_occur_time") else "-",
        "trendData": {"dates": dates, "values": values},
        "sentimentDist": [
            {"name": "正面", "value": sentiment_dist["positive"]},
            {"name": "中性", "value": sentiment_dist["neutral"]},
            {"name": "负面", "value": sentiment_dist["negative"]}
        ],
        "wordCloud": wordcloud,  # 使用新生成的词云数据
        "recentPosts": recent_posts,
        "propagationTimeline": timeline_events,
        "evolutionData": evolution_data
    }

    return resp_200(data=data)

# === 新增接口 1：全网词云透视 ===
@router.get("/wordcloud", response_model=dict)
async def get_global_wordcloud():
    """聚合全网热点词云"""
    collection = db.get_collection("analyzed_topics")
    # 取前 150 个热点话题
    cursor = collection.find().sort("total_heat", -1).limit(150)
    
    word_freq = defaultdict(int)
    
    for doc in cursor:
        heat = doc.get("total_heat", 0)
        keywords = doc.get("keywords", [])
        # 简单算法：话题越热，它的关键词权重越高
        # 排名越靠前的词，权重越高
        for i, kw in enumerate(keywords[:4]): # 只取每话题前4词
            weight = int(math.sqrt(heat) * (5 - i))
            word_freq[kw] += weight
            
    # 转为列表
    result = [{"name": k, "value": v} for k, v in word_freq.items()]
    # 按权重降序，取前 200 个词
    result.sort(key=lambda x: x['value'], reverse=True)
    return resp_200(data=result[:200])

# === 新增接口 2：话题关系网 ===
@router.get("/graph", response_model=dict)
async def get_topic_graph():
    """生成话题聚类 2D 分布图 (Intertopic Distance Map)"""
    collection = db.get_collection("analyzed_topics")
    # 取全部话题 (或者 Top 50 以免图太挤)
    cursor = collection.find().sort("total_heat", -1).limit(50)
    
    data = []
    
    for doc in cursor:
        data.append({
            "id": str(doc["_id"]),
            "name": doc["name"],
            # 获取存入的坐标，如果没有则默认为0
            "x": doc.get("x", 0.0),
            "y": doc.get("y", 0.0),
            "value": doc.get("total_heat", 0),
            "sentiment": doc.get("avg_sentiment", 0),
            "keywords": doc.get("keywords", [])[:5]
        })
                
    return resp_200(data=data)