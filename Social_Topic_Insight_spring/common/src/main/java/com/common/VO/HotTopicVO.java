package com.common.VO;

import lombok.Data;

import java.util.List;

/**
 * 热点话题展示 VO。
 */
@Data
public class HotTopicVO {
    /** 话题 ID。 */
    private String id;
    /** 话题名称。 */
    private String topic;
    /** 热度指数。 */
    private Integer hotScore;
    /** 情感得分。 */
    private Double sentiment;
    /** 是否爆款。 */
    private Boolean isExplosive;
    /** 是否新话题。 */
    private Boolean isNew;
    /** 话题关键词列表。 */
    private List<String> keywords;
}
