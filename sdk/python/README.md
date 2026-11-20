# AI SOP Python SDK

零依赖客户端，只使用标准库，适用于 MES / ERP 侧脚本、定时任务与数据同步。

## 安装

把 `ai_sop_client.py` 拷到你的项目里即可，无需 pip 安装。

## 快速开始

```python
from ai_sop_client import AiSopClient, AiSopError

client = AiSopClient("http://localhost:8000", api_key="sk_xxxxxxxx")

print(client.list_sop())
print(client.analytics_overview(days=7))

for record in client.iter_execution(limit=50):
    payload = client.mes_payload(record["id"])
    # 推送给你自己的 MES / ERP
```

## 获取 API Key

在系统里用租户管理员登录后调用（JWT 鉴权）：

```bash
curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "MES 对接", "scopes": ["read"]}'
```

响应中的 `key` 只返回一次，请立即保存。

## 错误处理

所有非 2xx 响应统一抛 `AiSopError`，包含状态码与服务端返回的 detail。
