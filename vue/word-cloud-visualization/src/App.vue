<template>
  <div class="app-layout">
    <!-- 动态背景层 -->
    <div class="ambient-bg"></div>

    <!-- 侧边栏 (玻璃态) -->
    <div class="sidebar glass-panel">
      <div class="logo-container">
        <div class="logo-icon floating-anim">
          <el-icon :size="28" color="#fff"><Share /></el-icon>
        </div>
        <span class="logo-text">Topic Insight</span>
      </div>
      
      <el-menu
        :default-active="currentView"
        class="sidebar-menu no-border"
        background-color="transparent"
        text-color="rgba(255,255,255,0.7)"
        active-text-color="#fff"
        :unique-opened="true"
      >
        <el-menu-item index="dashboard" @click="changeView('dashboard')">
          <el-icon><Odometer /></el-icon>
          <span>总览仪表盘</span>
        </el-menu-item>

        <el-sub-menu index="1">
          <template #title>
            <el-icon><DataLine /></el-icon>
            <span>深度分析</span>
          </template>
          <el-menu-item index="hot-topics" @click="changeView('hot-topics')">热点排行榜</el-menu-item>
          <el-menu-item index="keywords" @click="changeView('keywords')">词云透视</el-menu-item>
          <el-menu-item index="graph" @click="changeView('graph')">话题关系网</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="2">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="task" @click="changeView('task')">任务调度</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </div>

    <!-- 主内容区 -->
    <div class="main-container">
      <!-- 顶部 Header (悬浮玻璃) -->
      <header class="header glass-panel">
        <div class="breadcrumb">
          <h2 class="page-title">{{ getPageTitle() }}</h2>
        </div>
        <div class="header-actions">
          <div class="action-item">
             <el-badge :value="5" type="danger" class="notification-badge">
              <el-button circle class="icon-btn-glass">
                <el-icon :size="18"><Bell /></el-icon>
              </el-button>
            </el-badge>
          </div>
          <div class="user-profile glass-pill">
            <el-avatar :size="32" src="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png" />
            <span class="username">Admin</span>
          </div>
        </div>
      </header>

      <!-- 滚动内容区域 -->
      <main class="content-scroll">
        <!-- 1. 仪表盘 Dashboard -->
        <div v-if="currentView === 'dashboard'" class="fade-in">
          <el-row :gutter="24" class="mb-24">
            <el-col :span="6" v-for="(item, index) in dashboardStats" :key="index">
              <div class="stat-card glass-card hover-lift">
                <div class="stat-icon-wrapper" :class="item.type">
                  <el-icon><component :is="item.icon" /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-title">{{ item.title }}</div>
                  <div class="stat-value">
                    {{ item.value }}
                    <span class="stat-trend" :class="item.trend > 0 ? 'up' : 'down'">
                      <el-icon><component :is="item.trend > 0 ? 'CaretTop' : 'CaretBottom'" /></el-icon>
                      {{ Math.abs(item.trend) }}%
                    </span>
                  </div>
                </div>
              </div>
            </el-col>
          </el-row>

          <el-row :gutter="24">
            <el-col :span="16">
              <div class="glass-card padding-20">
                <div class="card-header-styled">
                  <span class="title-text">实时热度监控</span>
                  <div class="decoration-line"></div>
                </div>
                <div ref="dashboardTrendRef" style="height: 350px;"></div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="glass-card padding-20">
                <div class="card-header-styled">
                  <span class="title-text">平台占比</span>
                </div>
                <div ref="platformPieRef" style="height: 350px;"></div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 2. 热点排行榜 Hot Topics -->
        <div v-if="currentView === 'hot-topics'" class="fade-in">
          <div class="glass-card padding-20">
            <div class="flex-between mb-20">
              <span class="card-header-styled">全网热点话题 TOP 50</span>
              <button class="liquid-btn" @click="loadHotTopics">
                <span>刷新榜单</span>
                <div class="liquid"></div>
              </button>
            </div>
            
            <el-table :data="hotTopics" class="glass-table" style="width: 100%">
              <el-table-column type="index" label="排名" width="80" align="center">
                <template #default="scope">
                  <div :class="['rank-hexagon', scope.$index < 3 ? 'top-3' : '']">
                    {{ scope.$index + 1 }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="topic" label="话题名称" min-width="250">
                <template #default="scope">
                  <div class="topic-cell">
                    <span class="topic-text" @click="viewTopicDetail(scope.row.id)">
                      #{{ scope.row.topic }}#
                    </span>
                    <el-tag v-if="scope.row.isExplosive" size="small" class="tag-explosive" effect="dark" round>爆</el-tag>
                    <el-tag v-else-if="scope.row.isNew" size="small" class="tag-new" effect="light" round>新</el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="hotScore" label="热度指数" sortable width="150">
                <template #default="scope">
                  <span class="score-text">{{ scope.row.hotScore }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="sentiment" label="情感倾向" width="240">
                <template #default="scope">
                  <div class="sentiment-wrapper">
                    <el-progress 
                      :percentage="Math.min(100, Math.max(0, Math.round((scope.row.sentiment + 1) * 50)))" 
                      :color="getSentimentColor(scope.row.sentiment)"
                      :show-text="false"
                      :stroke-width="8"
                      class="custom-progress"
                    />
                    <span :style="{ color: getSentimentColor(scope.row.sentiment) }" class="sentiment-val">
                      {{ scope.row.sentiment > 0 ? '+' : '' }}{{ scope.row.sentiment }}
                    </span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" align="center">
                <template #default="scope">
                  <el-button class="action-btn-glass" size="small" @click="viewTopicDetail(scope.row.id)">分析</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- 3. 词云分析 Keywords -->
        <div v-if="currentView === 'keywords'" class="fade-in">
          <!-- 
              style说明: 
              calc(100vh - 140px) 是为了减去顶部Header的高度(约70px)和上下Margin，
              保证卡片刚好铺满剩余屏幕。
          -->
          <div class="glass-card" style="height: calc(100vh - 140px); padding: 0; position: relative;">
            <!-- 图表容器直接 100% 宽高 -->
            <div ref="wordcloudRef" style="width: 100%; height: 100%;"></div>
          </div>
        </div>

        <!-- 4. 话题关系网 Graph -->
        <div v-if="currentView === 'graph'" class="fade-in">
          <div class="glass-card padding-20">
            <span class="card-header-styled">话题共现关系图谱</span>
            <div ref="graphRef" class="chart-container" style="height: 600px; width: 100%;"></div>
          </div>
        </div>

        <!-- 9. 任务管理 Task -->
        <div v-if="currentView === 'task'" class="fade-in">
          <div class="glass-card padding-20">
            <div class="flex-between mb-20">
              <span class="card-header-styled">数据分析任务</span>
              <button class="liquid-btn blue" @click="showCreateTaskDialog = true">
                 <el-icon class="mr-5"><Plus /></el-icon>新建任务
                 <div class="liquid"></div>
              </button>
            </div>
            <el-table :data="tasks" class="glass-table" style="width: 100%">
                <el-table-column prop="id" label="ID" width="220">
                  <template #default="{row}"><span class="mono-text">{{ row.id }}</span></template>
                </el-table-column>
                <el-table-column prop="name" label="任务名称" />
                <el-table-column prop="status" label="状态" width="120">
                  <template #default="scope">
                    <div v-if="scope.row.status === 'running'" class="status-pill running">
                        <div class="pulse-dot"></div> 进行中
                    </div>
                    <div v-else-if="scope.row.status === 'completed'" class="status-pill success">已完成</div>
                    <div v-else class="status-pill error">失败</div>
                  </template>
                </el-table-column>
                <el-table-column prop="log" label="实时日志" show-overflow-tooltip />
                <el-table-column prop="create_time" label="创建时间" width="160" />
                <el-table-column label="操作" width="150">
                  <template #default="scope">
                    <el-button class="text-btn" link type="primary" :disabled="scope.row.status !== 'completed'">查看报告</el-button>
                    <el-popconfirm title="确定删除该记录吗?" @confirm="handleDelete(scope.row)">
                        <template #reference><el-button class="text-btn danger" link>删除</el-button></template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
            </el-table>
          </div>
        </div>
      </main>
    </div>

    <!-- 弹窗：创建任务 -->
    <el-dialog v-model="showCreateTaskDialog" title="创建挖掘任务" width="550px" class="glass-dialog" :modal-class="'glass-modal-mask'">
      <el-form :model="taskForm" label-width="100px" class="glass-form">
        <el-form-item label="任务名称">
          <el-input v-model="taskForm.name" placeholder="例如：春节联欢晚会舆情监控" class="glass-input" />
        </el-form-item>
        <el-form-item label="数据源">
          <el-checkbox-group v-model="taskForm.platforms">
            <el-checkbox label="weibo" border class="glass-checkbox">微博</el-checkbox>
            <el-checkbox label="bilibili" border class="glass-checkbox">B站</el-checkbox>
            <el-checkbox label="douyin" border class="glass-checkbox">抖音</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="任务模式">
          <el-radio-group v-model="taskForm.mode" class="glass-radio">
            <el-radio label="hot_list" border>全网热榜</el-radio>
            <el-radio label="prediction" border>热点预测</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="监控关键词">
          <el-input 
            v-model="taskForm.keywords" 
            :placeholder="taskForm.mode === 'prediction' ? '输入关键词(逗号分隔)' : '热榜模式下无需输入关键词'"
            :disabled="taskForm.mode === 'hot_list'"
            type="textarea"
            :rows="2"
            class="glass-input"
          />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker 
            v-model="taskForm.dateRange" 
            type="daterange" 
            start-placeholder="开始" 
            end-placeholder="结束" 
            style="width: 100%" 
            class="glass-date-picker"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateTaskDialog = false" class="btn-plain">取消</el-button>
        <button class="liquid-btn small" @click="createTask">
          <span>立即启动</span>
          <div class="liquid"></div>
        </button>
      </template>
    </el-dialog>

    <!-- 弹窗：话题详情 -->
    <el-dialog 
      v-model="topicDetailVisible" 
      :title="`话题深度追踪：#${currentTopic.topic}#`" 
      width="85%"
      top="5vh"
      destroy-on-close
      class="glass-dialog wide-dialog"
      :modal-class="'glass-modal-mask'"
    >
      <!-- 顶部关键指标 -->
      <el-row :gutter="20" class="mb-24">
        <el-col :span="6">
          <div class="detail-stat-box glass-panel-inset">
            <div class="label">生命周期起点</div>
            <div class="value time">{{ currentTopic.firstOccurTime || '加载中...' }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="detail-stat-box glass-panel-inset">
            <div class="label">当前热度峰值</div>
            <div class="value heat">{{ currentTopic.hotScore }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="detail-stat-box glass-panel-inset">
            <div class="label">持续时长</div>
            <div class="value">{{ calculateDuration(currentTopic.firstOccurTime) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="detail-stat-box glass-panel-inset">
            <div class="label">情感倾向</div>
            <el-rate 
              v-model="currentTopic.sentimentScore" 
              disabled 
              show-score 
              text-color="#ff9900"
              class="glass-rate"
            />
          </div>
        </el-col>
      </el-row>

      <!-- 中间图表区 -->
      <el-row :gutter="20">
        <el-col :span="16">
          <div class="glass-card padding-20">
            <div class="flex-between mb-10">
              <span class="card-title-sm">热度演化趋势 & 关键事件</span>
              <el-radio-group v-model="trendTimeRange" size="small" @change="fetchTopicTrend" fill="#6366f1">
                <el-radio-button label="week">近一周</el-radio-button>
                <el-radio-button label="month">近一月</el-radio-button>
              </el-radio-group>
            </div>
            <div ref="detailTrendRef" style="height: 350px;"></div>
          </div>
        </el-col>

        <el-col :span="8">
          <div class="glass-card padding-20 mb-20">
            <span class="card-title-sm">核心关联词</span>
            <div ref="detailWordCloudRef" style="height: 180px;"></div>
          </div>
          <div class="glass-card padding-20">
            <span class="card-title-sm">舆论情感分布</span>
            <div ref="detailSentimentRef" style="height: 120px;"></div>
          </div>
        </el-col>
      </el-row>

      <el-row :gutter="20" class="mt-20">
        <!-- 传播路径 -->
        <el-col :span="10">
          <div class="glass-card padding-20" style="height: 380px;">
            <span class="card-title-sm mb-10 block">传播路径 & 关键节点</span>
            <div class="custom-scrollbar" style="height: 320px; overflow-y: auto; padding-right: 10px;">
              <el-timeline>
                <el-timeline-item
                  v-for="(activity, index) in currentTopic.propagationTimeline"
                  :key="index"
                  :type="activity.type === 'start' ? 'primary' : 'danger'"
                  :color="activity.type === 'start' ? '#2979ff' : '#ff4d4f'"
                  :timestamp="activity.timestamp"
                  placement="top"
                >
                  <div class="timeline-glass-card">
                    <h4>
                        <span class="platform-tag" :class="activity.platform">{{ activity.platform }}</span> 
                        @ {{ activity.author }}
                    </h4>
                    <p>{{ activity.content }}</p>
                    <div class="mt-5">
                      <el-tag v-if="activity.type==='start'" size="small" effect="plain">溯源首发</el-tag>
                      <el-tag v-else type="danger" size="small" effect="plain">引爆热点</el-tag>
                    </div>
                  </div>
                </el-timeline-item>
              </el-timeline>
              <div v-if="!currentTopic.propagationTimeline?.length" class="no-data">暂无传播关键节点数据</div>
            </div>
          </div>
        </el-col>

        <!-- 演化趋势 -->
        <el-col :span="14">
          <div class="glass-card padding-20" style="height: 380px;">
            <span class="card-title-sm">话题内容演化 (关键词流变)</span>
            <div ref="evolutionChartRef" style="height: 320px;"></div>
            <div v-if="!currentTopic.evolutionData" class="no-data" style="margin-top: -150px;">暂无演化数据</div>
          </div>
        </el-col>
      </el-row>

      <!-- 底部：最新相关帖子 -->
      <div class="mt-20">
        <div class="section-title-glass">话题溯源 (最新 Top 5)</div>
        <el-table :data="currentTopic.recentPosts" size="small" class="glass-table border-table">
          <el-table-column prop="time" label="发布时间" width="160" />
          <el-table-column prop="platform" label="平台" width="100">
            <template #default="{ row }">
               <span class="platform-badge" :class="row.platform">{{ row.platform }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="author" label="用户" width="120" />
          <el-table-column prop="content" label="内容摘要" show-overflow-tooltip />
          <el-table-column prop="likes" label="点赞" width="100" sortable />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
// 【注：JS 逻辑部分完全保持原样，未做任何修改】
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import { ElMessage } from 'element-plus'
import request from '@/utils/request' 

const currentView = ref('dashboard')
const showCreateTaskDialog = ref(false)
const topicDetailVisible = ref(false)
const selectedPlatform = ref('all')
const trendTimeRange = ref('week')
const detailTrendRef = ref(null)
const detailWordCloudRef = ref(null)
const detailSentimentRef = ref(null)
const evolutionChartRef = ref(null)

const dashboardStats = ref([
  { title: '总帖子数', value: '1,258,040', icon: 'Document', type: 'primary', trend: 12.5 },
  { title: '活跃话题', value: '89', icon: 'ChatLineSquare', type: 'success', trend: 8.2 },
  { title: '突发热点', value: '12', icon: 'Lightning', type: 'warning', trend: -3.1 },
  { title: '负面舆情', value: '5.2%', icon: 'Warning', type: 'danger', trend: 2.1 }
])

const hotTopics = ref([])
const tasks = ref([])
const geoData = ref([])

const taskForm = reactive({ 
  name: '', 
  platforms: ['weibo'], 
  mode: 'hot_list',     
  keywords: '',         
  dateRange: [] 
})

const currentTopic = ref({
  id: '',
  topic: '',
  firstOccurTime: '',
  hotScore: 0,
  sentimentScore: 3.5,
  keywords: [],
  recentPosts: []
})

const dashboardTrendRef = ref(null)
const platformPieRef = ref(null)
const wordcloudRef = ref(null)
const graphRef = ref(null)
const trendRef = ref(null)
const evolutionRef = ref(null)
const geoMapRef = ref(null)
const sentimentPieRef = ref(null)
const sentimentGaugeRef = ref(null)
const sentimentTrendRef = ref(null)

const loadDashboardCharts = async () => {
  if (currentView.value !== 'dashboard') return
  try {
    const res = await request.get('/analysis/dashboard/charts')
    if (dashboardTrendRef.value && res.lineData) {
      const chart = echarts.init(dashboardTrendRef.value)
      chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: res.lineData.x },
        yAxis: { type: 'value' },
        series: [{ 
            name: '实时帖文量', type: 'line', smooth: true, 
            areaStyle: { opacity: 0.2, color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: '#6366f1'}, {offset: 1, color: 'rgba(99,102,241,0)'}]) }, 
            itemStyle: { color: '#6366f1' }, 
            data: res.lineData.y 
        }]
      })
      window.addEventListener('resize', () => chart.resize())
    }
    if (platformPieRef.value && res.pieData) {
      const chart = echarts.init(platformPieRef.value)
      chart.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: '0%' },
        series: [{
            name: '来源平台', type: 'pie', radius: ['40%', '70%'],
            center: ['50%', '45%'],
            itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
            data: res.pieData
        }]
      })
      window.addEventListener('resize', () => chart.resize())
    }
  } catch (e) { console.error("加载图表数据失败", e) }
}

