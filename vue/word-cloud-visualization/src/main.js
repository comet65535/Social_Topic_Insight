import { createApp } from 'vue'
import App from './App.vue'
// 导入Element Plus核心和样式
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 导入所有图标
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// 创建实例
const app = createApp(App)
// 注册Element Plus
app.use(ElementPlus)
// 全局注册所有图标（遍历+注册）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
// 挂载到#app
app.mount('#app')