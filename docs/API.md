# REST API 参考

> 所有接口以 `/api/v1` 为前缀，JSON 收发。
> 认证：`Authorization: Bearer <token>` 或登录后写入的 HttpOnly Cookie。
> 返回码约定：`401` 未认证 / `402` 订阅到期只读 / `403` 无权限 / `409` 业务冲突 / `404` 不存在。

---

## 1. 系统

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/health` | 公开 | 健康检查 |

## 2. 认证与用户

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/auth/login` | 公开 | 登录，请求体 `{username, password, tenant}`；返回 Token 并写入 HttpOnly Cookie |
| POST | `/auth/logout` | 公开 | 退出，清除 Cookie |
| GET | `/auth/me` | 登录 | 当前用户（Cookie 与 Bearer 均可） |
| GET | `/auth/users` | `user:manage` | 本租户用户列表 |
| POST | `/auth/users` | `user:manage` | 创建用户（平台管理员角色仅平台管理员可创建） |
| DELETE | `/auth/users/{id}` | `user:manage` | 删除用户 |

## 3. SOP 管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/sop/list` | `sop:view` | 可用 SOP（文件 + 数据库） |
| GET | `/sop/file/{filename}` | `sop:view` | 读取 SOP 文件内容 |
| POST | `/sop/load` | `sop:execute` | 加载 SOP，请求体 `source`：`file:xxx.json` 或 `db:{id}` |
| POST | `/sop/start` | `sop:execute` | 开始 / 恢复 |
| POST | `/sop/pause` | `sop:execute` | 暂停 |
| POST | `/sop/reset` | `sop:execute` | 重置 |
| POST | `/sop/skip` | `sop:skip` | 跳过当前步骤 |
| GET | `/sop/status` | `sop:view` | 当前状态快照 |
| GET | `/sop/zones` | `sop:view` | 工作区域定义 |
| POST | `/sop/zones` | `camera:manage` | 更新工作区域（立即生效并落盘） |
| GET | `/sop/db/list` | `sop:view` | 数据库中的 SOP 列表 |
| GET | `/sop/db/{id}` | `sop:view` | 数据库 SOP 详情 |
| POST | `/sop/db/save` | `sop:edit` | 保存 SOP 到数据库（`activate` 可立即激活） |
| DELETE | `/sop/db/{id}` | `sop:delete` | 删除数据库 SOP |

## 4. 视频与摄像头

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/video/mjpeg` | 登录 | MJPEG 视频流 |
| GET | `/video/snapshot` | 登录 | 单帧快照 |
| GET | `/camera/list` | `camera:view` | 可用摄像头 |
| POST | `/camera/switch` | `camera:manage` | 运行时切换，请求体 `{index}` |

## 5. 执行记录

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/records/` | `record:view:own` 或 `record:view:all` | 分页查询（`status` / `sop_name` / `start_time` / `end_time` / `page` / `limit`） |
| GET | `/records/{id}` | 同上 | 记录详情与步骤明细 |

## 6. 质检报告与告警

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/reports/generate` | `record:export` | 生成 JSON 报告 |
| POST | `/reports/export/text` | `record:export` | 文本报告 |
| POST | `/reports/export/csv` | `record:export` | CSV 报告 |
| POST | `/reports/export/pdf` | `record:export` | PDF（需 `reportlab`） |
| POST | `/reports/export/excel` | `record:export` | Excel（需 `openpyxl`） |
| GET | `/reports/alarms` | `station:view` | 告警历史 |
| POST | `/reports/alarms/{id}/acknowledge` | `alarm:acknowledge` | 确认告警 |
| DELETE | `/reports/alarms` | `alarm:manage` | 清除活跃告警 |

## 7. 产线看板（中央聚合）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/station/report` | 公开（`X-Station-Key`） | 工位上报，按租户校验订阅与工位配额 |
| GET | `/stations` | `line:view` | 所有工位状态与摘要 |
| GET | `/stations/{id}` | `station:view` | 单工位详情 |
| DELETE | `/stations/{id}` | `station:manage` | 移除工位 |
| GET | `/line/summary` | `line:view` | 产线整体摘要 |