const fetchTasks = async () => {
  try {
    const res = await request.get('/tasks')
    if (Array.isArray(res)) tasks.value = res
    else if (res && res.data) tasks.value = res.data
  } catch (error) { console.error("获取任务列表失败", error) }
}

const createTask = async () => {
  if (!taskForm.name) return ElMessage.warning('请输入任务名称')
  if (taskForm.platforms.length === 0) return ElMessage.warning('请至少选择一个平台')
  const payload = {
    name: taskForm.name,
    platforms: taskForm.platforms,
    mode: taskForm.mode,
    keywords: taskForm.mode === 'prediction' && taskForm.keywords ? taskForm.keywords.split(/[,，]/).map(k => k.trim()).filter(k=>k) : [], 
    startTime: taskForm.dateRange?.[0] || new Date(),
    endTime: taskForm.dateRange?.[1] || new Date(),
    status: 'running',
    progress: 0
  }
  try {
     await request.post('/tasks', payload)
     ElMessage.success('任务已启动，正在后台运行...')
     showCreateTaskDialog.value = false
     fetchTasks() 
   } catch (error) { console.error("请求失败:", error); ElMessage.error('任务创建失败') }
}

const handleDelete = async (row) => {
    try {
        await request.delete(`/tasks/${row.id}`)
        ElMessage.success('删除成功')
        fetchTasks()
    } catch(e) { ElMessage.error('删除失败') }
}

