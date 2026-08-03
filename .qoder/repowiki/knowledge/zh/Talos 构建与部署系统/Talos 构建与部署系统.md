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
    - backend/requirements.txt
    - frontend/package.json
    - backend/pytest.ini
    - backend/alembic.ini
---

## 构建系统与部署架构

### 1. 多环境构建策略

项目采用**双轨构建模式**：本地开发使用轻量级 SQLite + 内存队列，生产环境使用 Docker Compose 编排完整依赖栈。

- **后端（Python/FastAPI）**：通过 `requirements.txt` 管理依赖，使用 `uvicorn` 作为 ASGI 服务器，支持异步数据库操作（asyncpg）和任务队列（arq + Redis）
- **前端（Vue 3/Vite）**：通过 `package.json` 管理依赖，使用 Vite 构建静态资源，Nginx 反向代理提供静态文件服务
- **容器化**：每个服务独立 Dockerfile，docker-compose.yml 统一编排 PostgreSQL、Redis、Gotenberg 等依赖服务

### 2. 核心构建文件与工具链

**后端构建配置：**
- `backend/Dockerfile`：基于 python:3.12-slim 的多阶段镜像，安装依赖后启动 uvicorn
- `backend/requirements.txt`：定义运行时依赖，包含 FastAPI、SQLAlchemy、Pydantic、Redis、arq 等
- `backend/pytest.ini`：配置 pytest 的 asyncio 自动模式
- `backend/alembic.ini`：数据库迁移配置

**前端构建配置：**
- `frontend/Dockerfile`：Node.js 构建阶段 + Nginx 运行阶段的二阶段构建
- `frontend/package.json`：定义 npm scripts（dev/build/preview）和依赖版本
- `frontend/vite.config.ts`：Vite 构建配置
- `frontend/nginx.conf`：Nginx 反向代理配置

**开发脚本：**
- `dev.sh`：Linux/macOS 一键开发脚本，自动创建 Python venv、安装依赖、启动前后端
- `dev.ps1`：Windows PowerShell 版本的开发脚本
- `docker-compose.yml`：生产环境编排，包含健康检查和数据卷持久化

### 3. 构建流程与依赖管理

**本地开发流程：**
```bash
# 执行 dev.sh 或 dev.ps1 自动完成：
# 1. 检查 Python/Node/npm 依赖
# 2. 初始化 backend/.venv 虚拟环境
# 3. 安装 requirements-dev.txt 依赖
# 4. 安装 frontend/node_modules
# 5. 启动后端（SQLite + 免队列模式）
# 6. 启动前端 Vite Dev Server
```

**生产构建流程：**
```bash
# Docker Compose 构建顺序：
# 1. postgres:16-alpine - PostgreSQL 数据库
# 2. redis:7-alpine - Redis 缓存和任务队列
# 3. gotenberg/gotenberg:8 - PDF 生成服务
# 4. api - FastAPI 应用（端口 8000）
# 5. worker - arq 任务处理器
# 6. frontend - Nginx 静态文件服务（端口 80）
```

### 4. 环境变量与配置管理

**后端环境变量（VP_ 前缀）：**
- `VP_DATABASE_URL`：数据库连接字符串（支持 SQLite/PostgreSQL）
- `VP_REDIS_URL`：Redis 连接地址
- `VP_GOTENBERG_URL`：PDF 生成服务地址
- `VP_SECRET_KEY`：JWT 密钥
- `VP_STORAGE_DIR`：文件存储目录
- `VP_DISABLE_QUEUE`：禁用队列模式（开发用）

**测试环境：**
- 使用 SQLite 内存数据库进行单元测试
- pytest 自动处理异步测试用例
- 测试数据存储在 `tests/test_vp.db` 中

### 5. 部署与运维约定

**容器化规范：**
- 每个服务独立 Dockerfile，遵循最小化镜像原则
- 使用 Alpine 基础镜像减小体积
- 健康检查确保服务就绪后再启动依赖服务
- 数据持久化通过 Docker volumes 管理

**开发环境优化：**
- 后端使用 `--reload` 参数实现热重载
- 前端使用 Vite Dev Server 提供快速刷新
- 默认账号 `admin/admin123` 便于快速体验
- API 文档自动生成为 `/api/docs`（Swagger UI）

**跨平台支持：**
- 提供 bash 和 PowerShell 两套开发脚本
- 路径处理适配不同操作系统
- 错误提示使用彩色输出提升可读性