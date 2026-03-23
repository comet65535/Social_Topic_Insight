package com.common.entity;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

import java.util.List;

/**
 * 话题实体（Mongo: analyzed_topics）。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "analyzed_topics") // 映射聚类输出集合
public class Topic {

    /** 话题 ID。 */
    @MongoId(targetType = FieldType.OBJECT_ID)
    private String id;

    /** 话题名称（由 Java 侧 LLM 摘要填充）。 */
    private String name;

    /** 关键词列表。 */
    private List<String> keywords;

    /** 总热度。 */
    @Field("total_heat")
    private Integer totalHeat;

    /** 帖文数量。 */
    @Field("post_count")
    private Integer postCount;

    /** 平均情感分。 */
    @Field("avg_sentiment")
    private Double avgSentiment;

    /** 是否为突发话题。 */
    @Field("is_burst")
    private Boolean isBurst;

    /** 代表性文本。 */
    @Field("rep_docs")
    private List<String> repDocs;

    /** 来源任务 ID。 */
    @Field("task_id")
    private String taskId;
}
