# 虚拟机部署记录（2026-10-22）

当前方式：CentOS 7 虚拟机运行 MySQL / Redis / PostgreSQL / Qdrant，Windows 运行 Java、Python 和前端。适用于当前电脑的开发与演示；没有开放公网服务。

## 最简启动

先在 VMware 启动虚拟机，IP 为 192.168.100.128。Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Users\31895\Documents\New project\Enterprise-Support-Agent\scripts\start-vm-demo.ps1'
```

等待后访问 http://127.0.0.1:5175 。登录账号和随机密码仍在 `.local-run/login-accounts.txt`。脚本后台启动服务，日志在 `.local-run/*-launcher.*.log`。若端口已监听，脚本不再启动第二份进程。

## 虚拟机部署

目录 `/opt/enterprise-support-agent/infra`；Compose 项目名 `esa-vm`。Docker 已启用开机启动，容器使用 `restart: unless-stopped`。

| 组件 | 镜像 | SSH 隧道本地端口 | 用途 |
| --- | --- | --- | --- |
| MySQL | mysql:8.4.11 | 23306 | 订单、账号、Flyway 迁移 |
| PostgreSQL | postgres:17.6-alpine | 25432 | 会话归属、LangGraph checkpoint |
| Redis | redis:8.4.6-alpine | 26379 | JWT 黑名单、幂等、限流、订单缓存 |
| Qdrant | qdrant/qdrant:v1.18.2 | 26333 | 政策的稠密向量和 BM25 索引 |

虚拟机原有 3306、6379、8080 服务未替换。每个新组件使用独立命名卷 `esa-vm_*_data`，Redis 使用 AOF / always / noeviction。

宿主端口绑定 127.0.0.1，通过 SSH 隧道连接，组件均设置密码或 API key。本机凭据在 Git 忽略的 `.local-run/vm.env`，远端 `.env` 权限 600；未将模型 API Key 上传到虚拟机。SSH 公钥由用户手动授权，仅允许 192.168.100.1 来源。

Docker 26 的回环发布存在旧版本网络边界限制，因此这里同时使用组件认证和 SSH；不把该环境描述成已达到生产安全基线。官方说明：[Docker 端口发布](https://docs.docker.com/engine/network/port-publishing/)、[Qdrant 安全配置](https://qdrant.tech/documentation/security/)。

## 数据和模型

- 原 PostgreSQL 的 10 个会话、64 个 checkpoint 及相关写入数据已备份、迁移，迁移前后每张表行数一致。
- 原本机 Redis 中 `esa:*` 有效键为 0，没有遗留幂等记录需要复制。
- Java 从 H2 演示库切换为持久 MySQL；初始化项目订单和两个已有演示账号，四个 Flyway 迁移成功。
- Qdrant 集合 `enterprise_support_knowledge_hybrid_vm_v1`：company_001 两份政策文档、9 个片段，使用 384 维 dense + BM25；Cross-Encoder 已启用。
- Embedding 使用本机 Hugging Face 缓存；BM25、Reranker 缓存在 `.local-run/model-cache/fastembed`，不依赖临时目录。
- 切换前配置与 PostgreSQL dump 路径记录在 `.local-run/vm-backup-path.txt`。原本机数据库目录保留，不删除。

## 验证

17 项认证链路检查通过；10 项 VM 联调检查通过：真实 RAG 答案及来源、JWT、订单、PostgreSQL 会话、退款 interrupt/取消 resume、Qdrant 拒绝匿名请求。未批准退款或产生实际资金操作。

四个容器重启后，PG 行数、Qdrant 9 个片段、Redis 验证键和 JWT 黑名单仍保留。应用重新启动后再验证业务链路。报告位于 `.local-run/vm-migration-result.json`、`vm-integration-result.json`、`vm-persistence-result.json`。

复验：`python scripts/verify-auth.py` 和 `python scripts/verify-vm.py`。这是当前本机配置下的联调脚本，会调用模型并创建演示会话。

## 常用维护命令（FinalShell）

```bash
cd /opt/enterprise-support-agent/infra
docker compose ps
docker compose logs --tail 80
docker compose up -d
docker compose stop
```

不要使用 `docker compose down -v`：它会删除持久数据卷。正式部署前应升级已停止维护的 CentOS 7，并配置生产级密钥管理、备份、监控与 TLS。
