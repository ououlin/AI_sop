# 开放平台接入指南

> 面向 MES / ERP / BI 等第三方系统。所有接口位于 `/api/v1/open`，用 `X-API-Key` 鉴权，租户由 Key 决定。

## 1. 接入流程

1. 租户管理员登录后创建 API Key（`POST /api/v1/api-keys`），保存返回的 `key`（只返回一次）
2. 调用方每次请求带 `X-API-Key: sk_xxx`
3. 需要实时事件时，创建 Webhook 订阅（`POST /api/v1/webhooks`）
4. 生产环境建议为每个集成方单独建 Key，便于审计与单独吊销

## 2. 开放接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/open/sop` | SOP 列表（含步骤数） |
| GET | `/open/execution?status=&page=&limit=` | 执行记录分页 |
| GET | `/open/execution/{id}` | 执行详情（含步骤与质量标记） |
| GET | `/open/mes/execution/{id}` | MES 报文（适配层显式出口） |
| GET | `/open/analytics/overview?days=` | OEE / FPY / CT / DPMO / MTBF |

```bash
curl http://localhost:8000/api/v1/open/execution?limit=5 \
  -H "X-API-Key: sk_xxxxxxxx"
```

## 3. Webhook 事件

| 事件 | 触发时机 |
|------|----------|
| `execution.started` | 一次 SOP 执行开始 |
| `execution.completed` | 执行正常结束 |
| `execution.failed` | 执行异常结束（error / interrupted） |
| `alarm.triggered` | 告警触发（v1 预留，未接入投递） |

投递格式：

```json
{
  "event": "execution.completed",
  "data": { "record_id": 42, "status": "completed", "duration_sec": 61.2 }
}
```

请求头：

- `X-AI-SOP-Event`：事件名
- `X-AI-SOP-Signature: sha256=<HMAC-SHA256(body, secret)>`（订阅时配置 secret 才携带）

验签示例（Python）：

```python
import hashlib, hmac

body = request.get_data()
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
provided = request.headers["X-AI-SOP-Signature"].split("=", 1)[1]
assert hmac.compare_digest(expected, provided)
```

投递策略：3 秒超时、最多重试 3 次（间隔 0.5s / 1.0s 递增）、独立线程执行；
失败只记录在 `/api/v1/webhooks/deliveries/recent`（内存最近 50 条，含 `attempts` 与 `detail`），不阻塞识别主链路。

## 4. MES 报文结构

`/open/mes/execution/{id}` 返回通用骨架，字段映射可按厂商适配：

```json
{
  "source": "ai_sop",
  "schema_version": "1.0",
  "execution": { "id": 42, "sop_name": "装配工序", "status": "completed",
                 "start_time": "...", "end_time": "...", "cycle_time_sec": 61.2 },
  "steps": [ { "index": 0, "name": "取料", "status": "completed",
               "duration_sec": 12.0, "completed_at": "..." } ],
  "quality": { "defect_steps": 0, "passed": true }
}
```

## 5. 配额与限制

- API Key 属于租户，只能看到该租户数据
- 分页 `limit` 上限 100，分析接口 `days` 上限 90
- 限流：每个 API Key 默认 120 次/分钟（`OPEN_API_RATE_LIMIT_PER_MIN` 可调），
  超限返回 429 并带 `Retry-After`；限流为进程内计数，多实例部署时每实例独立配额
- Webhook 支持 HMAC-SHA256 签名与失败重试，当前只支持 http(s) 回调地址

## 6. SDK

见 [sdk/python/README.md](../sdk/python/README.md)。
