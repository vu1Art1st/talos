---
kind: error_handling
name: Talos 漏洞管理平台错误处理机制
category: error_handling
scope:
    - '**'
source_files:
    - backend/app/main.py
    - backend/app/core/deps.py
    - backend/app/api/v1/auth.py
    - backend/app/api/v1/assets.py
    - frontend/src/api/client.ts
    - backend/app/workers/dispatch.py
---

## 错误处理架构概述

Talos 平台采用前后端分离的错误处理策略：后端基于 FastAPI 的 HTTPException 进行统一业务错误返回，前端通过 Axios 拦截器实现全局错误响应处理和用户提示。

## 后端错误处理模式

### 1. 统一的 HTTPException 抛出方式
- **认证错误**：在 `core/deps.py` 中通过 `get_current_user` 依赖函数统一处理 token 验证失败（401）和权限不足（403）
- **业务错误**：在各 API 路由中直接 raise HTTPException，如 assets.py 中的文件类型校验、大小限制、数据不存在等场景
- **参数校验错误**：使用 400 状态码配合明确的中文错误消息

### 2. 中间件层错误处理
- CORS 中间件：在 `main.py` 中配置允许跨域请求
- 无自定义异常处理器：未注册 `@app.exception_handler`，依赖 FastAPI 默认异常处理机制

### 3. 异步任务错误降级
- `workers/dispatch.py` 实现了 Redis/Arq 队列不可用时的进程内执行降级
- `main.py` 启动时尝试连接 Redis，失败则记录警告日志并禁用队列功能

## 前端错误处理策略

### 1. Axios 全局拦截器
- **请求拦截**：自动附加 access_token 到 Authorization 头
- **响应拦截**：集中处理 401 未授权、网络错误和业务错误
- **Token 刷新机制**：遇到 401 时自动调用 refresh 接口获取新 token 并重试请求

### 2. 用户友好的错误提示
- 使用 Element Plus 的 ElMessage.error 显示错误信息
- 对 409 冲突错误不显示重复提示
- 网络错误时显示通用 "请求失败" 消息

## 错误分类与状态码约定

| 状态码 | 用途 | 示例场景 |
|--------|------|----------|
| 400 | 客户端参数错误 | 文件格式不支持、文件大小超限、必填字段缺失 |
| 401 | 认证失败 | 用户名密码错误、token 过期、账号被禁用 |
| 403 | 权限不足 | 缺少所需权限、账号已禁用 |
| 404 | 资源不存在 | 资产不存在、导入批次不存在 |

## 关键约束与约定

1. **错误消息语言**：所有 HTTPException 的错误消息均使用中文，便于用户理解
2. **统一错误格式**：FastAPI 默认将 HTTPException 转换为 `{"detail": "错误消息"}` 格式的 JSON 响应
3. **前端错误过滤**：409 冲突错误不显示错误提示，避免重复通知
4. **安全原则**：认证相关错误不泄露敏感信息，仅返回通用错误消息
5. **降级策略**：Redis 队列服务不可用时自动降级为进程内执行，保证系统可用性

## 待改进点

- 缺乏统一的自定义异常基类，建议创建 `AppException` 基类统一管理错误码和消息
- 未实现全局异常处理器，无法统一格式化错误响应格式
- 日志记录不够完善，部分异常仅打印警告而未记录详细堆栈信息