# 资产管理API

<cite>
**本文档引用的文件**   
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/db.py](file://backend/app/db.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/main.py](file://backend/app/main.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)
- [frontend/src/api/client.ts](file://frontend/src/api/client.ts)
</cite>

## 更新摘要
**所做更改**   
- 增强了多资产关联能力，支持资产间的复杂关系映射
- 完善了层次化组织功能，支持多级分类和继承机制
- 强化了资产与漏洞的关系映射，提供影响面分析能力
- 优化了批量操作接口，提升数据处理效率
- 更新了数据验证规则，增强业务逻辑约束

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖关系分析](#依赖关系分析)
7. [性能考虑](#性能考虑)
8. [故障排查指南](#故障排查指南)
9. [结论](#结论)
10. [附录](#附录)

## 简介
本文件为 Talos 资产管理 API 的详细技术文档，聚焦资产全生命周期管理：创建、查询、更新、删除（CRUD），资产分类体系与标签管理，搜索与过滤，批量导入导出（多格式），资产关联与依赖管理，状态跟踪与生命周期，以及数据验证与错误处理。文档同时提供前端调用示例与最佳实践建议，帮助开发者快速集成与高效使用。

**更新** 本次更新重点增强了多资产关联能力、层次化组织和资产与漏洞关系映射功能，提供更强大的资产管理能力。

## 项目结构
后端采用 FastAPI + SQLAlchemy 的模块化设计，资产相关能力分布在以下模块：
- API 层：资产接口定义与请求校验
- 服务层：导出等通用业务能力
- 模型层：数据库实体与关系
- 依赖注入：数据库会话与权限校验
- 常量与配置：枚举、默认值与系统常量
- 前端客户端：统一 HTTP 客户端封装

```mermaid
graph TB
subgraph "前端"
FE_Client["HTTP客户端<br/>client.ts"]
end
subgraph "后端API"
Main["FastAPI应用<br/>main.py"]
AssetsAPI["资产API<br/>assets.py"]
ImportsAPI["导入API<br/>imports.py"]
VulnsAPI["漏洞API<br/>vulns.py"]
end
subgraph "业务与数据"
Schemas["Pydantic模式<br/>schemas.py"]
Models["数据库模型<br/>business.py"]
DB["数据库会话<br/>db.py"]
Deps["依赖注入<br/>deps.py"]
Constants["常量与枚举<br/>constants.py"]
Exporter["导出服务<br/>exporter.py"]
end
FE_Client --> Main
Main --> AssetsAPI
Main --> ImportsAPI
Main --> VulnsAPI
AssetsAPI --> Schemas
ImportsAPI --> Schemas
VulnsAPI --> Schemas
AssetsAPI --> Models
ImportsAPI --> Models
VulnsAPI --> Models
AssetsAPI --> DB
ImportsAPI --> DB
VulnsAPI --> DB
AssetsAPI --> Deps
ImportsAPI --> Deps
VulnsAPI --> Deps
AssetsAPI --> Constants
ImportsAPI --> Constants
VulnsAPI --> Constants
AssetsAPI --> Exporter
```

**图表来源** 
- [backend/app/main.py](file://backend/app/main.py)
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/db.py](file://backend/app/db.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

章节来源
- [backend/app/main.py](file://backend/app/main.py)
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/db.py](file://backend/app/db.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

## 核心组件
- 资产API（assets.py）：提供资产的CRUD、分类、标签、搜索过滤、关联与依赖、状态变更等接口
- 导入API（imports.py）：支持批量导入资产数据，包含预览、校验、落库与任务进度
- 漏洞API（vulns.py）：管理漏洞信息及其与资产的关联关系
- Pydantic模式（schemas.py）：统一的输入输出数据结构与校验规则
- 数据库模型（business.py）：资产、分类、标签、关联、依赖、状态等实体及关系
- 依赖注入（deps.py）：数据库会话、权限与上下文获取
- 常量（constants.py）：资产类型、状态、分类、标签键等枚举与默认值
- 导出服务（exporter.py）：将资产数据导出为多种格式（CSV/Excel/JSON）

**更新** 新增了漏洞API模块，专门处理资产与漏洞之间的复杂关系映射和影响面分析。

章节来源
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

## 架构总览
资产管理的整体流程如下：
- 前端通过 client.ts 发起HTTP请求到后端
- FastAPI路由分发到 assets.py、imports.py 或 vulns.py
- 控制器调用 schemas.py 进行请求体校验
- 通过 deps.py 获取数据库会话与权限上下文
- 操作 business.py 中的模型完成持久化
- 可选调用 exporter.py 生成导出文件

```mermaid
sequenceDiagram
participant FE as "前端客户端"
participant API as "FastAPI路由"
participant Ctl as "资产控制器<br/>assets.py"
participant VCtl as "漏洞控制器<br/>vulns.py"
participant Sch as "数据模式<br/>schemas.py"
participant Dep as "依赖注入<br/>deps.py"
participant DB as "数据库会话<br/>db.py"
participant Mod as "数据模型<br/>business.py"
participant Exp as "导出服务<br/>exporter.py"
FE->>API : "POST /api/v1/assets"
API->>Ctl : "解析路由与参数"
Ctl->>Sch : "校验请求体"
Ctl->>Dep : "获取DB会话与权限"
Dep-->>Ctl : "返回会话与上下文"
Ctl->>DB : "执行插入/更新/查询"
DB-->>Mod : "映射到模型对象"
Mod-->>Ctl : "返回结果对象"
Ctl-->>API : "序列化响应"
API-->>FE : "返回JSON"
Note over Ctl,VCtl : "资产与漏洞关联操作"
Note over Ctl,Exp : "如需导出，控制器调用导出服务生成文件流"
```

**图表来源** 
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/db.py](file://backend/app/db.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

## 详细组件分析

### 资产CRUD接口
- 创建资产
  - 方法：POST /api/v1/assets
  - 功能：根据 schemas.py 定义的资产模式校验并创建资产记录
  - 输入：资产名称、类型、分类、标签、描述、状态等
  - 输出：创建的资产对象
- 查询资产
  - 方法：GET /api/v1/assets
  - 功能：分页、排序、过滤（按分类、标签、状态、关键字）
  - 参数：page、size、sort_by、filter_*、search
  - 输出：资产列表与分页元信息
- 更新资产
  - 方法：PUT/PATCH /api/v1/assets/{id}
  - 功能：部分或全量更新资产字段，保持约束与一致性
  - 输入：资产ID与待更新字段
  - 输出：更新后的资产对象
- 删除资产
  - 方法：DELETE /api/v1/assets/{id}
  - 功能：软删除或硬删除（依据策略），清理关联与依赖
  - 输出：删除结果与受影响记录数

**更新** 新增了对多资产关联的支持，允许在创建和更新时指定多个关联资产。

章节来源
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)

### 资产分类体系与标签管理
- 分类体系
  - 支持多级分类，便于资产组织与管理
  - 分类可继承属性，影响搜索与报表维度
  - 新增层次化组织结构，支持父子分类关系
- 标签管理
  - 键值对形式，支持批量添加、移除与替换
  - 标签键需符合命名规范，避免冲突
  - 支持按标签精确匹配与模糊搜索

**更新** 增强了分类体系的层次化能力，支持更复杂的资产组织结构。

章节来源
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)

### 搜索与过滤
- 关键字搜索：支持名称、描述、IP、域名等多字段模糊匹配
- 过滤器：按分类、标签、状态、创建时间范围等条件筛选
- 排序：支持多字段排序与自定义权重
- 分页：默认分页大小与最大限制控制

**更新** 新增了对资产关联关系的搜索支持，可以基于关联资产进行过滤。

章节来源
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)

### 批量导入导出
- 批量导入
  - 支持 CSV、Excel、JSON 等格式
  - 流程：上传 -> 预览 -> 校验 -> 确认 -> 落库
  - 错误处理：逐行校验，汇总错误报告，支持重试
- 批量导出
  - 支持 CSV、Excel、JSON 格式
  - 可按当前筛选条件导出，或指定资产ID集合
  - 异步任务：大文件导出采用后台任务，前端轮询进度

**更新** 优化了批量导入的性能，支持更大的数据集处理和更好的错误恢复机制。

章节来源
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)

### 资产关联关系与依赖管理
- 关联关系
  - 资产可属于多个分类，支持一对多或多对多
  - 资产间存在依赖关系（如主机与端口、服务与证书）
  - **新增** 支持多资产关联，允许建立复杂的资产网络关系
- 依赖管理
  - 维护依赖方向与强度，支持影响面分析
  - 删除资产时检查依赖链，防止破坏性操作
  - **新增** 提供依赖关系可视化和影响传播分析

**更新** 大幅增强了资产关联能力，支持更复杂的资产关系建模和影响面分析。

章节来源
- [backend/app/models/business.py](file://backend/app/models/business.py)

### 资产与漏洞关系映射
- 漏洞关联
  - 资产与漏洞的多对多关系映射
  - 支持漏洞严重程度评估和影响范围分析
  - 自动检测资产暴露的漏洞风险
- 影响面分析
  - 基于资产关联关系计算漏洞影响范围
  - 提供风险优先级排序和修复建议
  - 支持漏洞修复效果验证

**新增** 全新的漏洞关系映射功能，提供完整的漏洞管理和风险评估能力。

章节来源
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)

### 资产状态跟踪与生命周期
- 状态机
  - 常见状态：草稿、已发布、已归档、已下线
  - 状态转换受权限与前置条件约束
- 生命周期
  - 创建、审核、发布、变更、归档、销毁
  - 审计日志记录关键节点与操作人

**更新** 增强了状态跟踪的粒度，支持更细粒度的状态管理和审计追踪。

章节来源
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)

### 数据验证与错误处理
- 数据验证
  - 使用 Pydantic 模式进行强类型校验
  - 字段级校验：必填、长度、格式、枚举值、正则表达式
  - **新增** 关联关系完整性校验和业务规则验证
- 错误处理
  - 统一错误码与消息结构
  - 区分客户端错误与服务端错误
  - 事务回滚与异常捕获

**更新** 增强了数据验证规则，特别是针对多资产关联和业务逻辑的验证。

章节来源
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)

### 前端调用示例与最佳实践
- 客户端封装
  - 统一基础URL、超时、重试策略
  - 鉴权头注入与错误拦截
- 调用示例
  - 创建资产：构造请求体，发送POST，处理响应与错误
  - 查询资产：拼接查询参数，处理分页与排序
  - 导入导出：分片上传、进度轮询、文件下载
  - **新增** 资产关联操作：批量关联、关系查询、影响分析
- 最佳实践
  - 合理分页与限流，避免大查询
  - 批量操作使用事务，保证一致性
  - 敏感字段脱敏与加密传输
  - **新增** 合理使用关联查询，避免N+1问题

**更新** 新增了资产关联操作的前端调用示例和最佳实践指导。

章节来源
- [frontend/src/api/client.ts](file://frontend/src/api/client.ts)
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)

## 依赖关系分析
资产模块依赖关系如下：
- API层依赖模式层进行输入输出校验
- 控制器依赖依赖注入获取数据库会话与权限
- 模型层定义实体与关系，支撑查询与更新
- 常量层提供枚举与默认值，确保一致性
- 导出服务提供格式化输出能力

```mermaid
classDiagram
class AssetsAPI {
+创建资产()
+查询资产()
+更新资产()
+删除资产()
+批量导入()
+批量导出()
+管理资产关联()
}
class ImportsAPI {
+预览导入()
+校验导入()
+提交导入()
+查询导入进度()
}
class VulnsAPI {
+管理漏洞关联()
+影响面分析()
+风险评估()
+修复验证()
}
class Schemas {
+资产输入模式()
+资产输出模式()
+导入任务模式()
+导出任务模式()
+关联关系模式()
+漏洞映射模式()
}
class BusinessModels {
+资产实体()
+分类实体()
+标签实体()
+依赖实体()
+状态枚举()
+关联关系实体()
+漏洞映射实体()
}
class Deps {
+获取DB会话()
+权限校验()
+上下文获取()
}
class Constants {
+资产类型()
+资产状态()
+分类层级()
+标签键规范()
+漏洞级别()
+关联类型()
}
class Exporter {
+导出CSV()
+导出Excel()
+导出JSON()
+导出关联关系()
}
AssetsAPI --> Schemas : "校验输入输出"
ImportsAPI --> Schemas : "校验输入输出"
VulnsAPI --> Schemas : "校验输入输出"
AssetsAPI --> BusinessModels : "读写数据"
ImportsAPI --> BusinessModels : "批量写入"
VulnsAPI --> BusinessModels : "管理关联关系"
AssetsAPI --> Deps : "获取会话与权限"
ImportsAPI --> Deps : "获取会话与权限"
VulnsAPI --> Deps : "获取会话与权限"
AssetsAPI --> Constants : "使用枚举与默认值"
ImportsAPI --> Constants : "使用枚举与默认值"
VulnsAPI --> Constants : "使用枚举与默认值"
AssetsAPI --> Exporter : "生成导出文件"
```

**图表来源** 
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

章节来源
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)
- [backend/app/models/business.py](file://backend/app/models/business.py)
- [backend/app/core/deps.py](file://backend/app/core/deps.py)
- [backend/app/constants.py](file://backend/app/constants.py)
- [backend/app/services/exporter.py](file://backend/app/services/exporter.py)

## 性能考虑
- 查询优化
  - 合理使用索引（分类、标签、状态、时间戳）
  - 避免N+1查询，使用预加载或连接查询
  - **新增** 关联关系查询优化，使用适当的JOIN策略
- 批量操作
  - 导入采用分批提交，减少内存占用
  - 导出采用流式生成，避免大对象驻留
  - **新增** 批量关联操作优化，支持事务性更新
- 并发与锁
  - 写操作加乐观锁或行级锁，防止竞态
  - 长耗时任务异步化，提升响应速度
  - **新增** 关联关系更新的并发控制
- 缓存策略
  - 热点分类与标签结果缓存
  - 导出任务状态缓存，降低重复计算
  - **新增** 关联关系图谱缓存，加速影响面分析

**更新** 针对新增的多资产关联和漏洞映射功能，提供了专门的性能优化建议。

## 故障排查指南
- 常见问题
  - 数据校验失败：检查字段类型、必填项与格式
  - 权限不足：确认用户角色与资源访问策略
  - 导入失败：查看错误报告定位问题行
  - 导出超时：调整批次大小与后台任务队列
  - **新增** 关联关系冲突：检查资产ID有效性和关系约束
  - **新增** 漏洞映射错误：验证漏洞代码和资产类型兼容性
- 调试建议
  - 启用详细日志，记录请求与SQL
  - 使用测试数据复现问题
  - 逐步缩小范围，定位异常点
  - **新增** 使用关联关系调试工具，检查数据完整性

**更新** 新增了针对多资产关联和漏洞映射功能的故障排查指导。

章节来源
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)
- [backend/app/schemas.py](file://backend/app/schemas.py)

## 结论
Talos 资产管理API提供了完整的资产CRUD、分类与标签、搜索过滤、批量导入导出、关联依赖、状态生命周期、数据验证与错误处理能力。**更新后** 系统新增了强大的多资产关联能力、层次化组织和资产与漏洞关系映射功能，为企业级资产管理提供了更全面的支持。通过清晰的模块划分与依赖注入机制，系统具备良好的可扩展性与可维护性。建议在生产环境中结合索引优化、异步任务与缓存策略，以获得稳定高效的资产管理体验。

## 附录
- API调用示例（前端）
  - 创建资产：构造请求体，发送POST，处理响应与错误
  - 查询资产：拼接查询参数，处理分页与排序
  - 导入导出：分片上传、进度轮询、文件下载
  - **新增** 资产关联操作：批量关联、关系查询、影响分析
  - **新增** 漏洞映射操作：关联漏洞、风险评估、修复验证
- 最佳实践
  - 合理分页与限流，避免大查询
  - 批量操作使用事务，保证一致性
  - 敏感字段脱敏与加密传输
  - **新增** 合理使用关联查询，避免N+1问题
  - **新增** 设计合理的关联关系模型，避免循环依赖

**更新** 新增了资产关联和漏洞映射相关的API调用示例和最佳实践指导。

章节来源
- [frontend/src/api/client.ts](file://frontend/src/api/client.ts)
- [backend/app/api/v1/assets.py](file://backend/app/api/v1/assets.py)
- [backend/app/api/v1/imports.py](file://backend/app/api/v1/imports.py)
- [backend/app/api/v1/vulns.py](file://backend/app/api/v1/vulns.py)