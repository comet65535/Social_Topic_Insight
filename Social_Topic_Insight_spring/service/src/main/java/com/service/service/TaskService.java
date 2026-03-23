package com.service.service;

import com.common.DTO.TaskCreateDTO;
import com.common.DTO.TaskDispatchMessage;
import com.common.VO.TaskVO;
import com.common.entity.Task;
import com.service.config.RabbitConfig;
import com.service.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.bson.types.ObjectId;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.Date;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * 任务调度核心服务。
 * <p>
 * 职责：
 * 1. 校验前端任务入参；
 * 2. 使用 Redisson 做同类任务防刷与幂等保护；
 * 3. 持久化任务到 Mongo；
 * 4. 向 RabbitMQ 下发执行消息；
 * 5. 维护任务状态与锁释放。
 */
@Slf4j
@Service // 注入 Spring 容器，供 Controller 复用核心任务逻辑
@RequiredArgsConstructor
public class TaskService {

    private static final String TASK_LOCK_PREFIX = "lock:task:";

    private final RedissonClient redissonClient;
    private final MongoTemplate mongoTemplate;
    private final RabbitTemplate rabbitTemplate;

    /**
     * 创建并下发任务。
     *
     * @param dto 任务创建请求
     * @return 新创建的任务实体
     */
    public Task createTask(TaskCreateDTO dto) {
        // Step 1: 基础参数校验（空值、模式、平台、关键词）
        validateTaskCreateDto(dto);

        // Step 2: 构建分布式锁 key，粒度 = mode + taskName（同类任务互斥）
        String lockKey = buildTaskLockKey(dto.getMode(), dto.getName());
        RLock lock = redissonClient.getLock(lockKey);
        boolean acquired = false;

        try {
            // Step 3: 尝试立即加锁，锁租约 30 分钟，防止并发重复提交
            acquired = lock.tryLock(0, 30, TimeUnit.MINUTES);
            if (!acquired) {
                throw new BusinessException("Duplicate task is still running", HttpStatus.CONFLICT.value());
            }

            // Step 4: 持久化任务，初始状态设为 pending（等待 Python Worker 消费）
            Task task = Task.builder()
                    .name(dto.getName().trim())
                    .platforms(dto.getPlatforms())
                    .mode(dto.getMode())
                    .keywords(dto.getKeywords())
                    .status("pending")
                    .log("Task created, waiting for Python worker")
                    .createTime(new Date())
                    .build();

            Task savedTask = mongoTemplate.save(task);

            // Step 5: 组装 MQ 消息并投递到 task.exchange
            TaskDispatchMessage message = TaskDispatchMessage.builder()
                    .taskId(savedTask.getId())
                    .name(savedTask.getName())
                    .platforms(savedTask.getPlatforms())
                    .mode(savedTask.getMode())
                    .keywords(savedTask.getKeywords())
                    .createTime(savedTask.getCreateTime())
                    .build();

            rabbitTemplate.convertAndSend(
                    RabbitConfig.TASK_EXCHANGE,
                    RabbitConfig.TASK_ROUTING_KEY,
                    message
            );

            // Step 6: 返回新建任务给控制器
            return savedTask;
        } catch (BusinessException ex) {
            throw ex;
        } catch (Exception ex) {
            // Step 7: 非业务异常，主动释放锁，避免锁残留造成长时间阻塞
            if (acquired) {
                releaseTaskLock(dto.getMode(), dto.getName());
            }
            log.error("Create task failed", ex);
            throw new BusinessException("Task dispatch failed");
        }
    }

    /**
     * 主动释放任务锁。
     * <p>
     * 正常流程由 Java 在收到 cluster.done 后调用；
     * 异常流程在创建失败时也会兜底释放，避免死锁。
     *
     * @param mode 任务模式
     * @param taskName 任务名称
     */
    public void releaseTaskLock(String mode, String taskName) {
        String lockKey = buildTaskLockKey(mode, taskName);
        RLock lock = redissonClient.getLock(lockKey);
        try {
            if (lock.isLocked()) {
                lock.forceUnlock();
            }
        } catch (Exception ex) {
            log.warn("Release task lock failed, key={}", lockKey, ex);
        }
    }