const getPageTitle = () => {
  const map = {
    'dashboard': '总览仪表盘',
    'hot-topics': '热点话题排行榜',
    'keywords': '话题词云透视',
    'graph': '话题关系图谱',
    'task': '分析任务管理'
  }
  return map[currentView.value] || '系统'
}

const getSentimentColor = (val) => {
  if (val >= 0.2) return '#10b981'
  if (val <= -0.2) return '#f43f5e'
  return '#8b5cf6' 
}

const changeView = async (view) => {
  currentView.value = view
  await nextTick()
  initChartsForView(view)
}

const initChartsForView = (view) => {
  if (view === 'dashboard') { initDashboardTrend(); initPlatformPie(); }
  else if (view === 'keywords') { initWordCloud(); }
  else if (view === 'graph') { initGraph(); }
}

const initDashboardTrend = () => {
  if(!dashboardTrendRef.value) return
  const chart = echarts.init(dashboardTrendRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'] },
    yAxis: { type: 'value' },
    series: [
      { name: '全网热度', type: 'line', smooth: true, areaStyle: { opacity: 0.1 }, itemStyle: { color: '#6366f1' }, data: [120, 132, 101, 134, 90, 230, 210] },
      { name: '突发事件', type: 'line', smooth: true, itemStyle: { color: '#f43f5e' }, data: [20, 32, 11, 34, 290, 330, 310] }
    ]
  })
  window.addEventListener('resize', () => chart.resize())
}

