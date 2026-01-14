from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
from hdbscan import HDBSCAN
from umap import UMAP
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core.database import db
from core.logger import logger
from models.topic import AnalyzedTopic
from models.trend import TopicTrend
from .nlp_base import NLPProcessor
from collections import defaultdict
import google.generativeai as genai
import requests
import time
import re
import random
import os
from core.config import settings


class ClusterEngine:
    def __init__(self):
        self.nlp = NLPProcessor()
        
        # 1. 终极停用词表
        custom_stopwords = list(self.nlp.stopwords)
        custom_stopwords.extend([
            "视频", "内容", "查看", "全文", "展开", "链接", "网页", 
            "合集", "日常", "记录", "打卡", "文案", "推荐", "分享",
            "相关", "话题", "编辑", "当地", "时间", "小时", "分钟", "左右",
            "ai", "dou", "vlog", "回复", "刚刚", "真棒", "好棒", "加油", 
            "今天", "昨天", "明天", "今年", "去年", "发生", "现在", "近日",
            "一月", "二月", "周一", "周日", "周末", "月份", "期间",
            "2024", "2025", "2026", "10", "11", "12", "01", "02"
        ])
        
        # 2. 优化 Vectorizer
        vectorizer_model = CountVectorizer(
            stop_words=custom_stopwords,
            min_df=2, 
            token_pattern=r'(?u)\b[a-zA-Z\u4e00-\u9fa5]{2,}\w*\b'
        )
        
        # 3. 聚类模型微调
        umap_model = UMAP(
            n_neighbors=10, 
            n_components=10, 
            min_dist=0.0, 
            metric='cosine', 
            random_state=42
        )
        
        hdbscan_model = HDBSCAN(
            min_cluster_size=3, 
            min_samples=2,      
            metric='euclidean', 
            cluster_selection_method='eom', 
            prediction_data=True
        )
        
        self.topic_model = BERTopic(
            embedding_model=self.nlp.embedder,
            vectorizer_model=vectorizer_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            language="multilingual",
            calculate_probabilities=False,
            verbose=True,
            nr_topics=None 
        )

    def generate_llm_topic_name(self, keywords, representative_docs):
        """
        生成话题名称：Google 轮询 (REST模式) + DeepSeek 重试
        """
        # === 配置区域 ===
        # 使用 .strip() 防止复制粘贴时带入空格或换行
        GOOGLE_API_KEY = settings.GOOGLE_API_KEY.strip()
        DEEPSEEK_API_KEY = settings.DEEPSEEK_API_KEY.strip()
        PROXY_URL = settings.PROXY_URL.strip()

        # 设置环境变量代理
        os.environ["HTTP_PROXY"] = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL

        # 准备 Prompt (保持不变)
        selected_docs = representative_docs[:5]
        if len(representative_docs) > 8:
            selected_docs.extend(random.sample(representative_docs[5:], 3))
        
        docs_text = "\n".join([
            f"- {doc.replace(chr(10), ' ').strip()[:150]}"
            for doc in selected_docs
        ])

        prompt = (
            f"请根据以下社交媒体帖子，总结一个**极简的新闻标题**（15字以内）。\n"
            f"{docs_text}\n"
            f"要求：直接输出标题，不要任何修饰或前缀，禁止包含'标题'二字。"
        )

        title_result = None

        # --- 1. Google Gemini (REST 模式轮询) ---
        google_models = [
            'gemini-1.5-flash', 
            'gemini-1.5-flash-001', 
            'gemini-1.5-pro',
            'gemini-pro'
        ]
        
        try:
            # 【关键修改】添加 transport='rest' 解决 gRPC 代理报错问题
            genai.configure(api_key=GOOGLE_API_KEY, transport='rest')
            
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=30, temperature=0.3
            )
            for model_name in google_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt, generation_config=generation_config)
                    if response.text:
                        t = response.text.strip().replace('"', '').replace('\n', '')
                        if len(t) > 2:
                            title_result = t
                            logger.info(f"[Google-{model_name}] Success: {title_result}")
                            break
                except Exception as inner_e:
                    # 忽略 404 和常见的网络错误，继续尝试下一个模型
                    error_str = str(inner_e).lower()
                    if "404" in error_str or "not found" in error_str:
                        continue
                    else:
                        # 记录一下非 404 错误，但不要刷屏
                        # logger.warning(f"Google {model_name} error: {error_str[:50]}...")
                        continue
        except Exception as e:
            logger.warning(f"Google SDK Error: {str(e)}")

        if title_result: return title_result

        # --- 2. DeepSeek (保持不变) ---
        proxies = {"http": PROXY_URL, "https": PROXY_URL}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 50
        }

        for attempt in range(2):
            try:
                if attempt > 0: time.sleep(1)
                response = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers, json=payload, timeout=20, proxies=proxies
                )
                if response.status_code == 200:
                    res_json = response.json()
                    t = res_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                    if t and len(t) > 2:
                        title_result = t.replace('"', '').replace('\n', '')
                        logger.info(f"[DeepSeek] Success: {title_result}")
                        break
                else:
                    logger.warning(f"DeepSeek fail: {response.status_code}")
            except Exception as e:
                logger.warning(f"DeepSeek error: {str(e)}")

        if title_result: return title_result

        # --- 3. 兜底 ---
        return self._fallback(keywords)

    def _fallback(self, keywords):
        stop_phrases = {"相关", "话题", "视频", "内容", "查看", "全文", "ai", "dou"}
        valid_kws = [k for k in keywords if 2 < len(k) <= 8 and not k.isdigit() and k not in stop_phrases]
        if not valid_kws:
            valid_kws = [k for k in keywords if len(k) > 2 and k not in stop_phrases]
        if not valid_kws:
            return "热门话题"
        valid_kws.sort(key=len, reverse=True)
        return " ".join(valid_kws[:3])

    def run_clustering(self):
        logger.info("开始执行聚类任务...")
        
        # 1. 获取数据
        cursor = db.get_collection("social_posts").find(
            {"process_status": 1, "embedding": {"$ne": None}},
            {"content": 1, "embedding": 1, "publish_time": 1, "metrics": 1, "clean_content": 1, "sentiment_score": 1, "ip_location": 1, "post_id": 1}
        )
        all_posts = list(cursor)
        
        valid_posts = []
        valid_embeddings = []
        
        # 数据清洗
        for p in all_posts:
            emb = p.get("embedding")
            if not (emb and isinstance(emb, list) and len(emb) == 768): continue
            text = p.get("clean_content", "") or p.get("content", "")
            text_no_year = re.sub(r'202\d', '', text)
            if re.match(r'^[\d\W\s_]+$', text_no_year): continue
            if len(text_no_year.strip()) < 4: continue
            if text.count('#') > 5: continue
            valid_posts.append(p)
            valid_embeddings.append(emb)
        
        if len(valid_posts) < 20:
            logger.warning(f"Not enough valid data. Valid: {len(valid_posts)}")
            return

        docs = [re.sub(r'202\d', '', p.get("clean_content", "") or p.get("content", "")) for p in valid_posts]
        embeddings = np.array(valid_embeddings)
        ids = [p["_id"] for p in valid_posts]

        logger.info(f"Fitting BERTopic model with {len(docs)} cleaned docs...")
        
        # 2. 训练模型
        topics, probs = self.topic_model.fit_transform(docs, embeddings)
        topic_info = self.topic_model.get_topic_info()
        logger.info(f"Initial topics found: {len(topic_info) - 1}")
        
        # 计算 2D 坐标
        logger.info("Calculating 2D coordinates...")
        topic_embeddings = self.topic_model.topic_embeddings_
        umap_2d = UMAP(n_neighbors=15, n_components=2, min_dist=0.2, metric='cosine', random_state=42)
        embeddings_2d = umap_2d.fit_transform(np.array(topic_embeddings))
        
        topic_coords = {}
        all_topic_ids = list(self.topic_model.topic_representations_.keys())
        for i, t_id in enumerate(all_topic_ids):
            if i < len(embeddings_2d):
                topic_coords[t_id] = [float(embeddings_2d[i][0]), float(embeddings_2d[i][1])]

        # === 3. 聚合统计 ===
        topic_stats = defaultdict(lambda: {
            "heat_score": 0, "posts_count": 0, "sentiment_sum": 0.0, "sentiment_count": 0,
            "min_time": None, "max_time": None, "geo_map": defaultdict(int)
        })
        trend_stats = defaultdict(lambda: defaultdict(lambda: {
            "heat": 0, "count": 0, "sent_sum": 0.0, "sent_count": 0,
            "max_likes": -1, "rep_post_id": None
        }))

        # 热度预计算
        likes_arr = np.array([p.get("metrics", {}).get("likes", 0) or 0 for p in valid_posts], dtype=float)
        comments_arr = np.array([p.get("metrics", {}).get("comments", 0) or 0 for p in valid_posts], dtype=float)
        shares_arr = np.array([p.get("metrics", {}).get("shares", 0) or 0 for p in valid_posts], dtype=float)
        views_arr = np.array([p.get("metrics", {}).get("views", 0) or 0 for p in valid_posts], dtype=float)

        likes_log = np.log1p(likes_arr)
        comments_log = np.log1p(comments_arr)
        shares_log = np.log1p(shares_arr)
        views_log = np.log1p(views_arr / 50.0) 

        def normalize(arr):
            _min, _max = arr.min(), arr.max()
            if _max == _min: return np.zeros_like(arr)
            return (arr - _min) / (_max - _min)

        interaction_score = 10 + (normalize(views_log) * 10) + (normalize(likes_log) * 20) + \
                            (normalize(comments_log) * 40) + (normalize(shares_log) * 60)

        # 【时间衰减修复】：如果数据整体较老，不要用当前系统时间(2026)去减，而是用数据集中最新的时间
        data_max_time = max([p.get("publish_time") for p in valid_posts if p.get("publish_time")], default=datetime.now())
        # 如果系统时间比数据时间快太多(超过30天)，说明是在跑历史数据，用数据时间作为锚点
        anchor_time = datetime.now()
        if (anchor_time - data_max_time).days > 30:
            anchor_time = data_max_time + timedelta(hours=1)
            logger.info(f"Detected historical data. Using anchor time: {anchor_time}")

        final_scores = []
        for i, p in enumerate(valid_posts):
            p_time = p.get("publish_time")
            time_weight = 0.001 
            if p_time:
                diff = anchor_time - p_time
                hours_diff = diff.total_seconds() / 3600
                days_diff = diff.days
                # 放宽时间衰减，7天内都算热
                if days_diff > 7: time_weight = 0.001
                else: time_weight = 1 / (1 + 0.05 * max(0, hours_diff))
            final_scores.append(interaction_score[i] * time_weight)

        # 遍历填充
        for i, topic_id in enumerate(topics):
            if topic_id == -1: continue 
            
            post = valid_posts[i]
            heat_val = final_scores[i]
            
            topic_stats[topic_id]["posts_count"] += 1
            topic_stats[topic_id]["heat_score"] += heat_val
            
            s_score = post.get("sentiment_score")
            if s_score is not None:
                topic_stats[topic_id]["sentiment_sum"] += s_score
                topic_stats[topic_id]["sentiment_count"] += 1
            
            p_time = post.get("publish_time")
            if p_time:
                if topic_stats[topic_id]["min_time"] is None or p_time < topic_stats[topic_id]["min_time"]:
                    topic_stats[topic_id]["min_time"] = p_time
                if topic_stats[topic_id]["max_time"] is None or p_time > topic_stats[topic_id]["max_time"]:
                    topic_stats[topic_id]["max_time"] = p_time
                
                time_bucket = p_time.strftime("%Y-%m-%d %H:00")
                t_bucket = trend_stats[topic_id][time_bucket]
                t_bucket["heat"] += heat_val
                t_bucket["count"] += 1
                if s_score is not None:
                    t_bucket["sent_sum"] += s_score
                    t_bucket["sent_count"] += 1
                if likes_arr[i] > t_bucket["max_likes"]:
                    t_bucket["max_likes"] = likes_arr[i]
                    t_bucket["rep_post_id"] = post.get("post_id")

            loc = post.get("ip_location", "未知")
            if loc and loc != "未知":
                topic_stats[topic_id]["geo_map"][loc] += 1

        # ==========================================
        # 找出真正的“最热”话题 ID 集合
        # ==========================================
        sorted_topics_by_heat = sorted(
            topic_stats.items(), 
            key=lambda x: x[1]['heat_score'], 
            reverse=True
        )
        top_50_hot_ids = set([item[0] for item in sorted_topics_by_heat[:50]])
        logger.info(f"Identified Top 50 hottest topics for LLM naming.")

        # 4. 入库逻辑
        topic_collection = db.get_collection("analyzed_topics")
        post_collection = db.get_collection("social_posts")
        trend_collection = db.get_collection("topic_trends")
        
        topic_collection.delete_many({}) 
        trend_collection.delete_many({}) 

        topic_map = {} 
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        all_trend_docs = []

        for index, row in topic_info.iterrows():
            t_id = row['Topic']
            if t_id == -1: continue 
            if t_id not in topic_stats: continue 
            
            stats = topic_stats[t_id]
            avg_sent = 0.0
            if stats["sentiment_count"] > 0:
                avg_sent = stats["sentiment_sum"] / stats["sentiment_count"]
            
            sorted_geo = sorted(stats["geo_map"].items(), key=lambda x: x[1], reverse=True)[:10]
            geo_list = [{"name": k, "value": v} for k, v in sorted_geo]

            raw_kws = [w[0] for w in self.topic_model.get_topic(t_id)]
            rep_docs = self.topic_model.get_representative_docs(t_id)
            
            # 判断当前话题是否属于“最热Top 50”
            if t_id in top_50_hot_ids: 
                topic_name = self.generate_llm_topic_name(raw_kws, rep_docs)
            else:
                topic_name = self._fallback(raw_kws)

            display_kws = [k for k in raw_kws if len(k) > 1 and not k.isdigit() and k not in self.nlp.stopwords]

            # 热度值修正：确保显示好看 (你的截图里是235，说明被时间衰减打得很低)
            final_heat = int(stats["heat_score"])
            is_explosive = final_heat > 3000
            
            first_time = stats["min_time"] or now
            is_new_burst = (first_time > yesterday) and (stats["posts_count"] > 5)
            coords = topic_coords.get(t_id, [0.0, 0.0])
            
            new_topic = AnalyzedTopic(
                name=topic_name,
                keywords=display_kws[:10],
                total_heat=final_heat,
                post_count=stats["posts_count"],
                avg_sentiment=round(avg_sent, 4),
                first_occur_time=first_time,
                last_active_time=stats["max_time"] or now,
                is_burst=is_new_burst, 
                geo_distribution=geo_list
            )
            
            topic_dict = new_topic.model_dump(by_alias=True, exclude={"id"})
            topic_dict["x"] = coords[0]
            topic_dict["y"] = coords[1]
            
            res = topic_collection.insert_one(topic_dict)
            db_topic_id = res.inserted_id # 这里获取的是 ObjectId
            topic_map[t_id] = db_topic_id
            
            current_trends = trend_stats[t_id]
            for t_bucket, t_data in current_trends.items():
                t_avg_sent = 0.0
                if t_data["sent_count"] > 0:
                    t_avg_sent = t_data["sent_sum"] / t_data["sent_count"]
                
                trend_doc = TopicTrend(
                    topic_ref_id=db_topic_id,
                    time_bucket=t_bucket,
                    heat_value=int(t_data["heat"]),
                    post_count=t_data["count"],
                    sentiment_value=round(t_avg_sent, 4),
                    representative_post=t_data["rep_post_id"]
                )
                
                # 【关键修复】手动覆盖 topic_ref_id，确保它是 ObjectId 类型
                dumped_trend = trend_doc.model_dump(by_alias=True, exclude={"id"})
                dumped_trend["topic_ref_id"] = db_topic_id  # 强制使用 ObjectId 对象
                
                all_trend_docs.append(dumped_trend)

        if all_trend_docs:
            trend_collection.insert_many(all_trend_docs)

        logger.info("Updating post topic references...")
        from pymongo import UpdateOne
        bulk_ops = []
        for i, topic_num in enumerate(topics):
            if topic_num != -1 and topic_num in topic_map:
                bulk_ops.append(
                    UpdateOne({"_id": ids[i]}, {"$set": {"topic_ref_id": topic_map[topic_num]}})
                )
        if bulk_ops:
            post_collection.bulk_write(bulk_ops)

        logger.info("Clustering finished.")