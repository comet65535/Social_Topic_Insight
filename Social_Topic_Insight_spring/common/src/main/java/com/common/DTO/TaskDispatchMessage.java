package com.common.DTO;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Date;
import java.util.List;

/**
 * 任务下发消息 DTO（Java -> Python Worker）。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TaskDispatchMessage {

    /** 任务 ID。 */
    private String taskId;

    /** 任务名称。 */
    private String name;

    /** 采集平台列表。 */
    private List<String> platforms;

    /** 任务模式（hot_list / prediction）。 */
    private String mode;

    /** 关键词列表。 */
    private List<String> keywords;

    /** 任务创建时间。 */
    private Date createTime;
}