const initPlatformPie = () => {
  if(!platformPieRef.value) return
  const chart = echarts.init(platformPieRef.value)
  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: '5%', left: 'center' },
    series: [{
        name: '来源', type: 'pie', radius: ['40%', '70%'],
        itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
        data: [{ value: 1048, name: '微博' }, { value: 735, name: '抖音' }, { value: 580, name: 'Twitter' }, { value: 484, name: '知乎' }]
    }]
  })
  window.addEventListener('resize', () => chart.resize())
}

const initWordCloud = async () => {
  if (!wordcloudRef.value) return
  
  try {
    // 调用后端新接口
    const res = await request.get('/analysis/wordcloud')
    
    const chart = echarts.init(wordcloudRef.value)
    chart.setOption({
      tooltip: { show: true },
      series: [{
        type: 'wordCloud',
        gridSize: 15,
        sizeRange: [14, 70],
        rotationRange: [-45, 90],
        shape: 'circle',
        textStyle: {
          fontFamily: 'sans-serif',
          fontWeight: 'bold',
          color: () => `rgb(${Math.round(Math.random() * 160)}, ${Math.round(Math.random() * 160)}, ${Math.round(Math.random() * 160)})`
        },
        data: res // 直接填入后端返回的 [{name, value}, ...]
      }]
    })
    
    // 响应式
    window.addEventListener('resize', () => chart.resize())
    
  } catch (e) {
    console.error("加载词云失败", e)
  }
}


