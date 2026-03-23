package com.service.service;

import com.common.DTO.ClusterDoneMessage;
import com.common.VO.HotTopicVO;
import com.common.entity.Task;
import com.common.entity.Topic;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.service.config.RabbitConfig;
import jakarta.annotation.Resource;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.bson.types.ObjectId;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.util.CollectionUtils;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

/**
 * 话题摘要与缓存预热服务。
 * <p>
 * 该服务在收到 Python Worker 的 cluster.done 回调后执行：
 * 1. 查询待命名话题；
 * 2. 并发调用 Spring AI 生成标题；
 * 3. 批量写回 Mongo；
 * 4. 预热 Redis 热点缓存；
 * 5. 更新任务状态并释放分布式锁。
 */
@Slf4j
@Service // 注入 Spring 容器，负责 cluster.done 回调后的摘要与缓存预热
@RequiredArgsConstructor
public class LlmSummaryService {

    private static final String PROMPT_TEMPLATE = """
            Please summarize the following social posts into one concise news-style title (within 15 Chinese characters):
            %s
            Requirement: return title only, no prefix and no explanation.
            """;

    private final MongoTemplate mongoTemplate;
    private final ChatClient chatClient;
    private final RedisTemplate<String, Object> redisTemplate;
    private final TaskService taskService;
    private final RestClient.Builder restClientBuilder;
    private final ObjectMapper objectMapper;

    @Resource(name = "llmSummaryExecutor")
    private Executor llmSummaryExecutor;

    @Value("${topic.cache.hot-topics-key:dashboard:hot_topics:top50}")
    private String hotTopicsCacheKey;

    @Value("${topic.cache.hot-topics-ttl-minutes:10}")
    private long hotTopicsCacheTtlMinutes;

    @Value("${spring.ai.openai.base-url}")
    private String openAiBaseUrl;

    @Value("${spring.ai.openai.api-key}")
    private String openAiApiKey;

    @Value("${spring.ai.openai.chat.options.model:deepseek-chat}")
    private String openAiModel;

    @Value("${spring.ai.openai.chat.options.temperature:0.1}")
    private double openAiTemperature;

    /**
     * 监听 Python Worker 发出的聚类完成事件。
     *
     * @param message MQ 回调消息（包含 taskId）
     */
    @RabbitListener(queues = RabbitConfig.CLUSTER_DONE_QUEUE) // 订阅 cluster.done.queue，消费聚类完成事件
    public void onClusterDone(ClusterDoneMessage message) {
        if (message == null || !StringUtils.hasText(message.getTaskId())) {
            log.warn("Received invalid cluster.done message: {}", message);
            return;
        }

        // Step 1: 读取并清洗 taskId
        String taskId = message.getTaskId().trim();
        log.info("Received cluster.done callback, taskId={}", taskId);

        try {
            // Step 2: 查询任务（用于后续释放锁）
            Task task = taskService.findById(taskId).orElse(null);
            // Step 3: 拉取本任务 Top50 话题并统一执行命名（避免历史关键字标题残留）
            List<Topic> targetTopics = queryTopicsForSummary(taskId);

            if (!targetTopics.isEmpty()) {
                // Step 4: 并发调用 LLM 生成标题，并回写 Mongo
                summarizeTopicsConcurrently(targetTopics);
            } else {
                log.info("No topics found for summary, taskId={}", taskId);
            }

            // Step 5: 预热热点缓存，提升 hot-topics 接口首屏性能
            refreshHotTopicsCache();

            if (task != null) {
                // Step 6: 任务完成后释放 Redisson 锁
                taskService.releaseTaskLock(task.getMode(), task.getName());
            }
            // Step 7: 标记任务完成
            taskService.markTaskCompleted(taskId, "LLM summary finished and cache warmed");
        } catch (Exception ex) {
            log.error("LLM summary pipeline failed, taskId={}", taskId, ex);
            taskService.markTaskFailed(taskId, "LLM summary failed: " + ex.getMessage());
            taskService.findById(taskId)
                    .ifPresent(task -> taskService.releaseTaskLock(task.getMode(), task.getName()));
        }
    }

    /**
     * 查询需要命名的目标话题。
     *
     * @param taskId 当前任务 ID
     * @return 话题列表，最多 50 条
     */
    private List<Topic> queryTopicsForSummary(String taskId) {
        Query queryByTask = new Query(Criteria.where("task_id").is(taskId))
                .with(Sort.by(Sort.Direction.DESC, "total_heat"))
                .limit(50);

        // 优先查询当前任务产生的话题
        List<Topic> topics = mongoTemplate.find(queryByTask, Topic.class);
        if (!CollectionUtils.isEmpty(topics)) {
            return topics;
        }

        // 兜底：如果当前任务没有数据，则从全局热点中拿 Top 50
        Query fallbackQuery = new Query()
                .with(Sort.by(Sort.Direction.DESC, "total_heat"))
                .limit(50);
        return mongoTemplate.find(fallbackQuery, Topic.class);
    }

