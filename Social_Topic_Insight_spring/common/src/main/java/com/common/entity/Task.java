package com.common.entity;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

import java.util.Date;
import java.util.List;

/**
 * 任务实体（Mongo: crawler_tasks）。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "crawler_tasks") // 映射 Mongo 集合 crawler_tasks
public class Task {

    /** Mongo ObjectId（字符串形式）。 */
    @MongoId(targetType = FieldType.OBJECT_ID)
    private String id;

    /** 任务名称。 */
    private String name;

    /** 任务平台列表。 */
    private List<String> platforms;

    /** 任务模式。 */
    private String mode;

    /** 关键词列表（预测模式使用）。 */
    private List<String> keywords;

    /** 任务状态（pending/running/completed/failed）。 */
    private String status;

    /** 实时日志。 */
    private String log;

    /** 创建时间。 */
    @Field("create_time")
    private Date createTime;

    /** 完成时间。 */
    @Field("finished_time")
    private Date finishedTime;
}
