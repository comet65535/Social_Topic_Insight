package com.service.controller;

import com.common.result.Result;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 分析结果查询控制器。
 * <p>
 * 前端仅调用 Spring；Spring 直接从 MongoDB（以及 Redis 缓存）读取分析结果。
 * Python 仅负责采集/清洗/聚类，不再承担分析接口查询职责。
 */
@Slf4j
@CrossOrigin // 允许前端跨域访问分析接口
@RestController // 声明为 REST 控制器，返回 JSON
@RequiredArgsConstructor
@RequestMapping("/api/analysis") // 统一分析接口前缀
public class AnalysisController {

    private static final DateTimeFormatter HOUR_BUCKET_FMT = DateTimeFormatter.ofPattern("HH:00", Locale.CHINA);
    private static final DateTimeFormatter DT_MINUTE_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm", Locale.CHINA);
    private static final ZoneId ZONE_ID = ZoneId.systemDefault();

    private final RedisTemplate<String, Object> redisTemplate;
    private final MongoTemplate mongoTemplate;
    private final ObjectMapper objectMapper;

    @Value("${topic.cache.hot-topics-key:dashboard:hot_topics:top50}")
    private String hotTopicsCacheKey;

    @Value("${topic.cache.hot-topics-ttl-minutes:10}")
    private long hotTopicsCacheTtlMinutes;

    /**
     * 热点排行榜（Top 50）。
     *
     * @return 热点话题列表
     */
    @GetMapping("/hot-topics")
    public Result<List<Map<String, Object>>> getHotTopics() {
        // Step 1: 优先读缓存（由 LlmSummaryService 预热）
        List<Map<String, Object>> cached = loadHotTopicsFromCache();
        if (!cached.isEmpty()) {
            return Result.success(cached);
        }

        // Step 2: 缓存未命中，回源 Mongo
        List<Map<String, Object>> fallback = queryHotTopicsFromMongo();
        if (!fallback.isEmpty()) {
            redisTemplate.opsForValue().set(hotTopicsCacheKey, fallback, Duration.ofMinutes(hotTopicsCacheTtlMinutes));
        }
        return Result.success(fallback);
    }

    /**
     * 仪表盘图表数据（平台占比 + 24 小时热度趋势）。
     *
     * @return 图表数据
     */
    @GetMapping("/dashboard/charts")
    public Result<Map<String, Object>> getDashboardCharts() {
        // Step 1: 锁定最新任务数据（若该任务尚未写入 task_id，则兜底全量）
        String latestTaskId = resolveLatestTaskId();
        Query postQuery = new Query();
        if (hasSocialPostsForTask(latestTaskId)) {
            postQuery.addCriteria(Criteria.where("task_id").is(latestTaskId));
        }
        postQuery.fields()
                .include("platform")
                .include("crawl_time")
                .include("publish_time");
        List<Document> firstBatch = mongoTemplate.find(postQuery, Document.class, "social_posts");

        // Step 2: 平台占比
        List<Map<String, Object>> pieData = new ArrayList<>();
        Map<String, Integer> platformCounter = new HashMap<>();
        for (Document item : firstBatch) {
            String platform = String.valueOf(item.getOrDefault("platform", "unknown"));
            platformCounter.merge(platform, 1, Integer::sum);
        }
        platformCounter.forEach((k, v) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", k);
            row.put("value", v);
            pieData.add(row);
        });

        // Step 3: 最近 24 小时趋势（优先 crawl_time，兜底 publish_time）
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime yesterday = now.minusDays(1);
        Date fromDate = Date.from(yesterday.atZone(ZONE_ID).toInstant());

        Map<String, Integer> bucketCounter = new ConcurrentHashMap<>();
        for (Document doc : firstBatch) {
            Date eventTime = toDate(doc.get("crawl_time"));
            if (eventTime == null) {
                eventTime = toDate(doc.get("publish_time"));
            }
            if (eventTime == null || eventTime.before(fromDate)) {
                continue;
            }
            LocalDateTime ldt = LocalDateTime.ofInstant(eventTime.toInstant(), ZONE_ID);
            String hourKey = ldt.format(HOUR_BUCKET_FMT);
            bucketCounter.merge(hourKey, 1, Integer::sum);
        }

