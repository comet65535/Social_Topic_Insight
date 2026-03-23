package com.common.DTO;

import lombok.Data;
import java.util.Date;
import java.util.List;

/**
 * 创建任务请求 DTO。
 */
@Data
public class TaskCreateDTO {
    /** 任务名称。 */
    private String name;
    /** 平台列表（如 weibo、douyin）。 */
    private List<String> platforms;
    /** 任务模式（hot_list 或 prediction）。 */
    private String mode;
    /** 预测模式下的关键词列表。 */
    private List<String> keywords;
    /** 任务统计起始时间（可选）。 */
    private Date startTime;
    /** 任务统计结束时间（可选）。 */
    private Date endTime;
}