let chartInstance = null;
let resizeHandler = null;

const initGraph = async () => {
  if (!graphRef.value) return;
  if (chartInstance) { chartInstance.dispose(); chartInstance = null; }
  if (resizeHandler) { window.removeEventListener('resize', resizeHandler); resizeHandler = null; }
  const existingChart = echarts.getInstanceByDom(graphRef.value);
  if (existingChart) existingChart.dispose();

  try {
    const res = await request.get('/analysis/graph'); 
    const values = res.map(item => item.value || 0);
    const maxVal = Math.max(...values);
    const minVal = Math.min(...values);
    const MIN_SIZE = 10; const MAX_SIZE = 70;

    chartInstance = echarts.init(graphRef.value);
    resizeHandler = () => { if (chartInstance) chartInstance.resize(); };
    window.addEventListener('resize', resizeHandler);

    chartInstance.setOption({
      title: { text: 'Intertopic Distance Map', subtext: '话题热度(面积)与语义距离(位置)可视化', left: 'center', top: 20, textStyle: { fontSize: 24, fontWeight: 'bold', color: '#333' } },
      tooltip: {
        trigger: 'item', backgroundColor: 'rgba(255, 255, 255, 0.95)', borderColor: '#ddd', textStyle: { color: '#333' },
        formatter: function (param) {
          const d = param.data;
          const keywords = d.keywords ? d.keywords.join(' | ') : '无';
          return `<div style="min-width: 200px;"><div style="font-size:16px; font-weight:bold; margin-bottom:8px; border-bottom:1px solid #eee; padding-bottom:5px;">${d.name}</div><div style="margin-bottom:4px;">🔥 热度指数: <b style="color:#ff7d00">${d.val}</b></div><div style="margin-bottom:4px;">Mask 情感倾向: <b style="${d.sent>0?'color:#67C23A':'color:#F56C6C'}">${d.sent>0?'正面':'负面'}</b></div><div style="color:#666; font-size:12px; margin-top:8px; line-height:1.4;"><b>关键词:</b><br/>${keywords}</div></div>`;
        }
      },
      xAxis: { show: false, scale: true }, yAxis: { show: false, scale: true },
      grid: { top: 80, bottom: 40, left: 40, right: 40 },
      series: [{
        type: 'scatter',
        symbolSize: function (dataItem) {
          const val = dataItem[2];
          if (maxVal === minVal) return (MIN_SIZE + MAX_SIZE) / 2;
          const ratio = (val - minVal) / (maxVal - minVal);
          return MIN_SIZE + Math.sqrt(ratio) * (MAX_SIZE - MIN_SIZE);
        },
        data: res.map((item, index) => {
          const isPositive = item.sentiment >= 0;
          const fillColor = isPositive ? 'rgba(99, 102, 241, 0.4)' : 'rgba(244, 63, 94, 0.4)';
          const borderColor = isPositive ? '#6366f1' : '#f43f5e';
          return {
            name: item.name, value: [item.x, item.y, item.value], val: item.value, sent: item.sentiment, keywords: item.keywords,
            itemStyle: { color: fillColor, borderColor: borderColor, borderWidth: 2, shadowBlur: 0 }
          };
        }),
        label: { show: false },
        emphasis: {
          focus: 'self', scale: true,
          label: { show: true, formatter: '{b}', position: 'top', color: '#333', fontSize: 14, fontWeight: 'bold', backgroundColor: 'rgba(255,255,255,0.9)', padding: [4, 8], borderRadius: 4, shadowBlur: 5, shadowColor: 'rgba(0,0,0,0.2)' },
          itemStyle: { color: (params) => { return params.data.sent >= 0 ? 'rgba(99, 102, 241, 0.9)' : 'rgba(244, 63, 94, 0.9)'; }, shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' }
        }
      }],
      dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'empty' }, { type: 'inside', yAxisIndex: 0, filterMode: 'empty' }]
    });
  } catch (e) { console.error("加载聚类分布图失败", e); }
};

