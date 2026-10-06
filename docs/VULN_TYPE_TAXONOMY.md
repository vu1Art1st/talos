# 漏洞类型字典与 OWASP 映射

漏洞类型（`vul_type`）是平台对漏洞本质的技术分类，唯一来源是 `backend/app/constants.py::VUL_TYPE`，
由 `/meta` 下发前端色值与名称；内置类型随 `init_db()` 写入 `vuln_types` 表，用户新增类型从 `code=1000` 起。

OWASP Top 10:2021 是**归类审校标准**而非字典本身——它是风险类别，粒度较粗（SQL 注入、XSS、命令执行
同属 A03），直接替换技术分类会丢失渗透报告所需的区分度。平台保留细粒度技术类型，但每个类型都能
对应到 OWASP 类别，且不再用「威胁情报」这类非漏洞类型兜底。

## 字典映射

| code | 类型 | OWASP 对应 |
|---|---|---|
| 10 | SQL注入漏洞 | A03 Injection |
| 15 | XSS跨站漏洞 | A03 Injection |
| 20 | 命令执行漏洞 | A03 Injection |
| 25 | 代码执行漏洞 | A03 / A08（反序列化） |
| 30 | 文件包含漏洞 | A03 Injection |
| 35 | 任意文件操作 | A01 Broken Access Control / A05 Misconfiguration |
| 40 | 权限绕过 | A01 Broken Access Control |
| 45 | 逻辑漏洞 | A04 Insecure Design / A07 Auth Failures |
| 50 | 存在后门 | A08 Integrity Failures |
| 55 | 信息泄露 | A05 Misconfiguration / A01 |
| 60 | 文件上传 | A05 Misconfiguration / A01 |
| 65 | 弱口令 | A07 Auth Failures |
| 70 | 威胁情报（仅保留兼容，模板库不再使用） | - |
| 75 | 其他 | - |
| 80 | 其他注入 | A03 Injection（LDAP / NoSQL / XPath 注入、CRLF / Host 头注入、XXE） |
| 85 | 服务端请求伪造 | A10 SSRF |
| 90 | 拒绝服务 | API4:2023 Unrestricted Resource Consumption |
| 95 | 加密缺陷 | A02 Cryptographic Failures |
| 100 | 组件已知漏洞 | A06 Vulnerable and Outdated Components |

## 归类规则

- **组件 CVE 按漏洞本质归类**：命令注入 / 代码执行 / 权限绕过 / 信息泄露 / 拒绝服务各归其位；
  只有无法落到具体类型的组件类条目才用 `100 组件已知漏洞`。禁止把 CVE 一律塞进「威胁情报」。
- **20 命令执行**用于操作系统命令注入 / 执行；**25 代码执行**用于反序列化、模板注入（SSTI）、
  沙箱逃逸、缓冲区溢出、表达式注入等代码级执行。
- SSRF、拒绝服务、加密缺陷、非 SQL 注入必须使用 `85 / 90 / 95 / 80` 专用码，不得兜底到
  「逻辑漏洞」或「其他」。
- 新增内置类型需同步 `constants.py` 的 `VUL_TYPE` 与 `VUL_TYPE_COLOR`，并在
  `tests/test_knowledge_templates.py::test_vul_type_follows_owasp_mapping` 增补断言。

## 变更记录

- **2026-10-06**：新增 `80 其他注入 / 85 服务端请求伪造 / 90 拒绝服务 / 95 加密缺陷 /
  100 组件已知漏洞` 五个内置类型；`knowledge-import-vulnerabilities.json` 全量复核并调整 30 条
  归类（含用户反馈的 `Text4shell远程代码漏洞（CVE-2022-42889）` 由「威胁情报」改为「代码执行漏洞」），
  模板库不再使用 code 70。
