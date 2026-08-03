import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const client = axios.create({ baseURL: '/api/v1', timeout: 30000 })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string | null> | null = null

async function refreshToken(): Promise<string | null> {
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) return null
  try {
    const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refresh })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    return data.access_token
  } catch {
    return null
  }
}

client.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const { response, config } = error
    if (response?.status === 401 && !config._retried && !config.url?.includes('/auth/login')) {
      config._retried = true
      refreshing = refreshing ?? refreshToken()
      const token = await refreshing
      refreshing = null
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
        return client(config)
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      router.push('/login')
    }
    const msg = response?.data?.detail || error.message || '请求失败'
    if (response?.status !== 409) ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
    return Promise.reject(error)
  },
)

export default client