const loadHotTopics = async () => {
  try {
    const res = await request.get('/analysis/hot-topics')
    if (res && res.length > 0) { hotTopics.value = res; ElMessage.success('热榜数据已刷新') } 
    else { hotTopics.value = []; ElMessage.warning('暂无分析数据，请先创建任务进行抓取') }
  } catch (e) { console.error(e); ElMessage.error('获取热榜失败') }
}

const loadDashboardStats = async () => {
  try {
    const res = await request.get('/analysis/dashboard/stats')
    if (res && res.length >= 3) {
      dashboardStats.value[0].value = res[0].value; dashboardStats.value[0].trend = res[0].trend
      dashboardStats.value[1].value = res[1].value; dashboardStats.value[1].trend = res[1].trend
      dashboardStats.value[3].value = res[2].value; dashboardStats.value[3].trend = res[2].trend
    }
  } catch (e) { console.log("加载统计失败，使用默认数据", e) }
}

const viewTopicDetail = async (id) => {
  topicDetailVisible.value = true
  try {
    const res = await request.get(`/analysis/topic/${id}`)
    if (res) {
      currentTopic.value = res
      currentTopic.value.chartData = { trend: res.trendData, wordCloud: res.wordCloud, sentiment: res.sentimentDist }
      currentTopic.value.propagationTimeline = res.propagationTimeline || []
      currentTopic.value.evolutionData = res.evolutionData || null
    }
  } catch (e) { ElMessage.error('获取话题详情失败'); console.error(e) }
  await nextTick()
  renderDetailCharts()
}

const fetchTopicTrend = async () => { renderDetailCharts() }
const calculateDuration = (t) => t ? '3天' : '-'

const renderDetailCharts = () => {
  const data = currentTopic.value.chartData
  if (!data) return
  if (detailTrendRef.value) { 
      const chart = echarts.init(detailTrendRef.value)
      chart.setOption({
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: data.trend.dates },
          yAxis: { type: 'value' },
          series: [{ type: 'line', smooth: true, areaStyle: { opacity: 0.2 }, data: data.trend.values, itemStyle: { color: '#6366f1' } }] 
      })
  }
  if (detailWordCloudRef.value) { 
      const chart = echarts.init(detailWordCloudRef.value)
      chart.setOption({ 
          series: [{
              type: 'wordCloud', sizeRange: [12, 40], rotationRange: [0, 0], gridSize: 8, layoutAnimation: true,
              textStyle: { fontFamily: 'sans-serif', fontWeight: 'bold', color: () => `rgb(${Math.round(Math.random() * 160)}, ${Math.round(Math.random() * 160)}, ${Math.round(Math.random() * 160)})` },
              data: data.wordCloud
          }] 
      }) 
  }
  if (detailSentimentRef.value) { 
      const chart = echarts.init(detailSentimentRef.value)
      chart.setOption({ 
          tooltip: { trigger: 'item' },
          series: [{
              type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: false, itemStyle: { borderRadius: 5, borderColor: '#fff', borderWidth: 2 },
              label: { show: false }, emphasis: { label: { show: true, fontSize: 12, fontWeight: 'bold' } },
              data: data.sentiment, color: ['#10b981', '#cbd5e1', '#f43f5e']
          }] 
      }) 
  }
  if (evolutionChartRef.value && currentTopic.value.evolutionData) {
    const existChart = echarts.getInstanceByDom(evolutionChartRef.value)
    if (existChart) existChart.dispose()
    const evoData = currentTopic.value.evolutionData
    const chart = echarts.init(evolutionChartRef.value)
    const series = evoData.keywords.map(kw => ({
      name: kw, type: 'line', stack: 'Total', areaStyle: {}, emphasis: { focus: 'series' }, smooth: true,
      data: evoData.stages.map(stage => stage[kw] || 0)
    }))
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: '#6a7985' } } },
      legend: { data: evoData.keywords, top: 0 },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: ['起步期', '爆发期', '长尾期'] },
      yAxis: { type: 'value' },
      series: series,
      color: ['#6366f1', '#8b5cf6', '#d946ef', '#f43f5e', '#f59e0b']
    })
  }
}

