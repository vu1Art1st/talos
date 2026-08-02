---
kind: build_system
name: Talos 构建与部署系统
category: build_system
scope:
    - '**'
source_files:
    - docker-compose.yml
    - backend/Dockerfile
    - frontend/Dockerfile
    - dev.sh
    - dev.ps1
    - frontend/nginx.conf
    - backend/requirements.txt
    - frontend/package.json
    - backend/alembic.ini
    - docs/RELEASE.md
---

## 构建系统与部署架构

### 一、构建工具链

**后端（Python/FastAPI）**：
- 依赖管理：requirements.txt + requirements-dev.txt，通过 pip install -r requirements.txt 安装
- 运行环境：Python 3.12-slim 基础镜像，Uvicorn ASGI 服务器启动 FastAPI 应用
- 数据库迁移：Alembic 管理版本化迁移脚本（alembic/versions/），连接串从环境变量 VP_DATABASE_URL 读取

**前端（Vue 3 + Vite）**：
- 包管理：pnpm（pnpm-lock.yaml）+ npm（package-lock.json 并存），使用淘宝镜像 https://registry.npmmirror.com
- 构建工具：Vite 5.x，TypeScript 支持，Tailwind CSS + PostCSS 处理样式
- 构建产物：输出到 frontend/dist/，由 Nginx 静态托管

### 二、容器化部署

**Docker 多阶段构建**：
- 后端镜像：python:3.12-slim → 安装依赖 → 复制代码 → Uvicorn 启动 8000 端口
- 前端镜像：node:20-alpine 构建 → nginx:1.27-alpine 托管静态资源 → 反向代理 /api/ 和 /storage/

**服务编排（docker-compose.yml）**：
- postgres:16-alpine：PostgreSQL 数据库，健康检查 pg_isready
- redis:7-alpine：任务队列缓存
- gotenberg/gotenberg:8：Word/PDF 文档转换服务
- api：FastAPI 后端，暴露 8000 端口
- worker：arq 异步任务处理器，复用后端镜像
- frontend：Nginx 前端，暴露 80 端口，反向代理 API 请求

### 三、开发环境

**一键启动脚本**：
- dev.sh（Linux/macOS）：自动创建 Python venv，SQLite 免队列模式，Vite 热重载
- dev.ps1（Windows PowerShell）：等效 Windows 版本，支持 UTF-8 BOM 编码

**开发模式特点**：
- 后端使用 SQLite + VP_DISABLE_QUEUE=1 禁用 Redis 队列
- 前端 Vite Dev Server 监听 5173 端口
- 自动依赖检测与环境初始化

### 四、版本管理与发布流程

**语义化版本控制**：
- 遵循 SemVer x.y.z 规范，当前处于 0.y.z 快速迭代阶段
- 版本号同步位置：docs/RELEASE.md、backend/app/core/config.py 的 APP_VERSION、frontend/package.json 的 version
- Git 标签：git tag -a v x.y.z -m "release x.y.z"

**变更日志**：按 Keep a Changelog 格式组织，分类为新增/变更/修复/移除/安全

### 五、配置管理

**环境变量驱动**：
- 数据库连接：VP_DATABASE_URL（支持 PostgreSQL/SQLite）
- Redis 连接：VP_REDIS_URL
- Gotenberg 地址：VP_GOTENBERG_URL
- 存储路径：VP_STORAGE_DIR
- 安全密钥：VP_SECRET_KEY

**Nginx 反向代理配置**：
- 前端路由 history 模式支持
- API 代理到后端 8000 端口
- 文件上传代理到后端 storage 接口
- 最大上传大小 64MB

### 六、关键约束

- 前后端分离部署，通过 Nginx 统一入口
- 异步任务依赖 Redis，无 Redis 时自动降级为进程内执行
- 所有服务通过 Docker Compose 统一编排，卷持久化数据库和存储数据
- 开发环境与生产环境通过不同脚本和环境变量区分