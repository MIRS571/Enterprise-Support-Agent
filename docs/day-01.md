# 第一天：建立可运行骨架

## 今日目标

- [x] 明确 Java 与 Python 的职责边界
- [x] 创建两个独立服务目录
- [x] 初始化独立 Git 仓库
- [x] Java 健康检查通过
- [x] Python 健康检查通过
- [x] 两侧自动化测试通过

## 今天不做什么

不接入 LLM、LangChain、LangGraph、Redis 和数据库。工程骨架不稳定时加入这些依赖，会让错误来源难以判断。

## 必须理解的四个问题

1. 为什么 Agent 不应该直接连接订单数据库？
2. 为什么健康检查不等于业务接口？
3. 为什么 API 路径使用 `/api/v1`？
4. 为什么 Java 和 Python 服务需要独立启动、独立测试？

## 验收接口

```text
GET http://127.0.0.1:8080/actuator/health
GET http://127.0.0.1:8080/api/v1/system/info
GET http://127.0.0.1:8000/api/v1/health
```

## 实际验收结果

```text
Python /api/v1/health       -> 200, status=UP
Python /docs                -> 200
Java /actuator/health       -> 200, status=UP
Java /api/v1/system/info    -> 200, status=UP
Python pytest               -> 1 passed
Java Maven test             -> 2 passed
```