let timer = null
onMounted(() => {
  loadDashboardStats(); loadDashboardCharts(); loadHotTopics(); initDashboardTrend(); fetchTasks();
  timer = setInterval(() => { if (currentView.value === 'task') fetchTasks() }, 3000)
})
import { watch } from 'vue'
watch(currentView, (newVal) => {
  if (newVal === 'dashboard') { nextTick(() => { loadDashboardStats(); loadDashboardCharts(); }) }
})
onUnmounted(() => { if(timer) clearInterval(timer) })
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');

/* 全局变量定义 */
:root {
  --primary-color: #6366f1; /* Indigo */
  --secondary-color: #8b5cf6; /* Violet */
  --glass-bg: rgba(255, 255, 255, 0.65);
  --glass-border: rgba(255, 255, 255, 0.4);
  --glass-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
  --text-dark: #1e293b;
  --text-light: #64748b;
  --sidebar-width: 240px;
}

/* 基础布局 */
.app-layout {
  display: flex;
  height: 100vh;
  font-family: 'Inter', sans-serif;
  overflow: hidden;
  position: relative;
  background-color: #eef2ff;
}

/* 动态流光背景 */
.ambient-bg {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  background: 
    radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0, transparent 50%), 
    radial-gradient(at 50% 0%, hsla(225,39%,30%,1) 0, transparent 50%), 
    radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0, transparent 50%);
  background-size: 200% 200%;
  z-index: 0;
  opacity: 0.1; /* 保持浅色基调，深色作为点缀 */
}

/* 侧边栏玻璃态 */
.sidebar {
  width: var(--sidebar-width);
  z-index: 10;
  display: flex;
  flex-direction: column;
  transition: all 0.3s;
  background: rgba(15, 23, 42, 0.95); /* 深色侧边栏 */
  backdrop-filter: blur(20px);
  border-right: 1px solid rgba(255,255,255,0.05);
}

.logo-container {
  height: 80px;
  display: flex;
  align-items: center;
  padding-left: 24px;
  gap: 12px;
}

.floating-anim {
  animation: float 3s ease-in-out infinite;
}

.logo-text {
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* 菜单样式重写 */
:deep(.el-menu) { border-right: none; }
:deep(.el-menu-item), :deep(.el-sub-menu__title) {
  height: 56px;
  margin: 4px 12px;
  border-radius: 12px;
}
:deep(.el-menu-item:hover), :deep(.el-sub-menu__title:hover) {
  background-color: rgba(255,255,255,0.1) !important;
}
:deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%) !important;
  color: #fff !important;
  box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
}

/* 主容器 */
.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

/* 玻璃 Header */
.header {
  height: 70px;
  padding: 0 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255,255,255,0.7);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255,255,255,0.5);
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-dark);
  margin: 0;
}

