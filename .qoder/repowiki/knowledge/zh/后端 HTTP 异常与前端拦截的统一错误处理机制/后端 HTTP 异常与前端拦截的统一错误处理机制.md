---
kind: error_handling
name: 后端 HTTP 异常与前端拦截的统一错误处理机制
category: error_handling
scope:
    - '**'
source_files:
    - backend/app/main.py
    - backend/app/core/deps.py
    - backend/app/core/security.py
    - backend/app/api/v1/auth.py
    - backend/app/api/v1/assets.py
    - backend/app/api/v1/reports.py
    - backend/app/api/v1/misc.py
    - backend/app/workers/dispatch.py
    - frontend/src/api/client.ts
---

## 1. 系统/方法概述
本项目采用 FastAPI + Pydantic + SQLAlchemy Async 的后端架构，配合 Vue 3 + Element Plus + Axios 的前端。错误处理围绕以下层次展开：
- 后端：通过 FastAPI 的 `HTTPException` 在业务层直接抛出异常，由 FastAPI 默认异常处理器统一转换为 JSON 响应；Pydantic 负责请求体校验并返回结构化错误。
- 前端：Axios 响应拦截器集中处理 401（自动刷新 token 并重试）、其他状态码统一以 ElMessage 提示，保持 UI 一致性。
- 异步任务：arq 队列投递失败时回退为进程内执行，并通过日志降级记录，保证功能可用性。

## 2. 关键文件与位置
- 后端应用入口与中间件：`backend/app/main.py`（注册 CORS、路由、静态资源挂载）
- 认证与权限依赖：`backend/app/core/deps.py`（`get_current_user`、`require_perm`、`require_any_perm` 中抛出 401/403）
- 安全工具：`backend/app/core/security.py`（JWT 编解码、密码哈希/校验，失败返回 None 或 False）
- API 路由示例（大量使用 HTTPException）：`backend/app/api/v1/auth.py`、`backend/app/api/v1/assets.py`、`backend/app/api/v1/reports.py`、`backend/app/api/v1/misc.py`
- 异步任务分发与降级：`backend/app/workers/dispatch.py`（Redis/arq 不可用时转为 asyncio.create_task 本地执行）
- 前端 Axios 客户端与拦截器：`frontend/src/api/client.ts`（401 刷新 token、统一错误提示）

## 3. 架构与约定
- 业务层错误表达：所有业务异常均通过 `raise HTTPException(status_code, detail)` 抛出，例如用户名密码错误、账号禁用、资源不存在、权限不足、并发冲突（409 乐观锁）等。FastAPI 默认会将这些异常序列化为 `{"detail": "..."}` 的 JSON 响应。
- 参数校验错误：由 Pydantic 模型自动校验，未通过时返回标准 422 错误结构，包含字段级错误信息。
- 认证与授权：
  - `core/deps.get_current_user` 在 token 无效或用户不存在/禁用时抛出 401。
  - `require_perm` / `require_any_perm` 在缺少权限时抛出 403，并附带缺失权限名。
- 全局异常处理器：代码库中未发现自定义 `@app.exception_handler` 注册，因此依赖 FastAPI 默认行为将 `HTTPException` 和 Pydantic `ValidationError` 转换为标准 JSON 响应。
- 前端错误处理：
  - 请求拦截器自动附加 `Authorization: Bearer <token>`。
  - 响应拦截器对 401 触发 refresh_token 流程，成功后重试原请求；失败则清除本地 token 并跳转登录页。
  - 非 409 的错误统一通过 `ElMessage.error` 展示 `response.data.detail` 或 fallback 消息。
- 异步任务降级：`workers/dispatch.dispatch` 先尝试 arq 入队，捕获异常后记录 warning 并改为本地 `asyncio.create_task` 执行，确保 Redis 不可用不影响主流程。

## 4. 约定与约束
- 业务异常必须使用 `fastapi.HTTPException` 抛出，禁止吞掉异常或直接返回错误字符串。
- 认证失败统一返回 401，权限不足统一返回 403，且 detail 需给出可读中文说明。
- 资源不存在统一返回 404，并发冲突（如报告版本不一致）返回 409。
- 前端仅对非 409 的状态码显示错误消息，避免覆盖用户明确感知的冲突提示。
- 异步任务必须遵循“优先队列、失败降级”的策略，并在日志中记录降级原因。
- 所有输入数据通过 Pydantic 模型进行校验，非法输入由框架返回 422，无需在业务层重复校验。

该方案简洁一致，前后端协作清晰，但尚未定义统一的错误码枚举或全局异常处理器来进一步收敛错误格式与语义。