        List<String> lineX = new ArrayList<>();
        List<Integer> lineY = new ArrayList<>();
        LocalDateTime cursor = yesterday;
        while (!cursor.isAfter(now)) {
            String key = cursor.format(HOUR_BUCKET_FMT);
            lineX.add(key);
            lineY.add(bucketCounter.getOrDefault(key, 0));
            cursor = cursor.plusHours(1);
        }

        Map<String, Object> lineData = new LinkedHashMap<>();
        lineData.put("x", lineX);
        lineData.put("y", lineY);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("pieData", pieData);
        data.put("lineData", lineData);
        return Result.success(data);
    }

    /**
     * 仪表盘统计卡片数据。
     *
     * @return 四个统计卡片数据
     */
    @GetMapping("/dashboard/stats")
    public Result<List<Map<String, Object>>> getDashboardStats() {
        String latestTaskId = resolveLatestTaskId();
        Document topicFilter = hasTopicsForTask(latestTaskId)
                ? new Document("task_id", latestTaskId)
                : new Document();
        Document postFilter = hasSocialPostsForTask(latestTaskId)
                ? new Document("task_id", latestTaskId)
                : new Document();

        long totalPosts = mongoTemplate.getCollection("social_posts").countDocuments(postFilter);
        long totalTopics = mongoTemplate.getCollection("analyzed_topics").countDocuments(topicFilter);
        long burstTopics = mongoTemplate.getCollection("analyzed_topics")
                .countDocuments(new Document(topicFilter).append("is_burst", true));
        long negativePosts = mongoTemplate.getCollection("social_posts")
                .countDocuments(new Document(postFilter).append("sentiment_score", new Document("$lt", -0.3)));

        double negRate = totalPosts > 0 ? round((negativePosts * 100.0) / totalPosts, 1) : 0.0;

        List<Map<String, Object>> stats = new ArrayList<>();
        stats.add(statItem("总帖子数", String.format("%,d", totalPosts), "Document", "primary", 12.5));
        stats.add(statItem("活跃话题", String.valueOf(totalTopics), "ChatLineSquare", "success", 8.2));
        stats.add(statItem("突发热点", String.valueOf(burstTopics), "Lightning", "warning", -3.1));
        stats.add(statItem("负面舆情", negRate + "%", "Warning", "danger", 2.1));
        return Result.success(stats);
    }

    /**
     * 全网词云透视数据。
     *
     * @return 词云列表
     */
    @GetMapping("/wordcloud")
    public Result<List<Map<String, Object>>> getWordCloud() {
        Query query = buildTopicQueryByLatestTask(150);
        List<Document> topics = mongoTemplate.find(query, Document.class, "analyzed_topics");

        Map<String, Integer> wordFreq = new HashMap<>();
        for (Document topic : topics) {
            int heat = toInt(topic.get("total_heat"));
            List<String> keywords = toStringList(topic.get("keywords"));
            int max = Math.min(4, keywords.size());
            for (int i = 0; i < max; i++) {
                String kw = keywords.get(i);
                if (kw == null || kw.isBlank()) {
                    continue;
                }
                int weight = (int) (Math.sqrt(Math.max(heat, 0)) * (5 - i));
                wordFreq.merge(kw, weight, Integer::sum);
            }
        }

        List<Map<String, Object>> result = new ArrayList<>();
        wordFreq.forEach((k, v) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", k);
            row.put("value", v);
            result.add(row);
        });
        result.sort((a, b) -> Integer.compare(toInt(b.get("value")), toInt(a.get("value"))));
        List<Map<String, Object>> limited = result.size() > 200
                ? result.subList(0, 200)
                : result;
        return Result.success(limited);
    }

    /**
     * 话题关系网数据（Intertopic Distance Map）。
     *
     * @return 关系网散点数据
     */
    @GetMapping("/graph")
    public Result<List<Map<String, Object>>> getTopicGraph() {
        Query query = buildTopicQueryByLatestTask(50);
        List<Document> topics = mongoTemplate.find(query, Document.class, "analyzed_topics");

        List<Map<String, Object>> data = new ArrayList<>();
        for (Document doc : topics) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", objectIdToString(doc.get("_id")));
            row.put("name", defaultTopicName(doc));
            row.put("x", toDouble(doc.get("x")));
            row.put("y", toDouble(doc.get("y")));
            row.put("value", toInt(doc.get("total_heat")));
            row.put("sentiment", round(toDouble(doc.get("avg_sentiment")), 4));
            List<String> keywords = toStringList(doc.get("keywords"));
            row.put("keywords", keywords.size() > 5 ? keywords.subList(0, 5) : keywords);
            data.add(row);
        }
        return Result.success(data);
    }

    /**
     * 话题详情（热点排行榜-分析）。
     *
     * @param topicId 话题 ID
     * @return 详情对象
     */
    @GetMapping("/topic/{topicId}")
    public Result<Map<String, Object>> getTopicDetail(@PathVariable String topicId) {
        if (!ObjectId.isValid(topicId)) {
            return Result.error(400, "无效的话题ID");
        }

        ObjectId oid = new ObjectId(topicId);
        Document topicDoc = mongoTemplate.findById(oid, Document.class, "analyzed_topics");
        if (topicDoc == null) {
            return Result.error(400, "话题不存在");
        }

        // Step 1: 趋势数据
        Query trendQuery = Query.query(Criteria.where("topic_ref_id").is(oid)).with(Sort.by(Sort.Direction.ASC, "time_bucket"));
        List<Document> trends = mongoTemplate.find(trendQuery, Document.class, "topic_trends");
        List<String> dates = new ArrayList<>();
        List<Integer> values = new ArrayList<>();
        for (Document t : trends) {
            dates.add(String.valueOf(t.get("time_bucket")));
            values.add(toInt(t.get("heat_value")));
        }

        // Step 2: 取该话题帖子样本（按点赞降序）
        Query postQuery = Query.query(Criteria.where("topic_ref_id").is(oid))
                .with(Sort.by(Sort.Direction.DESC, "metrics.likes"))
                .limit(100);
        postQuery.fields()
                .include("content")
                .include("publish_time")
                .include("metrics")
                .include("sentiment_score")
                .include("platform")
                .include("author_info")
                .include("keywords");
        List<Document> posts = mongoTemplate.find(postQuery, Document.class, "social_posts");

        Map<String, Integer> sentimentDistCounter = new HashMap<>();
        sentimentDistCounter.put("positive", 0);
        sentimentDistCounter.put("neutral", 0);
        sentimentDistCounter.put("negative", 0);

        List<String> allKeywords = new ArrayList<>();
        for (Document p : posts) {
            double score = toDouble(p.get("sentiment_score"));
            if (score > 0.3) {
                sentimentDistCounter.merge("positive", 1, Integer::sum);
            } else if (score < -0.3) {
                sentimentDistCounter.merge("negative", 1, Integer::sum);
            } else {
                sentimentDistCounter.merge("neutral", 1, Integer::sum);
            }
            allKeywords.addAll(toStringList(p.get("keywords")));
        }

        // Step 3: 词云（优先帖子关键词，兜底话题关键词）
        List<Map.Entry<String, Integer>> topKeywordCounts = topCounts(allKeywords, 30);
        List<Map<String, Object>> wordCloud = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : topKeywordCounts) {
            String kw = entry.getKey();
            if (kw == null || kw.isBlank() || kw.length() <= 1 || kw.chars().allMatch(Character::isDigit)) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", kw);
            row.put("value", entry.getValue());
            wordCloud.add(row);
        }
        if (wordCloud.isEmpty()) {
            List<String> topicKeywords = toStringList(topicDoc.get("keywords"));
            for (int i = 0; i < topicKeywords.size(); i++) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("name", topicKeywords.get(i));
                row.put("value", Math.max(10, 100 - i * 5));
                wordCloud.add(row);
            }
        }

        // Step 4: recent posts（点赞排序后前5）
        List<Map<String, Object>> recentPosts = new ArrayList<>();
        int limit = Math.min(5, posts.size());
        for (int i = 0; i < limit; i++) {
            Document p = posts.get(i);
            Document metrics = p.get("metrics", Document.class) == null ? new Document() : p.get("metrics", Document.class);
            Document author = p.get("author_info", Document.class) == null ? new Document() : p.get("author_info", Document.class);

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("time", formatDateTime(toDate(p.get("publish_time"))));
            item.put("platform", String.valueOf(p.getOrDefault("platform", "unknown")));
            item.put("author", String.valueOf(author.getOrDefault("nickname", "用户")));
            String content = String.valueOf(p.getOrDefault("content", ""));
            item.put("content", content.length() > 40 ? content.substring(0, 40) + "..." : content);
            item.put("likes", toInt(metrics.get("likes")));
            recentPosts.add(item);
        }

        // Step 5: 传播路径（最早 + 最热视频）
        List<Map<String, Object>> propagationTimeline = new ArrayList<>();
        List<Document> sortedByTime = new ArrayList<>(posts);
        sortedByTime.sort(Comparator.comparing(p -> {
            Date d = toDate(p.get("publish_time"));
            return d == null ? new Date(0) : d;
        }));
        Document firstPost = sortedByTime.isEmpty() ? null : sortedByTime.get(0);
        Document topPost = posts.isEmpty() ? null : posts.get(0);
        if (firstPost != null) {
            propagationTimeline.add(timelineEvent(firstPost, "start", "话题初现： "));
        }
        if (topPost != null && firstPost != null && !Objects.equals(firstPost.get("_id"), topPost.get("_id"))) {
            propagationTimeline.add(timelineEvent(topPost, "peak", "舆论引爆： "));
        }

        // Step 6: 演化数据
        Map<String, Object> evolutionData = null;
        if (posts.size() > 10) {
            int total = posts.size();
            int p1 = (int) (total * 0.3);
            int p2 = (int) (total * 0.7);
            List<Document> stage1 = posts.subList(0, Math.max(0, p1));
            List<Document> stage2 = posts.subList(Math.max(0, p1), Math.max(p1, p2));
            List<Document> stage3 = posts.subList(Math.max(0, p2), total);

            List<String> topKeywords = topKeywordCounts.stream().map(Map.Entry::getKey).filter(Objects::nonNull).limit(5).toList();
            if (topKeywords.isEmpty()) {
                List<String> topicKeywords = toStringList(topicDoc.get("keywords"));
                topKeywords = topicKeywords.size() > 5 ? topicKeywords.subList(0, 5) : topicKeywords;
            }

            List<Map<String, Object>> stages = new ArrayList<>();
            stages.add(stageStat("起步期", stage1, topKeywords));
            stages.add(stageStat("爆发期", stage2, topKeywords));
            stages.add(stageStat("长尾期", stage3, topKeywords));

            evolutionData = new LinkedHashMap<>();
            evolutionData.put("stages", stages);
            evolutionData.put("keywords", topKeywords);
        }

        // Step 7: 组装结果
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", objectIdToString(topicDoc.get("_id")));
        data.put("topic", defaultTopicName(topicDoc));
        data.put("hotScore", toInt(topicDoc.get("total_heat")));
        data.put("sentimentScore", mapSentimentToStars(toDouble(topicDoc.get("avg_sentiment"))));
        data.put("firstOccurTime", formatDateTime(toDate(topicDoc.get("first_occur_time"))));

        Map<String, Object> trendData = new LinkedHashMap<>();
        trendData.put("dates", dates);
        trendData.put("values", values);
        data.put("trendData", trendData);

        List<Map<String, Object>> sentimentDist = new ArrayList<>();
        sentimentDist.add(namedValue("正面", sentimentDistCounter.getOrDefault("positive", 0)));
        sentimentDist.add(namedValue("中性", sentimentDistCounter.getOrDefault("neutral", 0)));
        sentimentDist.add(namedValue("负面", sentimentDistCounter.getOrDefault("negative", 0)));
        data.put("sentimentDist", sentimentDist);

        data.put("wordCloud", wordCloud);
        data.put("recentPosts", recentPosts);
        data.put("propagationTimeline", propagationTimeline);
        data.put("evolutionData", evolutionData);

        return Result.success(data);
    }

    private List<Map<String, Object>> loadHotTopicsFromCache() {
        try {
            Object cached = redisTemplate.opsForValue().get(hotTopicsCacheKey);
            if (cached == null) {
                return Collections.emptyList();
            }
            if (cached instanceof List<?> rawList) {
                List<Map<String, Object>> result = new ArrayList<>();
                for (Object item : rawList) {
                    if (item instanceof Map<?, ?> rawMap) {
                        Map<String, Object> normalized = new LinkedHashMap<>();
                        rawMap.forEach((k, v) -> normalized.put(String.valueOf(k), v));
                        if (!String.valueOf(normalized.getOrDefault("id", "")).isBlank()) {
                            result.add(normalized);
                        }
                    } else {
                        result.clear();
                        break;
                    }
                }
                if (!result.isEmpty()) {
                    return result;
                }
            }
            return objectMapper.convertValue(cached, new TypeReference<List<Map<String, Object>>>() {
            });
        } catch (Exception ex) {
            log.warn("Failed to load hot topics cache", ex);
            return Collections.emptyList();
        }
    }

    private List<Map<String, Object>> queryHotTopicsFromMongo() {
        Query query = buildTopicQueryByLatestTask(50);
        List<Document> docs = mongoTemplate.find(query, Document.class, "analyzed_topics");

        List<Map<String, Object>> topics = new ArrayList<>();
        for (Document doc : docs) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", objectIdToString(doc.get("_id")));
            row.put("topic", defaultTopicName(doc));
            row.put("hotScore", toInt(doc.get("total_heat")));
            row.put("sentiment", round(toDouble(doc.get("avg_sentiment")), 2));
            row.put("isNew", toBool(doc.get("is_burst")));
            row.put("isExplosive", toInt(doc.get("total_heat")) > 4000);
            row.put("keywords", toStringList(doc.get("keywords")));
            topics.add(row);
        }
        return topics;
    }

    private Query buildTopicQueryByLatestTask(int limit) {
        Query query = new Query().with(Sort.by(Sort.Direction.DESC, "total_heat")).limit(limit);
        String latestTaskId = resolveLatestTaskId();
        if (hasTopicsForTask(latestTaskId)) {
            query.addCriteria(Criteria.where("task_id").is(latestTaskId));
        }
        return query;
    }

    private String resolveLatestTaskId() {
        Query query = new Query().with(Sort.by(Sort.Direction.DESC, "create_time")).limit(1);
        query.fields().include("_id");
        Document taskDoc = mongoTemplate.findOne(query, Document.class, "crawler_tasks");
        if (taskDoc == null) {
            return "";
        }
        return objectIdToString(taskDoc.get("_id"));
    }

    private boolean hasTopicsForTask(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            return false;
        }
        Query query = Query.query(Criteria.where("task_id").is(taskId));
        return mongoTemplate.exists(query, "analyzed_topics");
    }

    private boolean hasSocialPostsForTask(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            return false;
        }
        Query query = Query.query(Criteria.where("task_id").is(taskId));
        return mongoTemplate.exists(query, "social_posts");
    }

    private Map<String, Object> statItem(String title, String value, String icon, String type, double trend) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("title", title);
        row.put("value", value);
        row.put("icon", icon);
        row.put("type", type);
        row.put("trend", trend);
        return row;
    }

    private Map<String, Object> namedValue(String name, int value) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("name", name);
        row.put("value", value);
        return row;
    }

    private List<Map.Entry<String, Integer>> topCounts(List<String> values, int limit) {
        Map<String, Integer> counter = new HashMap<>();
        for (String value : values) {
            if (value == null || value.isBlank()) {
                continue;
            }
            counter.merge(value, 1, Integer::sum);
        }
        List<Map.Entry<String, Integer>> list = new ArrayList<>(counter.entrySet());
        list.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));
        return list.size() > limit ? list.subList(0, limit) : list;
    }

    private Map<String, Object> timelineEvent(Document post, String type, String prefix) {
        Document author = post.get("author_info", Document.class) == null ? new Document() : post.get("author_info", Document.class);
        String content = String.valueOf(post.getOrDefault("content", ""));
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("timestamp", formatDateTime(toDate(post.get("publish_time"))));
        row.put("content", prefix + (content.length() > 30 ? content.substring(0, 30) + "..." : content));
        row.put("author", String.valueOf(author.getOrDefault("nickname", "用户")));
        row.put("platform", String.valueOf(post.getOrDefault("platform", "unknown")));
        row.put("type", type);
        return row;
    }

    private Map<String, Object> stageStat(String stageName, List<Document> stagePosts, List<String> keywords) {
        StringBuilder textBuilder = new StringBuilder();
        for (Document p : stagePosts) {
            textBuilder.append(String.valueOf(p.getOrDefault("content", ""))).append(' ');
        }
        String text = textBuilder.toString();

        Map<String, Object> row = new LinkedHashMap<>();
        row.put("name", stageName);
        for (String kw : keywords) {
            if (kw == null || kw.isBlank()) {
                row.put(kw, 0);
                continue;
            }
            row.put(kw, countOccurrences(text, kw));
        }
        return row;
    }

    private int countOccurrences(String text, String keyword) {
        if (text == null || keyword == null || keyword.isBlank()) {
            return 0;
        }
        int count = 0;
        int index = 0;
        while ((index = text.indexOf(keyword, index)) >= 0) {
            count++;
            index += keyword.length();
        }
        return count;
    }

    private String defaultTopicName(Document doc) {
        String name = doc.getString("name");
        if (name != null && !name.isBlank()) {
            return name;
        }
        List<String> keywords = toStringList(doc.get("keywords"));
        if (keywords.isEmpty()) {
            return "Untitled Topic";
        }
        String title = String.join(" ", keywords.subList(0, Math.min(3, keywords.size()))).trim();
        return title.isBlank() ? "Untitled Topic" : title;
    }

    private String objectIdToString(Object id) {
        if (id == null) {
            return "";
        }
        if (id instanceof ObjectId objectId) {
            return objectId.toHexString();
        }
        return String.valueOf(id);
    }

    private List<String> toStringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return new ArrayList<>();
        }
        List<String> result = new ArrayList<>();
        for (Object item : list) {
            if (item != null) {
                String text = String.valueOf(item).trim();
                if (!text.isBlank()) {
                    result.add(text);
                }
            }
        }
        return result;
    }

    private Date toDate(Object value) {
        if (value instanceof Date d) {
            return d;
        }
        return null;
    }

    private String formatDateTime(Date date) {
        if (date == null) {
            return "-";
        }
        return LocalDateTime.ofInstant(date.toInstant(), ZONE_ID).format(DT_MINUTE_FMT);
    }

    private int toInt(Object value) {
        if (value instanceof Number n) {
            return n.intValue();
        }
        if (value instanceof String s) {
            try {
                return (int) Double.parseDouble(s);
            } catch (Exception ignore) {
                return 0;
            }
        }
        return 0;
    }

    private double toDouble(Object value) {
        if (value instanceof Number n) {
            return n.doubleValue();
        }
        if (value instanceof String s) {
            try {
                return Double.parseDouble(s);
            } catch (Exception ignore) {
                return 0.0;
            }
        }
        return 0.0;
    }

    private boolean toBool(Object value) {
        if (value instanceof Boolean b) {
            return b;
        }
        if (value instanceof String s) {
            return Boolean.parseBoolean(s);
        }
        return false;
    }

    private double round(double val, int digits) {
        double scale = Math.pow(10, digits);
        return Math.round(val * scale) / scale;
    }

    private int mapSentimentToStars(double score) {
        if (score >= 0.6) {
            return 5;
        }
        if (score >= 0.2) {
            return 4;
        }
        if (score >= -0.2) {
            return 3;
        }
        if (score >= -0.6) {
            return 2;
        }
        return 1;
    }
}