.header-actions { display: flex; align-items: center; gap: 20px; }
.glass-pill {
  padding: 4px 12px 4px 4px;
  background: rgba(255,255,255,0.5);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 30px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.3s;
}
.glass-pill:hover { background: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
.username { font-weight: 600; font-size: 14px; color: var(--text-dark); }
.icon-btn-glass { background: transparent; border: none; color: var(--text-light); transition: transform 0.2s; }
.icon-btn-glass:hover { transform: scale(1.1); color: var(--primary-color); }

/* 玻璃卡片系统 */
.content-scroll { padding: 32px; overflow-y: auto; }
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  border-radius: 20px;
  transition: transform 0.3s, box-shadow 0.3s;
  overflow: hidden;
}
.hover-lift:hover {
  transform: translateY(-5px);
  box-shadow: 0 15px 40px rgba(31, 38, 135, 0.15);
}
.padding-20 { padding: 24px; margin-bottom: 24px; }
.card-header-styled {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-dark);
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
  z-index: 1;
}
.card-header-styled::before {
  content: '';
  width: 6px;
  height: 24px;
  background: linear-gradient(to bottom, #6366f1, #d946ef);
  border-radius: 3px;
  display: inline-block;
  margin-right: 8px;
}
.card-title-sm { font-size: 15px; font-weight: 600; color: #475569; display: block; margin-bottom: 12px; }

/* 统计卡片特殊样式 */
.stat-card {
  padding: 24px;
  display: flex;
  align-items: center;
  height: 120px;
}
.stat-icon-wrapper {
  width: 64px; height: 64px;
  border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  font-size: 28px;
  margin-right: 20px;
  background: rgba(255,255,255,0.5);
  box-shadow: inset 0 0 20px rgba(255,255,255,0.8);
}
.stat-icon-wrapper.primary { color: #6366f1; background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(99,102,241,0.2)); }
.stat-icon-wrapper.success { color: #10b981; background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(16,185,129,0.2)); }
.stat-icon-wrapper.warning { color: #f59e0b; background: linear-gradient(135deg, rgba(245,158,11,0.1), rgba(245,158,11,0.2)); }
.stat-icon-wrapper.danger { color: #f43f5e; background: linear-gradient(135deg, rgba(244,63,94,0.1), rgba(244,63,94,0.2)); }

.stat-title { font-size: 13px; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-size: 28px; font-weight: 800; color: var(--text-dark); margin-top: 4px; }
.stat-trend { font-size: 13px; margin-left: 8px; font-weight: 600; padding: 2px 6px; border-radius: 6px; }
.stat-trend.up { background: rgba(16,185,129,0.1); color: #10b981; }
.stat-trend.down { background: rgba(244,63,94,0.1); color: #f43f5e; }

/* 液态玻璃按钮 (Liquid Button) - 核心亮点 */
.liquid-btn {
  position: relative;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  padding: 10px 24px;
  background: #6366f1;
  color: white;
  font-weight: 600;
  border-radius: 30px;
  border: none;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
  font-size: 14px;
}
.liquid-btn span { position: relative; z-index: 2; display: flex; align-items: center; gap: 6px; }
.liquid-btn .liquid {
  position: absolute;
  top: -80px; left: 0; width: 200px; height: 200px;
  background: rgba(255,255,255,0.25);
  border-radius: 40%;
  transition: .4s;
  animation: wave 10s infinite linear;
  z-index: 1;
}
.liquid-btn:hover .liquid { top: -60px; }
.liquid-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(99, 102, 241, 0.5); }
.liquid-btn.blue { background: #3b82f6; }
.liquid-btn.small { padding: 8px 20px; font-size: 13px; }

/* 表格美化 */
.glass-table {
  background: transparent !important;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255,255,255,0.3);
  --el-table-row-hover-bg-color: rgba(255,255,255,0.4);
  --el-table-border-color: rgba(255,255,255,0.2);
}
:deep(.el-table__inner-wrapper::before) { display: none; } /* 去掉底部线 */
:deep(.el-table th.el-table__cell) {
  color: var(--text-light);
  font-weight: 600;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}
:deep(.el-table td.el-table__cell) { border-bottom: 1px solid rgba(0,0,0,0.03); }

/* 六边形排名 */
.rank-hexagon {
  width: 32px; height: 32px;
  margin: 0 auto;
  line-height: 32px;
  background: rgba(0,0,0,0.05);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  font-weight: bold;
  color: #64748b;
}
.rank-hexagon.top-3 {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: #fff;
  box-shadow: 0 4px 10px rgba(245, 158, 11, 0.4);
}

.topic-text { font-weight: 600; color: #1e293b; cursor: pointer; transition: color 0.2s; }
.topic-text:hover { color: #6366f1; }
.tag-explosive { background: linear-gradient(to right, #f43f5e, #e11d48); border: none; color: white; margin-left: 8px; }
.tag-new { background: linear-gradient(to right, #10b981, #059669); border: none; color: white; margin-left: 8px; }
.score-text { font-family: 'Inter', monospace; font-weight: 700; color: #f59e0b; }

/* 状态胶囊 */
.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 20px;
  font-size: 12px; font-weight: 600;
}
.status-pill.running { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.status-pill.success { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.status-pill.error { background: rgba(244, 63, 94, 0.1); color: #f43f5e; }
.pulse-dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: pulse 1.5s infinite; }

/* 详情弹窗样式 */
:deep(.glass-dialog) {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(24px);
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255,255,255,0.6);
}
:deep(.el-dialog__header) {
  border-bottom: 1px solid rgba(0,0,0,0.05);
  margin-right: 0; padding: 20px 24px;
}
:deep(.el-dialog__title) { font-weight: 700; color: var(--text-dark); }
.glass-panel-inset {
  background: rgba(241, 245, 249, 0.5);
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}
.detail-stat-box .value { font-size: 24px; font-family: 'Inter', sans-serif; letter-spacing: -0.5px; margin-top: 5px; }

.timeline-glass-card {
  background: rgba(255,255,255,0.6);
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}
.platform-tag { font-weight: bold; margin-right: 4px; }
.platform-tag.weibo { color: #e11d48; }
.platform-tag.bilibili { color: #06b6d4; }
.platform-tag.douyin { color: #1e293b; }

/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.3); border-radius: 10px; }

/* 动画定义 */
@keyframes float {
  0% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
  100% { transform: translateY(0px); }
}
@keyframes wave {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
  70% { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0); }
  100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
}
.fade-in { animation: fadeIn 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 常用间距和排版 */
.mb-10 { margin-bottom: 10px; }
.mb-20 { margin-bottom: 20px; }
.mb-24 { margin-bottom: 24px; }
.mt-5 { margin-top: 5px; }
.mt-20 { margin-top: 20px; }
.mr-5 { margin-right: 5px; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.filter-bar { display: flex; justify-content: space-between; align-items: center; }
.section-title-glass { 
  font-size: 16px; font-weight: 700; color: var(--text-dark); margin-bottom: 16px; 
  padding-left: 12px; border-left: 4px solid #6366f1;
}
.platform-badge {
    padding: 2px 8px; border-radius: 4px; color: white; font-size: 11px;
}
.platform-badge.weibo { background: #e6162d; }
.platform-badge.bilibili { background: #22a6f2; }
.platform-badge.douyin { background: #000; }
</style>