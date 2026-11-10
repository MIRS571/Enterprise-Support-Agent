# 登录、可信身份与退出黑名单

> 2026-10-22 更新：已迁移到虚拟机 MySQL / Redis / PostgreSQL / Qdrant，RAG 已启用；启动与当前端口以 [虚拟机部署说明](vm-deployment.md) 为准。下文 2026-10-21 的 H2、16380 和 RAG 关闭描述为当时的本机基线。

2026-10-21：已实现并在 Windows 本地联调。本次没有安装 Linux / Docker，也未验证 Compose 全栈启动。

## 真实调用链

浏览器提交用户名/密码 → Node 同源代理 → Java 登录接口查 `auth_accounts` 并校验 BCrypt → 签发 JWT → 浏览器请求携带 Bearer → Spring Security 验签、issuer/audience/exp 校验、Redis 黑名单与账号启用状态校验 → 从数据库账号构造 Actor → Java 将可信身份传给 Python → Python 调 Java 内部订单接口。

外部传入 `X-Tenant-Id` / `X-User-Id` 不参与公共接口认证。普通用户 JWT 不能访问内部接口。`/internal/v1/orders/**` 必须有服务端保存的内部服务令牌，并再次校验账号和订单归属。前端不接收模型密钥、JWT 签名密钥或内部令牌。模型输入中的身份声明没有授权作用。

## 接口

| 方法与路径 | 行为 |
| --- | --- |
| POST /api/v1/auth/login | username/password；返回 access_token、expires_at 和用户信息 |
| GET /api/v1/auth/me | Bearer JWT；返回当前可信 Actor |
| POST /api/v1/auth/logout | Bearer JWT；撤销当前 token，成功后前端清除会话凭证 |
| /api/v1/orders/**、/api/v1/agent/** | 必须通过认证并有 CUSTOMER 角色；订单和会话继续做归属校验 |

未登录/过期/伪造/退出后凭证返回 401，无角色返回 403，不属于自己的订单或会话返回 404。Redis 或账号存储不可用时返回 503，不能绕过认证；退出失败时前端保留会话并明确提示重试。

登录按账号与来源 IP 做 Redis 原子计数限流（每分钟分别 20 / 100 次）。目前 Node 代理到 Java 的来源都是回环地址，IP 限流是本机总量限制；生产需配置可信代理和真实来源策略，不能直接信任任意 X-Forwarded-For。

## 黑名单为什么不影响重新登录

每次登录生成独立随机 jti。退出写入 `esa:auth:revoked:{jti}`，TTL 为这个 token 的剩余有效时间，默认 token 有效期 3600 秒。只撤销当前 token，不封禁账号，不撤销同用户其他独立登录。重新登录产生新 jti，因此仍能登录。

服务端先成功写黑名单，再返回退出成功。HTTP 响应丢失时，旧 token 再请求会得到 401，前端回到登录页。正在执行的请求/SSE 不会因退出被自动取消；黑名单用于后续鉴权，也不代替退款幂等与订单状态条件更新。

## 本机启动与账号

PowerShell 在项目根目录依次启动：

```powershell
.\.local-run\start-postgres.ps1
.\scripts\start-auth-redis.ps1
# 以下三个长期运行命令分别使用不同终端，或使用现有 IDE 配置
.\.local-run\start-business.ps1
.\.local-run\start-agent.ps1
.\scripts\start-frontend.ps1
```

访问 http://127.0.0.1:5175 。`customer1` 对应 company_001/U1001，拥有 A1001/A1002；`customer2` 对应 company_001/U2002，拥有 B2001。随机密码保存在被 Git 忽略的 `.local-run/login-accounts.txt`，不要复制到提交或报告中。账号是服务器数据库记录，不是浏览器任选身份。

Java `.env.local` 已配置 AUTH_JWT_SECRET、AUTH_BOOTSTRAP_ENABLED=true 和两组 AUTH_BOOTSTRAP_PASSWORD / AUTH_BOOTSTRAP_SECOND_PASSWORD。IDEA 的 Business Local 配置同步这些值。Bootstrap 默认关闭，只适合本地演示；现有账号不会在重启时被覆盖密码。

其他机器：自行提供至少 32 字节随机 JWT 密钥、与 Python 一致的 AGENT_INTERNAL_SERVICE_TOKEN、Redis 连接配置。仓库不包含便携 Redis 二进制和本机密码；可连接已有 Redis，并设置 BUSINESS_REDIS_HOST/PORT/PASSWORD。Compose 已补齐必需 AUTH_JWT_SECRET 环境变量，未执行容器部署。正式账号应由受控运维流程写入 BCrypt 密码哈希，不提供开放注册/任意角色创建接口。

## 持久化与边界

- JWT 只保存在浏览器 sessionStorage。localStorage 展示历史按 tenantId/userId 分开；这仅是 UI 隔离，不是加密存储，共用电脑仍应清理浏览器数据。
- Java 本机仍使用 H2 内存库，重启会重置演示账号/订单，bootstrap 从本机配置重新创建账号；生产应使用持久 MySQL。
- PostgreSQL 保存会话/checkpoint。独立 Redis 16380 保存黑名单和 Java 幂等数据，AOF `appendfsync always`、noeviction，数据目录 `.local-run/auth-redis`。不要清库、删卷或淘汰撤销记录，否则尚未自然过期的旧 token 可能重新有效。
- Redis 当前仅监听回环地址，不与勤工助学 Redis 混用。生产仍需 TLS、访问控制、密钥轮换、备份和监控；本次未实现 refresh token、注册或找回密码。
- RAG 和 Python Redis 缓存本机仍关闭；Java 黑名单使用 Redis 不代表 RAG 已启用。退款资金到账未在此次测试范围内。

## 验证与复现

- Java：42 项测试通过，包含未登录、伪造头、签名/过期/audience、账号停用、角色、跨用户/租户、内部服务边界、Redis 故障、logout 和 SSE 404 错误透传。打包成功。
- Python：189 项测试通过，包括内部接口认证客户端、评测请求使用 JWT 且拒绝缺失身份凭证；日志 `.local-run/auth-python-tests.log`。
- 前端：6 项测试，含代理只转发 Authorization、不暴露内部接口；浏览器实测错误密码、登录订单查询、退出、刷新、切换账号与历史隔离。
- 执行 `python scripts/verify-auth.py`：读取本机私有配置，通过真实前端代理 / Java / Python / Redis / 模型验证 17 项认证与 SSE 检查，报告 `.local-run/auth-smoke-result.json`；不执行退款确认。
- 旧 21 请求评测脚本现要求 AGENT_EVAL_IDENTITY_TOKENS 环境变量，内容为 JSON 对象 `{"tenant/user":"该账号登录获得的 JWT"}`，每个用例身份必须有独立正确凭证。评测账号与业务数据需预先受控配置；本次没有重跑该历史评测，也没有以客户端身份头绕过认证。

实现基于 Spring Security JWT 能力：[官方文档](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)。
