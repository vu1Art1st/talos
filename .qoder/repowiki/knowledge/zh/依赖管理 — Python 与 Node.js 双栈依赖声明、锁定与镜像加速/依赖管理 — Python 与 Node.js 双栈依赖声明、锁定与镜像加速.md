---
kind: dependency_management
name: 依赖管理 — Python 与 Node.js 双栈依赖声明、锁定与镜像加速
category: dependency_management
scope:
    - '**'
source_files:
    - backend/requirements.txt
    - backend/requirements-dev.txt
    - frontend/package.json
    - frontend/pnpm-lock.yaml
    - backend/Dockerfile
    - frontend/Dockerfile
---

本仓库采用前后端分离的双栈依赖管理策略：后端使用 Python pip + requirements.txt，前端使用 pnpm + package.json + pnpm-lock.yaml，并通过 Dockerfile 中的 npm registry 镜像源实现构建加速。

**1. 使用的系统与工具**
- 后端（Python）：pip 包管理器，通过 `requirements.txt` 声明运行时依赖，`requirements-dev.txt` 通过 `-r requirements.txt` 引用并叠加测试依赖。
- 前端（Node.js）：pnpm 作为包管理器，`package.json` 声明 dependencies 与 devDependencies，`pnpm-lock.yaml` 锁定精确版本与依赖树，`pnpm-workspace.yaml` 表明存在 workspace 配置。
- 容器化构建：后端 Dockerfile 基于 `python:3.12-slim`，前端 Dockerfile 基于 `node:20-alpine` 构建产物后由 `nginx:1.27-alpine` 静态托管。

**2. 核心文件与位置**
- `backend/requirements.txt`：后端运行时依赖清单，包含 FastAPI、uvicorn、SQLAlchemy、alembic、pydantic、redis、arq、python-docx、docxtpl、httpx、openpyxl、PyMySQL 等。
- `backend/requirements-dev.txt`：开发依赖，引用 `requirements.txt` 并追加 pytest、pytest-asyncio、aiosqlite。
- `frontend/package.json`：前端依赖声明，Vue 3、Element Plus、Pinia、vue-router、axios、echarts、Tiptap 编辑器套件及 Vite/Tailwind/TypeScript 等开发依赖。
- `frontend/pnpm-lock.yaml`：pnpm 生成的锁文件，记录每个包的精确版本、完整性校验（integrity）及 peerDependencies 解析结果。
- `backend/Dockerfile`：后端镜像构建脚本，`COPY requirements.txt . && RUN pip install --no-cache-dir -r requirements.txt` 确保依赖可重现安装。
- `frontend/Dockerfile`：前端镜像构建脚本，`RUN npm install --registry=https://registry.npmmirror.com` 指定国内镜像源加速下载。

**3. 架构与约定**
- 依赖分层：后端将运行期依赖与开发依赖拆分为两个文件，通过 `-r` 引用避免重复声明。
- 版本策略：后端使用 `>=` 语义范围（如 `fastapi>=0.115`、`sqlalchemy[asyncio]>=2.0.30`），允许小版本升级；前端使用 `^` 语义范围（如 `vue: ^3.4.27`），允许次版本更新。两者均通过 lockfile（pnpm-lock.yaml）在构建时固定实际版本。
- 构建缓存优化：后端 Dockerfile 先 COPY 并安装依赖再 COPY 源码，利用 Docker 层缓存加速重复构建。
- 网络加速：前端构建阶段显式设置 `--registry=https://registry.npmmirror.com` 以绕过外网访问限制。

**4. 约定与约束**
- 所有第三方依赖必须通过各自的 manifest 文件（`requirements.txt` / `package.json`）声明，禁止在代码中硬编码版本号。
- 前端变更需同步更新 `pnpm-lock.yaml`，确保 CI/CD 环境可复现安装。
- 后端依赖升级应遵循 `>=` 范围的最低兼容版本原则，避免破坏性升级。
- 未在后端发现类似 `pip.conf`、`setup.cfg` 或私有 PyPI 源的配置，依赖全部来自官方 PyPI。
- 未发现 vendoring（如 `vendor/` 目录或 `poetry.lock` 之外的本地包复制）策略。