package com.common.DTO;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 聚类完成回调消息 DTO（Python Worker -> Java）。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ClusterDoneMessage {

    /** 已完成聚类的任务 ID。 */
    private String taskId;
}