    /**
     * 并发生成话题标题并批量回写。
     *
     * @param topics 待处理话题
     */
    private void summarizeTopicsConcurrently(List<Topic> topics) {
        // Step 1: 为每个 topic 提交异步摘要任务
        List<CompletableFuture<Topic>> futures = topics.stream()
                .map(topic -> CompletableFuture.supplyAsync(() -> {
                    String title = buildTopicTitle(topic);
                    topic.setName(title);
                    return topic;
                }, llmSummaryExecutor))
                .toList();

        // Step 2: 等待全部摘要任务完成
        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

        // Step 3: 批量更新 Mongo，减少网络往返开销
        List<Topic> summarizedTopics = futures.stream().map(CompletableFuture::join).toList();
        bulkUpdateTopicNames(summarizedTopics);
    }

    /**
     * 批量回写话题名称。
     *
     * @param summarizedTopics 已生成标题的话题列表
     */
    private void bulkUpdateTopicNames(List<Topic> summarizedTopics) {
        BulkOperations bulkOperations = mongoTemplate.bulkOps(BulkOperations.BulkMode.UNORDERED, Topic.class);
        summarizedTopics.forEach(topic -> {
            Query query = buildTopicIdQuery(topic.getId());
            if (query != null) {
                bulkOperations.updateOne(query, new Update().set("name", topic.getName()));
            }
        });
        bulkOperations.execute();
    }

    /**
     * 构造按 topicId 查询的 Query。
     *
     * @param topicId 话题 ID
     * @return Mongo 查询对象；若 ID 非法返回 null
     */
    private Query buildTopicIdQuery(String topicId) {
        if (!StringUtils.hasText(topicId)) {
            return null;
        }
        if (ObjectId.isValid(topicId)) {
            return Query.query(Criteria.where("_id").is(new ObjectId(topicId)));
        }
        return Query.query(Criteria.where("_id").is(topicId));
    }

    /**
     * 生成单个话题标题（优先 LLM，失败则回退关键词）。
     *
     * @param topic 目标话题
     * @return 标题文本
     */
    private String buildTopicTitle(Topic topic) {
        String docs = renderDocs(topic.getRepDocs(), topic.getKeywords());
        String prompt = PROMPT_TEMPLATE.formatted(docs);

        try {
            String llmTitle = chatClient.prompt(prompt).call().content();
            return sanitizeTitle(llmTitle, topic.getKeywords());
        } catch (Exception ex) {
            log.warn("SpringAI call failed for topicId={}, try raw HTTP fallback. reason={}", topic.getId(), ex.getMessage());
        }

        try {
            String llmTitle = callLlmByHttpCompat(prompt);
            return sanitizeTitle(llmTitle, topic.getKeywords());
        } catch (Exception ex) {
            log.warn("Raw HTTP LLM call failed for topicId={}, fallback by keywords. reason={}", topic.getId(), ex.getMessage());
            return composeFallbackTitle(topic.getName(), topic.getKeywords());
        }
    }

    /**
     * 使用 OpenAI 兼容 HTTP 接口调用 LLM。
     * <p>
     * 该方法专门兜底 content-type 非 application/json 的场景，
     * 将响应体先按 String 读取，再手动解析 JSON。
     *
     * @param prompt 提示词
     * @return LLM 返回标题文本
     */
    private String callLlmByHttpCompat(String prompt) {
        String baseUrl = openAiBaseUrl == null ? "" : openAiBaseUrl.trim();
        if (!StringUtils.hasText(baseUrl)) {
            throw new IllegalStateException("spring.ai.openai.base-url is empty");
        }
        if (baseUrl.endsWith("/")) {
            baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
        }

        RestClient client = restClientBuilder
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + openAiApiKey)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();

        Map<String, Object> request = Map.of(
                "model", openAiModel,
                "messages", List.of(Map.of("role", "user", "content", prompt)),
                "temperature", openAiTemperature,
                "stream", false
        );

        String rawBody = client.post()
                .uri("/chat/completions")
                .body(request)
                .retrieve()
                .body(String.class);

        if (!StringUtils.hasText(rawBody)) {
            throw new IllegalStateException("Empty response body from LLM");
        }

