from collections import defaultdict
from datetime import datetime, timedelta
from math import sqrt
from typing import Any, Dict, List

from pymongo import UpdateOne

from core.database import db
from core.logger import logger
from models.topic import AnalyzedTopic
from models.trend import TopicTrend
from .nlp_base import NLPProcessor


class ClusterEngine:
    """
    Lightweight clustering engine for MQ worker mode.
    It keeps the same Mongo contracts expected by Java services:
    - analyzed_topics: includes rep_docs, task_id, and empty name
    - topic_trends: hourly trend buckets
    """

    def __init__(self):
        self.nlp = NLPProcessor()

    @staticmethod
    def _safe_publish_time(post: Dict[str, Any]) -> datetime:
        publish_time = post.get("publish_time")
        return publish_time if isinstance(publish_time, datetime) else datetime.now()

    @staticmethod
    def _calc_heat(metrics: Dict[str, Any]) -> int:
        likes = int(metrics.get("likes", 0) or 0)
        comments = int(metrics.get("comments", 0) or 0)
        shares = int(metrics.get("shares", 0) or 0)
        views = int(metrics.get("views", 0) or 0)

        # Simple but stable heat formula.
        score = likes * 3 + comments * 5 + shares * 8 + int(sqrt(max(views, 0)))
        return max(score, 1)

    @staticmethod
    def _topic_coords(topic_key: str) -> List[float]:
        seed_a = hash(topic_key)
        seed_b = hash(topic_key[::-1])
        x = ((seed_a % 2000) - 1000) / 100.0
        y = ((seed_b % 2000) - 1000) / 100.0
        return [x, y]

    def _topic_key_from_post(self, post: Dict[str, Any]) -> str:
        keywords = post.get("keywords") or []
        if keywords:
            return str(keywords[0])

        text = post.get("clean_content") or post.get("content") or ""
        inferred = self.nlp.get_keywords(text) if text else []
        return inferred[0] if inferred else "其他话题"

    def run_clustering(self, task_id=None):
        logger.info("Start topic clustering...")

        post_collection = db.get_collection("social_posts")
        topic_collection = db.get_collection("analyzed_topics")
        trend_collection = db.get_collection("topic_trends")

        cursor = post_collection.find(
            {"process_status": 1},
            {
                "content": 1,
                "clean_content": 1,
                "keywords": 1,
                "sentiment_score": 1,
                "publish_time": 1,
                "metrics": 1,
                "ip_location": 1,
                "post_id": 1,
            },
        )
        posts = list(cursor)

        if len(posts) < 10:
            logger.warning(f"Not enough processed posts for clustering. count={len(posts)}")
            return

        groups = defaultdict(
            lambda: {
                "posts": [],
                "keywords": defaultdict(int),
                "rep_docs": [],
                "heat": 0,
                "sent_sum": 0.0,
                "sent_count": 0,
                "min_time": None,
                "max_time": None,
                "geo": defaultdict(int),
                "trend": defaultdict(lambda: {"heat": 0, "count": 0, "sent_sum": 0.0, "sent_count": 0, "rep_post": None}),
            }
        )

        for post in posts:
            topic_key = self._topic_key_from_post(post)
            g = groups[topic_key]

            text = (post.get("clean_content") or post.get("content") or "").strip()
            publish_time = self._safe_publish_time(post)
            metrics = post.get("metrics") or {}
            heat = self._calc_heat(metrics)
            sent = post.get("sentiment_score")

            g["posts"].append(post)
            g["heat"] += heat
            if text:
                g["rep_docs"].append(text[:200])

            for kw in (post.get("keywords") or []):
                if isinstance(kw, str) and kw.strip():
                    g["keywords"][kw.strip()] += 1

            if sent is not None:
                g["sent_sum"] += float(sent)
                g["sent_count"] += 1

            if g["min_time"] is None or publish_time < g["min_time"]:
                g["min_time"] = publish_time
            if g["max_time"] is None or publish_time > g["max_time"]:
                g["max_time"] = publish_time

            location = post.get("ip_location")
            if location:
                g["geo"][str(location)] += 1

            bucket = publish_time.strftime("%Y-%m-%d %H:00")
            t = g["trend"][bucket]
            t["heat"] += heat
            t["count"] += 1
            if sent is not None:
                t["sent_sum"] += float(sent)
                t["sent_count"] += 1
            t["rep_post"] = post.get("post_id")

        # Rebuild topic collections by latest clustering snapshot.
        topic_collection.delete_many({})
        trend_collection.delete_many({})

        sorted_groups = sorted(groups.items(), key=lambda x: x[1]["heat"], reverse=True)
        top_50_keys = {name for name, _ in sorted_groups[:50]}

        now = datetime.now()
        yesterday = now - timedelta(days=1)

        topic_id_map = {}
        trend_docs = []

        for topic_key, data in sorted_groups:
            post_count = len(data["posts"])
            if post_count == 0:
                continue

            keywords = [k for k, _ in sorted(data["keywords"].items(), key=lambda x: x[1], reverse=True)[:10]]
            if not keywords:
                keywords = [topic_key]

            avg_sent = (data["sent_sum"] / data["sent_count"]) if data["sent_count"] else 0.0
            first_time = data["min_time"] or now
            last_time = data["max_time"] or now
            is_burst = first_time > yesterday and post_count >= 5
            coords = self._topic_coords(topic_key)

            geo_distribution = [
                {"name": k, "value": v}
                for k, v in sorted(data["geo"].items(), key=lambda x: x[1], reverse=True)[:10]
            ]

            topic = AnalyzedTopic(
                name="",
                keywords=keywords,
                total_heat=int(data["heat"]),
                post_count=post_count,
                avg_sentiment=round(avg_sent, 4),
                first_occur_time=first_time,
                last_active_time=last_time,
                is_burst=is_burst,
                geo_distribution=geo_distribution,
            )

            topic_doc = topic.model_dump(by_alias=True, exclude={"id"})
            topic_doc["x"] = coords[0]
            topic_doc["y"] = coords[1]
            topic_doc["task_id"] = str(task_id) if task_id else None
            topic_doc["rep_docs"] = data["rep_docs"][:8]
            topic_doc["is_hot_top50"] = topic_key in top_50_keys

            insert_result = topic_collection.insert_one(topic_doc)
            topic_id_map[topic_key] = insert_result.inserted_id

            for bucket, t in data["trend"].items():
                avg_sent_bucket = (t["sent_sum"] / t["sent_count"]) if t["sent_count"] else 0.0
                trend = TopicTrend(
                    topic_ref_id=insert_result.inserted_id,
                    time_bucket=bucket,
                    heat_value=int(t["heat"]),
                    post_count=int(t["count"]),
                    sentiment_value=round(avg_sent_bucket, 4),
                    representative_post=t["rep_post"],
                )
                trend_doc = trend.model_dump(by_alias=True, exclude={"id"})
                trend_doc["topic_ref_id"] = insert_result.inserted_id
                trend_docs.append(trend_doc)

        if trend_docs:
            trend_collection.insert_many(trend_docs)

        # Backfill social_posts.topic_ref_id
        bulk_ops = []
        for topic_key, data in sorted_groups:
            topic_ref_id = topic_id_map.get(topic_key)
            if topic_ref_id is None:
                continue
            for post in data["posts"]:
                bulk_ops.append(UpdateOne({"_id": post["_id"]}, {"$set": {"topic_ref_id": topic_ref_id}}))

        if bulk_ops:
            post_collection.bulk_write(bulk_ops)

        logger.info(f"Clustering finished. topics={len(topic_id_map)}, posts={len(posts)}")