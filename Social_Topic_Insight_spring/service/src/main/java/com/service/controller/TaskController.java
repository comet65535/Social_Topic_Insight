package com.service.controller;

import com.common.DTO.TaskCreateDTO;
import com.common.VO.TaskVO;
import com.common.entity.Task;
import com.common.result.Result;
import com.service.service.TaskService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 任务管理控制器。
 * <p>
 * 对外提供任务创建、查询、删除接口，
 * 控制层仅负责协议编排，核心业务由 {@link TaskService} 执行。
 */
@CrossOrigin // 允许前端跨域访问任务接口
@RestController // 声明为 REST 控制器，返回值自动序列化为 JSON
@RequiredArgsConstructor
@RequestMapping("/api/tasks") // 统一任务接口前缀
public class TaskController {

    private final TaskService taskService;

    /**
     * 查询最近任务列表。
     *
     * @return 最近任务列表（默认最多 50 条）
     */
    @GetMapping
    public Result<List<TaskVO>> getTasks() {
        return Result.success(taskService.listRecentTasks(50));
    }

    /**
     * 创建新任务。
     *
     * @param dto 任务创建请求体
     * @return 新建任务的任务 ID 与状态
     */
    @PostMapping
    public Result<Map<String, String>> createTask(@RequestBody TaskCreateDTO dto) {
        Task created = taskService.createTask(dto);
        return Result.success(Map.of("taskId", created.getId(), "status", created.getStatus()));
    }

    /**
     * 删除任务。
     *
     * @param id 任务 ID
     * @return 删除结果
     */
    @DeleteMapping("/{id}")
    public Result<?> deleteTask(@PathVariable String id) {
        taskService.deleteTask(id);
        return Result.success("Deleted");
    }
}
