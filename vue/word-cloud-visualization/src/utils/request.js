import axios from 'axios'

const service = axios.create({
  baseURL: 'http://localhost:8000/api', 
  timeout: 5000
})

// 响应拦截器
service.interceptors.response.use(
  response => {
    const res = response.data
    // Python 后端返回的是 { code: 200, data: ..., msg: ... }
    if (res.code === 200) {
      // ✅ 这里直接返回 res.data，这样组件里拿到的就是纯数据
      return res.data 
    } else {
      console.error('接口错误:', res.msg)
      return Promise.reject(new Error(res.msg || 'Error'))
    }
  },
  error => {
    console.error('请求失败:', error)
    return Promise.reject(error)
  }
)

export default service