# 本地基础设施

当前通过同一个 Compose 文件管理 MySQL、Qdrant、PostgreSQL、Redis、Java 业务服务和 Python Agent 服务。

## Rocky Linux 启动 MySQL

将 `infra` 目录上传到 Rocky Linux，然后执行：

```bash
cd infra
cp .env.example .env
vim .env
sudo docker compose up -d mysql
sudo docker compose ps
sudo docker compose logs --tail=100 mysql
```

必须修改 `.env` 中的两个密码。`.env` 已被 Git 忽略，不要提交真实密码。

查看虚拟机地址：

```bash
hostname -I
```

在 Windows PowerShell 检查端口：

```powershell
Test-NetConnection <虚拟机IP> -Port 3306
```

## Windows 启动 Java 并连接 MySQL

```powershell
$env:SPRING_PROFILES_ACTIVE="mysql"
$env:BUSINESS_DB_URL="jdbc:mysql://<虚拟机IP>:3306/agent_business?useUnicode=true&characterEncoding=utf8&serverTimezone=UTC"
$env:BUSINESS_DB_USERNAME="agent"
$env:BUSINESS_DB_PASSWORD="与 infra/.env 中 MYSQL_PASSWORD 相同的密码"
.\mvnw.cmd spring-boot:run
```

Java 启动时 Flyway 会自动执行 `db/migration` 中尚未执行的迁移。

## Rocky Linux 启动 Qdrant

```bash
cd infra
sudo docker compose up -d qdrant
sudo docker compose ps
sudo docker compose logs --tail=100 qdrant
curl http://127.0.0.1:6333
```

Qdrant 开发环境使用 REST 端口 `6333`，管理页面地址为：

```text
http://<虚拟机IP>:6333/dashboard
```

Qdrant 默认没有启用身份认证，不应直接向不受信任的网络开放。需要从 Windows 访问虚拟机时，只允许 Windows 主机地址访问 `6333`：

```bash
sudo firewall-cmd --zone=public --permanent \
  --add-rich-rule='rule family="ipv4" source address="<Windows主机IP>/32" port port="6333" protocol="tcp" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --zone=public --list-rich-rules
```

当前 Python 客户端使用 REST，因此暂不向宿主机暴露 gRPC 端口 `6334`。