    /**
     * 查询最近任务列表。
     *
     * @param limit 最大返回条数
     * @return 任务视图对象列表
     */
    public List<TaskVO> listRecentTasks(int limit) {
        Query query = new Query().with(Sort.by(Sort.Direction.DESC, "create_time")).limit(limit);
        return mongoTemplate.find(query, Task.class).stream().map(this::toTaskVO).toList();
    }

    /**
     * 删除指定任务。
     *
     * @param id 任务 ID（Mongo ObjectId）
     */
    public void deleteTask(String id) {
        if (!ObjectId.isValid(id)) {
            throw new BusinessException("Invalid task id");
        }
        Query query = Query.query(Criteria.where("_id").is(new ObjectId(id)));
        mongoTemplate.remove(query, Task.class);
    }

    /**
     * 根据任务 ID 查询任务详情。
     *
     * @param taskId 任务 ID
     * @return Optional 任务对象
     */
    public Optional<Task> findById(String taskId) {
        if (!ObjectId.isValid(taskId)) {
            return Optional.empty();
        }
        return Optional.ofNullable(mongoTemplate.findById(taskId, Task.class));
    }

    /**
     * 将任务标记为已完成。
     *
     * @param taskId 任务 ID
     * @param logMessage 完成日志
     */
    public void markTaskCompleted(String taskId, String logMessage) {
        updateTaskStatus(taskId, "completed", logMessage);
    }

    /**
     * 将任务标记为失败。
     *
     * @param taskId 任务 ID
     * @param logMessage 失败日志
     */
    public void markTaskFailed(String taskId, String logMessage) {
        updateTaskStatus(taskId, "failed", logMessage);
    }

    /**
     * 更新任务状态与完成时间。
     *
     * @param taskId 任务 ID
     * @param status 目标状态
     * @param logMessage 日志内容
     */
    private void updateTaskStatus(String taskId, String status, String logMessage) {
        if (!ObjectId.isValid(taskId)) {
            log.warn("Skip update task status, invalid taskId={}", taskId);
            return;
        }
        // Step 1: 依据任务 ID 定位文档
        Query query = Query.query(Criteria.where("_id").is(new ObjectId(taskId)));
        // Step 2: 更新状态、日志、结束时间
        Update update = new Update()
                .set("status", status)
                .set("log", logMessage)
                .set("finished_time", new Date());
        // Step 3: 落库
        mongoTemplate.updateFirst(query, update, Task.class);
    }

    /**
     * Entity -> VO 转换。
     *
     * @param task 任务实体
     * @return 任务展示对象
     */
    private TaskVO toTaskVO(Task task) {
        TaskVO vo = new TaskVO();
        vo.setId(task.getId());
        vo.setName(task.getName());
        vo.setStatus(task.getStatus());
        vo.setLog(task.getLog());
        vo.setCreateTime(task.getCreateTime());
        return vo;
    }

    /**
     * 构建分布式锁 key。
     *
     * @param mode 任务模式
     * @param taskName 任务名称
     * @return 锁 key
     */
    private String buildTaskLockKey(String mode, String taskName) {
        String safeMode = StringUtils.hasText(mode) ? mode.trim().toLowerCase() : "default";
        String safeName = StringUtils.hasText(taskName) ? taskName.trim().toLowerCase() : "unknown";
        return TASK_LOCK_PREFIX + safeMode + ":" + safeName;
    }

    /**
     * 任务创建入参校验。
     *
     * @param dto 创建任务 DTO
     */
    private void validateTaskCreateDto(TaskCreateDTO dto) {
        if (dto == null) {
            throw new BusinessException("Request body is required");
        }
        if (!StringUtils.hasText(dto.getName())) {
            throw new BusinessException("Task name is required");
        }
        if (!StringUtils.hasText(dto.getMode())) {
            throw new BusinessException("Task mode is required");
        }
        if (dto.getPlatforms() == null || dto.getPlatforms().isEmpty()) {
            throw new BusinessException("At least one platform is required");
        }
        if ("prediction".equalsIgnoreCase(dto.getMode())
                && (dto.getKeywords() == null || dto.getKeywords().isEmpty())) {
            throw new BusinessException("Prediction mode requires keywords");
        }
        if (dto.getKeywords() != null) {
            dto.setKeywords(dto.getKeywords().stream()
                    .filter(Objects::nonNull)
                    .map(String::trim)
                    .filter(StringUtils::hasText)
                    .toList());
        }
    }
}
