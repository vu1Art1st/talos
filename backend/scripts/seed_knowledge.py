"""漏洞知识库预置数据：录入 50 个最常见漏洞的标准信息（幂等，按漏洞名称 upsert）。

用法（backend 目录下）：
    python -m scripts.seed_knowledge

数据结构：(漏洞名称, 漏洞类型码 VUL_TYPE, 危害等级码 VUL_LEVEL, 标准描述, 危害说明, 修复建议, 参考链接)
描述/危害/修复建议为纯文句，入库时包裹为 <p> 段落，与富文本编辑器产出结构兼容。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (name, vul_type, severity_level, description, harm, solution, references)
SEED_DATA: list[tuple[str, int, int, str, str, str, list[str]]] = [
    ("SQL注入", 10, 10,
     "应用程序将未经过滤的用户输入直接拼接进 SQL 语句，攻击者可构造恶意输入改变查询逻辑，操纵数据库执行任意查询或命令。",
     "可导致数据库敏感信息被拖库、数据被篡改或删除，结合数据库特性还可能进一步获取服务器操作系统权限。",
     "使用参数化查询（预编译语句）或 ORM 框架，禁止字符串拼接 SQL；对输入做白名单校验；数据库账号遵循最小权限原则，关闭详细错误回显。",
     ["https://owasp.org/Top10/", "https://portswigger.net/web-security/sql-injection"]),
    ("SQL盲注", 10, 20,
     "应用存在 SQL 注入但不直接回显查询结果，攻击者通过布尔条件差异或时间延迟逐位推断数据库内容。",
     "攻击者可在无回显场景下缓慢窃取数据库中的敏感数据，隐蔽性强，常规日志难以及时发现。",
     "与普通 SQL 注入一致：参数化查询、输入白名单校验、统一错误页面；并对异常高频请求做速率限制与告警。",
     ["https://portswigger.net/web-security/sql-injection/blind"]),
    ("NoSQL注入", 10, 20,
     "应用将用户输入直接拼入 MongoDB 等 NoSQL 查询条件，攻击者可注入查询运算符（如 $ne、$gt、$where）绕过校验或读取数据。",
     "可绕过登录认证、越权读取集合数据，$where 注入还可能执行任意 JavaScript 造成拒绝服务。",
     "对输入做类型强校验（拒绝对象型参数），使用官方驱动的参数绑定机制，禁用 $where 等危险运算符。",
     ["https://owasp.org/www-community/Injection_Flaws"]),
    ("LDAP注入", 10, 20,
     "应用将用户输入直接拼接进 LDAP 查询过滤器，攻击者可注入特殊字符改变查询语义。",
     "可绕过认证、枚举目录中的用户与组织信息，获取内部账号结构。",
     "对输入中的 LDAP 特殊字符（* ( ) \\ 及空字符）进行转义，使用安全的 LDAP 查询 API 并做白名单校验。",
     ["https://owasp.org/www-community/attacks/LDAP_Injection"]),
    ("XPath注入", 10, 30,
     "应用使用用户输入拼接 XPath 查询语句检索 XML 数据，攻击者可注入表达式改变查询逻辑。",
     "可绕过认证或读取 XML 文档中本不可见的节点数据，造成敏感信息泄露。",
     "使用参数化 XPath 接口，对输入中的引号等特殊字符转义，并做输入白名单校验。",
     ["https://owasp.org/www-community/attacks/XPATH_Injection"]),
    ("存储型XSS", 15, 20,
     "攻击者提交的恶意脚本被持久化存储到服务端（数据库、文件等），其他用户浏览相关页面时脚本在其浏览器中执行。",
     "可批量窃取用户会话凭证、伪造操作、植入钓鱼页面或挂马，影响所有访问该页面的用户，危害面广。",
     "对输出到页面的内容做上下文相关的 HTML 编码；入库前按白名单过滤富文本标签与属性；设置 CSP 与 Cookie 的 HttpOnly 属性。",
     ["https://owasp.org/www-community/attacks/xss/", "https://portswigger.net/web-security/cross-site-scripting/stored"]),
    ("反射型XSS", 15, 30,
     "服务端将请求参数未经编码直接回显到响应页面，攻击者构造含恶意脚本的链接诱骗用户点击后在其浏览器执行。",
     "可窃取受害用户的会话凭证、执行伪造操作，常与钓鱼邮件、短链接结合实施定向攻击。",
     "对所有回显到页面的参数做 HTML/JS 上下文编码，设置 CSP 与 HttpOnly，避免将用户输入直接写入页面。",
     ["https://portswigger.net/web-security/cross-site-scripting/reflected"]),
    ("DOM型XSS", 15, 30,
     "前端 JavaScript 将 location、referrer 等可控数据未经处理写入 DOM（如 innerHTML、eval），恶意载荷完全在浏览器端触发。",
     "可窃取会话与本地存储数据、伪造页面内容，且服务端日志无法记录攻击载荷，检测困难。",
     "避免使用 innerHTML/eval 等危险 API，改用 textContent 等安全写法；对 URL 片段等来源数据先做编码或校验；启用 CSP。",
     ["https://portswigger.net/web-security/cross-site-scripting/dom-based"]),
    ("SSRF服务器端请求伪造", 75, 20,
     "服务端根据用户可控的 URL 发起网络请求且未做限制，攻击者可借服务器身份访问内网或本机服务。",
     "可探测扫描内网、读取云主机元数据（窃取临时凭证）、攻击内网未授权服务（如 Redis）进而横向渗透。",
     "对目标地址做协议与域名白名单校验，解析后禁止私有网段与本机回环地址，禁用重定向跟随，屏蔽 file/gopher/dict 等协议。",
     ["https://owasp.org/www-community/attacks/Server_Side_Request_Forgery", "https://portswigger.net/web-security/ssrf"]),
    ("CSRF跨站请求伪造", 75, 30,
     "关键操作接口仅依赖 Cookie 会话鉴权且缺少防伪造校验，攻击者可诱导已登录用户的浏览器发起非本意请求。",
     "可以受害用户身份执行改密、转账、加好友等敏感操作，用户全程无感知。",
     "为状态变更请求增加 CSRF Token 并在服务端校验；Cookie 设置 SameSite 属性；关键操作要求二次验证。",
     ["https://owasp.org/www-community/attacks/csrf"]),
    ("XXE外部实体注入", 75, 20,
     "XML 解析器未禁用外部实体，攻击者在提交的 XML 中声明恶意实体，诱使服务端解析时加载本地文件或远程资源。",
     "可读取服务器任意文件、发起 SSRF 攻击内网，部分场景可造成拒绝服务甚至远程代码执行。",
     "解析 XML 时禁用 DTD 与外部实体解析（如 Java 设置 disallow-doctype-decl），优先使用 JSON 等更简单的数据格式。",
     ["https://owasp.org/www-community/vulnerabilities/XML_External_Entity_(XXE)_Processing"]),
    ("CRLF注入", 75, 30,
     "服务端将用户输入未过滤地写入 HTTP 响应头，攻击者注入回车换行字符可拆分或伪造响应头。",
     "可导致 HTTP 响应拆分、缓存投毒、会话固定或跳转劫持。",
     "对写入响应头的用户输入过滤 CR/LF 字符，使用框架提供的安全 Header API，避免手工拼接响应头。",
     ["https://owasp.org/www-community/vulnerabilities/CRLF_Injection"]),
    ("命令注入", 20, 10,
     "应用将用户输入拼接进操作系统命令并交由 shell 执行，攻击者可注入命令分隔符执行任意系统命令。",
     "可直接获取服务器操作系统权限、读取或删除任意文件、横向渗透内网，危害极其严重。",
     "避免调用系统 shell，改用语言内置 API；必须调用时使用参数数组方式并对参数做严格白名单校验，禁止拼接。",
     ["https://owasp.org/www-community/attacks/Command_Injection"]),
    ("代码执行", 25, 10,
     "应用将用户输入传入 eval、反序列化、模板引擎等动态执行入口，攻击者可注入并执行任意应用层代码。",
     "可完全控制应用进程、读取内存敏感数据、执行系统命令，进而完全接管服务器。",
     "禁止将用户输入传入动态执行函数；使用安全的沙箱或白名单机制；及时更新存在 RCE 漏洞的框架组件。",
     ["https://owasp.org/Top10/A03_2021-Injection/"]),
    ("模板注入SSTI", 25, 10,
     "应用将用户输入拼接进服务端模板并渲染，攻击者可注入模板表达式访问对象属性乃至执行代码。",
     "可读取应用配置与敏感变量，多数模板引擎场景可进一步升级为远程代码执行。",
     "不将用户输入作为模板内容渲染，改为作为数据变量传入；使用沙箱模式并禁用危险内置对象。",
     ["https://portswigger.net/web-security/server-side-template-injection"]),
    ("反序列化漏洞", 25, 10,
     "应用对不可信来源的序列化数据直接反序列化，攻击者可构造恶意对象在反序列化过程中触发危险逻辑链（gadget chain）。",
     "可导致远程代码执行、拒绝服务或权限提升，是 Java、PHP、Python 等平台的高危攻击面。",
     "避免反序列化不可信数据；使用 JSON 等纯数据格式替代原生序列化；启用反序列化白名单与完整性校验（签名）。",
     ["https://owasp.org/www-community/vulnerabilities/Deserialization_of_untrusted_data"]),
    ("本地文件包含LFI", 30, 20,
     "应用根据用户可控参数包含本地文件且未做限制，攻击者可通过目录穿越包含任意本地文件。",
     "可读取源代码、配置文件与系统敏感文件，结合日志投毒或会话文件可能升级为代码执行。",
     "对包含路径做白名单映射，禁止使用用户输入直接拼接文件路径，过滤 ../ 等穿越序列。",
     ["https://owasp.org/www-community/attacks/Path_Traversal"]),
    ("远程文件包含RFI", 30, 10,
     "应用允许包含远程 URL 指向的文件，攻击者可托管恶意脚本诱使服务端加载执行。",
     "可直接导致远程代码执行，完全控制服务器。",
     "禁用远程文件包含配置（如 PHP 的 allow_url_include），对包含源做白名单校验。",
     ["https://owasp.org/www-community/attacks/Remote_File_Inclusion"]),
    ("目录穿越", 35, 20,
     "应用在文件读写操作中直接使用用户输入构造路径，攻击者通过 ../ 序列访问预期目录之外的文件。",
     "可读取或写入服务器任意文件，导致源码泄露、配置泄露乃至文件覆盖。",
     "对文件名做白名单校验，规范化路径后校验是否位于允许目录内，避免直接拼接用户输入。",
     ["https://portswigger.net/web-security/file-path-traversal"]),
    ("任意文件读取", 35, 20,
     "应用提供文件下载或读取功能但未校验路径归属，攻击者可指定任意路径读取服务器文件。",
     "可窃取源代码、数据库配置、密钥凭证等敏感文件，为后续攻击提供关键信息。",
     "使用文件 ID 到真实路径的服务端映射，对路径做规范化与归属校验，限制可访问目录。",
     ["https://owasp.org/www-community/attacks/Path_Traversal"]),
    ("任意文件下载", 35, 30,
     "文件下载接口直接接收文件路径参数且缺少校验，攻击者可下载 Web 目录外的任意文件。",
     "可导致敏感配置、备份文件、源代码泄露。",
     "对下载资源使用白名单或 ID 映射，禁止路径参数直传，校验最终路径位于受控目录。",
     ["https://owasp.org/www-community/attacks/Path_Traversal"]),
    ("任意文件删除", 35, 20,
     "文件删除接口未校验目标路径归属，攻击者可构造路径删除服务器上的任意文件。",
     "可删除关键业务文件或系统文件，造成业务中断，甚至通过删除校验文件绕过安全机制。",
     "对删除目标做白名单与归属校验，规范化路径后确认位于允许目录，记录删除操作审计日志。",
     ["https://owasp.org/www-community/attacks/Path_Traversal"]),
    ("任意文件上传", 60, 10,
     "文件上传功能未校验文件类型与内容，攻击者可上传 WebShell 等可执行脚本文件。",
     "可直接获取服务器命令执行权限，是最常见的服务器沦陷入口之一。",
     "对上传文件做扩展名与 MIME 白名单校验、重命名存储、存储目录禁用执行权限、校验文件内容魔术字节。",
     ["https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload"]),
    ("文件上传绕过", 60, 10,
     "上传校验逻辑存在缺陷（仅前端校验、大小写绕过、双扩展名、截断等），攻击者可绕过限制上传恶意文件。",
     "可绕过防护上传 WebShell，导致服务器被控制。",
     "校验逻辑全部在服务端执行，采用白名单与内容检测双重校验，统一重命名并隔离存储，禁用上传目录脚本解析。",
     ["https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload"]),
    ("未授权访问", 40, 20,
     "接口或页面未做任何身份认证即可访问，攻击者无需登录即可直接调用敏感功能或读取数据。",
     "可导致敏感数据泄露、管理功能被匿名调用，是权限体系失效的典型表现。",
     "所有敏感接口强制身份认证，采用统一鉴权中间件默认拒绝，杜绝遗漏；对内部接口做网络隔离。",
     ["https://owasp.org/Top10/A01_2021-Broken_Access_Control/"]),
    ("水平越权", 40, 20,
     "应用未校验资源归属，攻击者通过修改对象 ID 等标识可访问同级别其他用户的数据。",
     "可越权读取或修改其他用户的隐私数据、订单、消息等，造成大规模数据泄露。",
     "对每次数据访问校验资源所有者与当前用户一致；使用不可预测的资源标识；服务端强制做归属校验。",
     ["https://owasp.org/Top10/A01_2021-Broken_Access_Control/"]),
    ("垂直越权", 40, 10,
     "低权限用户可访问仅应由高权限角色使用的功能或接口，权限校验缺失或仅在前端实现。",
     "普通用户可执行管理员操作（如用户管理、系统配置），导致权限体系整体失守。",
     "服务端对每个敏感接口做基于角色/权限点的强制校验，采用默认拒绝的 RBAC 模型，前端隐藏不能替代后端校验。",
     ["https://owasp.org/Top10/A01_2021-Broken_Access_Control/"]),
    ("弱口令", 65, 20,
     "系统账号使用弱密码或默认密码，可被字典或暴力破解轻易猜解。",
     "攻击者可直接登录系统获取相应权限，弱口令的管理员账号将导致系统完全失守。",
     "强制密码复杂度策略与最短长度，禁用默认口令，启用登录失败锁定与二次认证，定期强制改密。",
     ["https://owasp.org/www-community/vulnerabilities/Weak_password_requirements"]),
    ("默认口令", 65, 20,
     "设备或系统保留出厂/安装时的默认账号密码未及时修改，攻击者可查阅公开文档直接登录。",
     "可直接获得管理权限，常见于中间件控制台、数据库、网络设备。",
     "上线前强制修改所有默认口令，删除或禁用示例账号，将默认口令检查纳入上线基线核查。",
     ["https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password"]),
    ("暴力破解", 65, 30,
     "登录、验证码等认证接口未做失败次数限制，攻击者可通过自动化工具高频尝试猜解凭证。",
     "可破解出有效账号口令，进而登录系统实施后续攻击。",
     "对认证接口增加失败次数锁定、图形/滑动验证码、IP 与账号维度速率限制，并对异常登录告警。",
     ["https://owasp.org/www-community/attacks/Brute_force_attack"]),
    ("会话固定", 45, 30,
     "用户登录后服务端未更换会话标识，攻击者可预先诱导受害者使用已知 Session ID 登录后劫持会话。",
     "攻击者可获取受害者的登录态，冒充其身份操作。",
     "登录成功后强制重新生成 Session ID，会话标识使用高熵随机值并设置合理过期时间。",
     ["https://owasp.org/www-community/attacks/Session_fixation"]),
    ("会话劫持", 45, 20,
     "会话凭证在传输或存储中缺乏保护，攻击者可窃取有效会话标识冒用用户身份。",
     "可完全接管受害者会话，执行其权限范围内的任意操作。",
     "全站启用 HTTPS，Cookie 设置 Secure、HttpOnly、SameSite 属性，缩短会话有效期并支持主动失效。",
     ["https://owasp.org/www-community/attacks/Session_hijacking_attack"]),
    ("逻辑漏洞", 45, 20,
     "业务流程设计缺陷导致校验可被绕过，如订单金额篡改、验证步骤跳过、并发条件竞争等。",
     "可造成资金损失、薅羊毛、绕过关键业务校验，危害与具体业务强相关。",
     "对关键业务流程做服务端完整性与顺序校验，金额等敏感数据以服务端为准，防范并发竞争。",
     ["https://owasp.org/www-community/vulnerabilities/Business_logic_vulnerability"]),
    ("支付金额篡改", 45, 10,
     "支付流程中金额、数量等参数由客户端提交且服务端未复核，攻击者可篡改为任意值。",
     "可实现 1 元购买高价商品等资金损失，直接造成经济损失。",
     "所有价格与金额以服务端数据为准重新计算，对订单做完整性签名校验，禁止信任客户端提交的金额。",
     ["https://owasp.org/www-community/vulnerabilities/Business_logic_vulnerability"]),
    ("验证码绕过", 45, 30,
     "验证码机制存在缺陷，如可重复使用、服务端不校验、可空值绕过或响应中回显答案。",
     "可绕过人机校验实施暴力破解、短信轰炸、批量注册等自动化攻击。",
     "验证码一次一用、服务端强制校验且用后即失效，禁止在响应中返回答案，结合频率限制使用。",
     ["https://owasp.org/www-community/controls/Blocking_Brute_Force_Attacks"]),
    ("短信轰炸", 45, 30,
     "短信/邮件发送接口未做频率限制，攻击者可高频调用向指定号码发送大量验证码。",
     "可对目标用户实施骚扰轰炸，消耗企业短信费用，影响业务信誉。",
     "对发送接口按手机号、IP、设备维度做频率与总量限制，增加图形验证码与滑块校验。",
     ["https://owasp.org/www-community/controls/Blocking_Brute_Force_Attacks"]),
    ("敏感信息泄露", 55, 20,
     "应用在页面、接口响应、日志或错误信息中暴露敏感数据（密钥、身份证号、内部路径等）。",
     "泄露的信息可被攻击者用于进一步攻击或直接造成隐私合规风险。",
     "对敏感字段脱敏展示，关闭生产环境详细报错，清理调试接口与注释，加强日志中的敏感信息过滤。",
     ["https://owasp.org/Top10/A02_2021-Cryptographic_Failures/"]),
    ("源代码泄露", 55, 30,
     "备份文件、版本控制目录（.git/.svn）或配置文件可被直接访问下载。",
     "攻击者可获取完整源代码与配置，分析出更多漏洞并窃取硬编码的密钥。",
     "禁止在 Web 目录存放备份与版本控制目录，服务器配置拒绝访问敏感后缀与隐藏目录。",
     ["https://owasp.org/www-project-web-security-testing-guide/"]),
    ("信息泄露-报错回显", 55, 40,
     "生产环境返回详细的异常堆栈或数据库错误信息。",
     "暴露技术栈、路径、SQL 语句等内部信息，辅助攻击者构造精准攻击。",
     "生产环境统一返回友好错误页，关闭调试模式，将详细错误仅记录到服务端日志。",
     ["https://owasp.org/www-community/Improper_Error_Handling"]),
    ("目录遍历列表", 55, 40,
     "Web 服务器开启了目录浏览功能，访问无索引页的目录时列出全部文件。",
     "暴露目录结构与文件清单，可能泄露备份、配置等敏感文件。",
     "关闭 Web 服务器的目录列表功能（如 Apache Options -Indexes、Nginx autoindex off）。",
     ["https://owasp.org/www-community/attacks/Forced_browsing"]),
    ("点击劫持", 55, 40,
     "页面未限制被 iframe 嵌套，攻击者可用透明层覆盖诱导用户点击执行非预期操作。",
     "可诱骗用户完成点赞、授权、转账等操作，用户以为在操作正常页面。",
     "设置 X-Frame-Options 为 DENY/SAMEORIGIN，或使用 CSP 的 frame-ancestors 指令限制嵌套来源。",
     ["https://owasp.org/www-community/attacks/Clickjacking"]),
    ("URL重定向漏洞", 45, 40,
     "跳转功能的目标地址由用户参数控制且未校验，攻击者可构造跳转到外部恶意站点的链接。",
     "常用于钓鱼攻击，借助可信域名诱导用户跳转到仿冒页面。",
     "对跳转目标做白名单校验，仅允许站内地址或预置的可信域名，避免开放式重定向。",
     ["https://owasp.org/www-community/attacks/Unvalidated_Redirects_and_Forwards"]),
    ("JWT安全漏洞", 45, 20,
     "JWT 实现存在缺陷，如接受 alg=none、使用弱密钥、不校验签名或密钥硬编码。",
     "攻击者可伪造任意用户的 Token 实现身份伪造与权限提升。",
     "固定并强制校验签名算法，使用高强度密钥且妥善保管，校验有效期与签发者，敏感场景引入吊销机制。",
     ["https://owasp.org/www-project-web-security-testing-guide/"]),
    ("越权修改密码", 40, 10,
     "改密接口未校验旧密码或未绑定当前会话用户，攻击者可指定任意用户 ID 重置其密码。",
     "可接管任意账号包括管理员，导致系统被完全控制。",
     "改密时强制校验旧密码或有效重置凭证，目标账号绑定当前会话，禁止通过参数指定他人账号。",
     ["https://owasp.org/Top10/A01_2021-Broken_Access_Control/"]),
    ("后门程序", 50, 10,
     "系统中存在预留或被植入的后门代码/账号，可绕过正常认证直接控制系统。",
     "攻击者可随时隐蔽地获取系统权限，持久化控制且难以察觉。",
     "对代码与服务器做完整性核查与恶意代码扫描，清理可疑账号与计划任务，加强供应链与代码审计。",
     ["https://owasp.org/www-community/attacks/"]),
    ("WebShell", 50, 10,
     "服务器上存在攻击者上传的可执行脚本木马，通过 Web 请求即可执行系统命令。",
     "攻击者可完全控制服务器、窃取数据、作为跳板横向渗透内网。",
     "清除木马文件并溯源上传入口，修复文件上传与命令执行漏洞，上传目录禁用脚本解析，部署 WAF 与文件监控。",
     ["https://owasp.org/www-community/attacks/"]),
    ("CORS配置错误", 55, 30,
     "跨域资源共享策略配置过于宽松，如允许任意 Origin 且携带凭证。",
     "攻击者站点可通过用户浏览器跨域读取受害者的敏感数据。",
     "严格配置允许的 Origin 白名单，避免将 Access-Control-Allow-Origin 设为通配同时允许携带凭证。",
     ["https://portswigger.net/web-security/cors"]),
    ("HTTP请求走私", 75, 20,
     "前后端服务器对请求边界（Content-Length 与 Transfer-Encoding）解析不一致，攻击者可走私隐藏请求。",
     "可绕过安全控制、投毒缓存、劫持其他用户请求或获取敏感数据。",
     "统一前后端 HTTP 解析行为，拒绝同时包含冲突长度头的请求，尽量使用 HTTP/2 端到端。",
     ["https://portswigger.net/web-security/request-smuggling"]),
    ("组件已知漏洞", 70, 20,
     "应用依赖的第三方框架或组件存在已公开的漏洞且未及时升级修复。",
     "攻击者可直接利用公开 EXP 攻击，危害取决于组件漏洞类型，严重者可远程代码执行。",
     "建立依赖清单（SBOM）与漏洞监控，及时升级到安全版本，移除不必要的组件，使用软件成分分析工具。",
     ["https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/"]),
    ("拒绝服务DoS", 45, 30,
     "应用缺乏资源与频率限制，攻击者可构造高消耗请求耗尽服务端 CPU、内存或连接资源。",
     "可导致服务不可用，影响正常业务，正则回溯、大文件解析等场景尤为突出。",
     "对请求做限流与超时控制，限制上传与解析规模，规避 ReDoS 正则，关键服务做资源隔离与弹性扩容。",
     ["https://owasp.org/www-community/attacks/Denial_of_Service"]),
]


async def main() -> None:
    from sqlalchemy import select

    from app.constants import VUL_LEVEL, VUL_TYPE
    from app.db import async_session_maker, init_db
    from app.models import KnowledgeEntry
    from app.models.user import User

    await init_db()

    # 校验字典码，避免录入非法数据
    for name, vt, sl, *_ in SEED_DATA:
        assert vt in VUL_TYPE, f"{name}: 非法漏洞类型 {vt}"
        assert sl in VUL_LEVEL, f"{name}: 非法危害等级 {sl}"

    async with async_session_maker() as session:
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        creator_id = admin.id if admin else None
        username = (admin.realname or admin.username) if admin else "system"

        existing = {
            e.vulnerability_name: e
            for e in (await session.execute(select(KnowledgeEntry))).scalars().all()
        }
        created = updated = 0
        for name, vt, sl, desc, harm, sol, refs in SEED_DATA:
            entry = existing.get(name)
            if entry is None:
                entry = KnowledgeEntry(vulnerability_name=name)
                session.add(entry)
                created += 1
            else:
                updated += 1
            entry.vul_type = vt
            entry.severity_level = sl
            entry.description_html = f"<p>{desc}</p>"
            entry.harm_html = f"<p>{harm}</p>"
            entry.solution_html = f"<p>{sol}</p>"
            entry.references = list(refs)
            entry.creator_id = creator_id
            entry.username = username
        await session.commit()

    print(f"知识库预置完成：新增 {created} 条，更新 {updated} 条，共 {len(SEED_DATA)} 条。")


if __name__ == "__main__":
    asyncio.run(main())