        try {
            JsonNode root = objectMapper.readTree(rawBody);
            JsonNode contentNode = root.path("choices").path(0).path("message").path("content");
            String content = contentNode.isMissingNode() ? null : contentNode.asText(null);
            if (!StringUtils.hasText(content)) {
                throw new IllegalStateException("No choices[0].message.content in LLM response");
            }
            return content;
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to parse LLM response: " + ex.getMessage(), ex);
        }
    }

    private String composeFallbackTitle(String currentName, List<String> keywords) {
        if (StringUtils.hasText(currentName)) {
            return currentName.trim();
        }
        return fallbackTitle(keywords);
    }

    /**
     * 将代表文本或关键词渲染为 Prompt 片段。
     *
     * @param repDocs 代表文本
     * @param keywords 关键词
     * @return Prompt 文本片段
     */
    private String renderDocs(List<String> repDocs, List<String> keywords) {
        if (!CollectionUtils.isEmpty(repDocs)) {
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < Math.min(repDocs.size(), 8); i++) {
                String text = repDocs.get(i);
                if (!StringUtils.hasText(text)) {
                    continue;
                }
                builder.append("- ")
                        .append(text.replace("\n", " ").trim())
                        .append("\n");
            }
            if (builder.length() > 0) {
                return builder.toString();
            }
        }
        if (!CollectionUtils.isEmpty(keywords)) {
            return String.join(", ", keywords);
        }
        return "No representative docs";
    }

    /**
     * 清洗并截断 LLM 返回标题。
     *
     * @param rawTitle 原始标题
     * @param keywords 关键词（用于兜底）
     * @return 规范化标题
     */
    private String sanitizeTitle(String rawTitle, List<String> keywords) {
        if (!StringUtils.hasText(rawTitle)) {
            return fallbackTitle(keywords);
        }
        String cleaned = rawTitle
                .replace("\n", "")
                .replace("\r", "")
                .replace("\"", "")
                .trim();
        if (!StringUtils.hasText(cleaned)) {
            return fallbackTitle(keywords);
        }
        int maxChars = 15;
        if (cleaned.length() > maxChars) {
            cleaned = cleaned.substring(0, maxChars);
        }
        return cleaned;
    }

    /**
     * 兜底标题策略：拼接关键词。
     *
     * @param keywords 关键词列表
     * @return 兜底标题
     */
    private String fallbackTitle(List<String> keywords) {
        if (CollectionUtils.isEmpty(keywords)) {
            return "Hot Topic";
        }
        List<String> safeKeywords = new ArrayList<>(keywords);
        safeKeywords.removeIf(keyword -> !StringUtils.hasText(keyword));
        if (safeKeywords.isEmpty()) {
            return "Hot Topic";
        }
        String title = String.join(" ", safeKeywords.subList(0, Math.min(3, safeKeywords.size())));
        return title.length() > 15 ? title.substring(0, 15) : title;
    }

    /**
     * 重新生成热点缓存并写入 Redis。
     *
     * @return 预热后的热点列表
     */
    public List<HotTopicVO> refreshHotTopicsCache() {
        // Step 1: 按热度查询 Mongo Top 50（要求已命名）
        Query query = new Query().with(Sort.by(Sort.Direction.DESC, "total_heat")).limit(50);
        query.addCriteria(Criteria.where("name").ne(null).ne(""));

        String latestTaskId = resolveLatestTaskId();
        if (StringUtils.hasText(latestTaskId)) {
            Query taskScoped = new Query()
                    .addCriteria(Criteria.where("task_id").is(latestTaskId))
                    .addCriteria(Criteria.where("name").ne(null).ne(""))
                    .with(Sort.by(Sort.Direction.DESC, "total_heat"))
                    .limit(50);
            List<Topic> scopedTopics = mongoTemplate.find(taskScoped, Topic.class);
            if (!CollectionUtils.isEmpty(scopedTopics)) {
                List<HotTopicVO> hotTopicVOList = scopedTopics.stream().map(this::toHotTopicVO).toList();
                redisTemplate.opsForValue().set(
                        hotTopicsCacheKey,
                        hotTopicVOList,
                        Duration.ofMinutes(hotTopicsCacheTtlMinutes)
                );
                return hotTopicVOList;
            }
        }

        List<Topic> topics = mongoTemplate.find(query, Topic.class);
        if (CollectionUtils.isEmpty(topics)) {
            redisTemplate.delete(hotTopicsCacheKey);
            return Collections.emptyList();
        }

        // Step 2: Entity 转 VO
        List<HotTopicVO> hotTopicVOList = topics.stream().map(this::toHotTopicVO).toList();
        // Step 3: 写入 Redis 并设置 TTL
        redisTemplate.opsForValue().set(
                hotTopicsCacheKey,
                hotTopicVOList,
                Duration.ofMinutes(hotTopicsCacheTtlMinutes)
        );
        return hotTopicVOList;
    }

    private String resolveLatestTaskId() {
        Query query = new Query().with(Sort.by(Sort.Direction.DESC, "create_time")).limit(1);
        query.fields().include("_id");
        Task latestTask = mongoTemplate.findOne(query, Task.class);
        return latestTask == null ? "" : latestTask.getId();
    }

    /**
     * Topic 转 HotTopicVO。
     *
     * @param topic 话题实体
     * @return 热点话题展示对象
     */
    private HotTopicVO toHotTopicVO(Topic topic) {
        HotTopicVO vo = new HotTopicVO();
        vo.setId(topic.getId());
        vo.setTopic(StringUtils.hasText(topic.getName()) ? topic.getName() : "Untitled Topic");
        vo.setHotScore(topic.getTotalHeat() == null ? 0 : topic.getTotalHeat());
        vo.setSentiment(topic.getAvgSentiment() == null ? 0D : topic.getAvgSentiment());
        vo.setIsNew(Boolean.TRUE.equals(topic.getIsBurst()));
        boolean explosive = (topic.getTotalHeat() != null && topic.getTotalHeat() > 4000)
                || Boolean.TRUE.equals(topic.getIsBurst());
        vo.setIsExplosive(explosive);
        vo.setKeywords(topic.getKeywords());
        return vo;
    }
}
