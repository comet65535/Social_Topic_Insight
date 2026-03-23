package com.common.VO;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import java.util.Date;

/**
 * 任务展示 VO。
 */
@Data
public class TaskVO {
    /** 任务 ID。 */
    private String id;
    /** 任务名称。 */
    private String name;
    /** 任务状态。 */
    private String status;
    /** 任务日志。 */
    private String log;

    /** 兼容前端 prop=\"create_time\" 的字段命名。 */
    @JsonProperty("create_time")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date createTime;
}