## 8. 租户与订阅（平台管理员）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/tenants` | `tenant:view` | 租户列表（含用户数） |
| POST | `/tenants` | `tenant:manage` | 开通租户并创建租户管理员 |
| GET | `/tenants/{id}` | `tenant:view` | 租户详情 |
| PATCH | `/tenants/{id}` | `tenant:manage` | 更新名称 / 状态（`active`、`suspended`）/ 套餐 |
| GET | `/tenants/{id}/subscription` | `tenant:view` | 套餐、配额与到期状态 |
| PUT | `/tenants/{id}/subscription` | `tenant:manage` | 变更套餐 / 设置到期时间（ISO 8601） |
| GET | `/plans` | `tenant:view` | 套餐目录 |

> 订阅到期后租户进入只读：GET 放行，写操作返回 402，续费接口例外；工位上报超过套餐上限返回 409。

## 9. 工序模板市场

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/marketplace/templates` | `sop:view` | 模板列表，`industry` 参数可按行业过滤 |
| GET | `/marketplace/templates/{template_id}` | `sop:view` | 模板详情（含完整步骤） |
| POST | `/marketplace/templates/{template_id}/apply` | `sop:edit` | 一键应用：写入本租户 SOP，`activate` 控制是否立即激活 |
| GET | `/marketplace/models` | `sop:view` | 检测模型目录 |

## 10. 设备运维

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/ops/devices` | `station:view` | 设备列表与健康摘要（healthy / warning / offline） |
| GET | `/ops/devices/{id}` | `station:view` | 设备详情、告警与命令记录 |
| POST | `/ops/devices/{id}/config` | `station:manage` | 下发配置（如 `report_interval`），下次心跳生效 |
| POST | `/ops/devices/{id}/upgrade` | `station:manage` | 下发模型升级命令（v1 重启后生效） |
| GET | `/ops/devices/{id}/commands` | `station:view` | 命令历史 |
| GET | `/ops/model-versions` | `station:view` | 可升级模型版本目录 |
| POST | `/station/ack` | 工位密钥 | 工位回执命令执行结果 |

> 工位上报 `POST /station/report` 的响应会带上 `commands`，工位据此执行并回执。

## 11. 数据分析

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/analytics/overview?days=7` | `record:view:all` | OEE / FPY / CT / DPMO / MTBF 汇总（1-90 天） |
| GET | `/analytics/trend?days=14` | `record:view:all` | 按自然日的执行量、完成数、FPY、平均节拍 |
| GET | `/analytics/steps?days=30&limit=10` | `record:view:all` | 瓶颈步骤排行（按平均耗时） |
| GET | `/analytics/sops?days=30` | `record:view:all` | SOP 维度对比（执行量 / FPY / 节拍） |

> OEE 为近似口径：可用率按统计窗口内的执行覆盖时长计算，窗口内运行时间不足时数值偏低属正常。

## 12. WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/video` | 推送带骨架标注的视频帧（JPEG 二进制），需登录 Cookie |
| `/ws/status` | 推送步骤状态更新（JSON），需登录 Cookie |


## 13. 错误响应

```json
{ "error": "未提供认证Token", "code": 401 }
```

业务异常使用 FastAPI 标准结构：

```json
{ "detail": "工位数量已达套餐上限 1（当前套餐：体验版）" }
```

## 14. SOP 定义格式

SOP 以 JSON 存放于 `sops/` 或数据库，字段如下：

| 字段 | 说明 |
|------|------|
| `sop_name` | 工序名称 |
| `version` | 版本号 |
| `steps[].step_id` | 步骤 ID |
| `steps[].name` | 步骤名称 |
| `steps[].target_zone` | 目标区域：`left_area` / `center_area` / `right_area` / `top_area` |
| `steps[].required_gesture` | 所需手势：`open` / `fist` / `pinch` / `point` / `unknown`（不限） |
| `steps[].hold_duration_sec` | 条件持续时长（秒），满足后判定完成 |
| `steps[].required_objects` | 要求物体：`class_name` / `target_zone` / `min_count` |
| `steps[].description` | 步骤描述 |

## 15. 角色与权限

| 角色 | 定位 | 权限点 |
|------|------|--------|
| `operator` | 操作员 | `sop:execute`、`sop:view`、`camera:view`、`video:view`、`record:view:own` |
| `supervisor` | 线长 | 操作员权限 + `sop:skip`、`record:view:all`、`record:export`、`alarm:acknowledge`、`station:view`、`line:view` |
| `admin` | 租户管理员 | SOP 编辑/删除、摄像头管理、用户管理、告警管理、产线看板 |
| `platform_admin` | 平台管理员 | `tenant:view`、`tenant:manage`、`user:manage`、`station:view`、`line:view` |
