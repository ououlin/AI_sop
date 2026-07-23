# AI SOP 装配线工序识别系统

> 基于 **MediaPipe 手部检测 + YOLOv8 物体检测 + 区域/手势/时序状态机** 的实时装配线工序识别系统。
>
> **当前阶段**：P2 识别精度与生产化已完成，P3 商业化与规模化规划中。

## 产品定位

面向中小制造企业的**轻量级SOP合规检查工具**，用摄像头+AI替代人工巡检，实时判断工人是否按SOP规范操作，实现装配过程的数字化追溯。

**差异化优势**：
- 轻量化：USB摄像头+普通PC即可部署，不依赖工业相机
- 低门槛：SOP可视化编辑，产线工程师可自助配置
- 快速迭代：基于MediaPipe，算法更新快
- 多工位：工位Agent+中央聚合服务+产线看板，支持产线级监控

## 功能特性

### 核心能力
- 海康USB摄像头实时采集（线程化低延迟，MSMF后端）
- MediaPipe 双手21点骨架检测与可视化
- 4种基础手势识别：张开 / 握拳 / 捏合 / 指向
- 工作区域划分（左/中/右），实时判断手部所在区域
- 工序步骤状态机：`待执行 → 进行中 → 已完成`，支持持续时长确认
- 实时视频流 + 步骤进度 WebSocket 推送

### 工程化特性（P0已完成）
- 全局异常处理中间件，统一错误响应格式
- 处理循环守护机制，崩溃自动重启
- 环境配置管理（`.env` 文件，多环境切换）
- 日志系统（控制台+文件双输出，按大小滚动）
- API版本化（`/api/v1/` 前缀，路由模块化）

### 功能增强（P1已完成）
- SQLite 数据库集成，SOP定义和执行记录持久化
- MJPEG 视频流，带宽降低 50%
- SOP 可视化编辑器（步骤增删改、属性配置）
- 执行记录查询（分页、筛选、详情）
- 摄像头运行时切换，无需重启服务

### 识别精度与生产化（P2已完成）
- **物体检测能力**：集成 YOLOv8（ObjectDetector），融合手部+物体多模态判定，降低误判率
- **异常告警系统**：AlarmManager 统一管理告警生命周期，支持超时/物体缺失/顺序错误检测；多渠道通知（日志/Webhook/声音），跨线程安全派发
- **多工位架构**：工位 Agent（StationReporter）定时上报状态到中央聚合服务（AggregationServer），产线看板实时聚合多工位进度与告警
- **权限系统**：JWT + RBAC，三角色（操作员/线长/管理员），AuthMiddleware 拦截校验
- **质检报告导出**：从当前执行状态生成报告，支持 JSON / 文本 / CSV 格式导出
- **架构重构**：移除模块单例，改用 FastAPI `app.state` + `Depends` 依赖注入；主服务拆分为处理循环/WebSocket/依赖工厂模块

## 产品路线图

| 阶段 | 状态 | 目标 | 文档 |
|------|------|------|------|
| **P0 稳定性与工程化** | ✅ 已完成 | 消除崩溃风险，建立工程化基础 | [P0-稳定性与工程化.md](docs/P0-稳定性与工程化.md) |
| **P1 核心功能增强** | ✅ 已完成 | 提升核心功能可靠性与扩展性 | [P1-核心功能增强.md](docs/P1-核心功能增强.md) |
| **P2 识别精度与生产化** | ✅ 已完成 | 从技术Demo升级为可售产品 | [P2-体验与部署.md](docs/P2-体验与部署.md) |
| **P3 商业化与规模化** | 📋 规划中 | 实现商业化落地与规模化交付 | [P3-商业化与规模化.md](docs/P3-商业化与规模化.md) |

### P3 商业化方向
1. **SaaS多租户平台**：订阅制计费，自助开通
2. **算法市场**：行业工序模板+社区检测模型
3. **设备管理**：远程运维+OTA算法热更新
4. **BI报表**：OEE/FPY/CT等核心指标分析
5. **开放平台**：REST API+Webhook+MES对接SDK

## 目录结构

```
g:\ai_sop\
├── backend/                        # Python 后端
│   ├── main.py                     # FastAPI 主服务（应用装配与生命周期）
│   ├── config.py                   # 全局配置（环境变量+部署开关）
│   ├── dependencies.py             # 依赖注入工厂（app.state + Depends）
│   ├── pipeline.py                 # 后台处理循环（采集→检测→识别→推送）
│   ├── ws_server.py                # WebSocket 端点与客户端注册表
│   ├── models.py                   # 数据模型 (Pydantic)
│   ├── db_models.py                # 数据库模型 (SQLAlchemy)
│   ├── database.py                 # 数据库初始化
│   ├── camera_service.py           # 摄像头采集服务 (线程化)
│   ├── hand_detector.py            # MediaPipe 手部检测
│   ├── step_recognizer.py          # 步骤识别引擎 (状态机)
│   ├── sop_manager.py              # SOP 工序管理
│   ├── logging_config.py           # 日志配置
│   ├── detectors/
│   │   └── object_detector.py      # YOLOv8 物体检测
│   ├── alarm/
│   │   ├── alarm_manager.py        # 告警管理器（跨线程安全派发）
│   │   └── notifiers.py            # 通知器（日志/Webhook/声音）
│   ├── agent/
│   │   └── station_reporter.py     # 工位状态上报器
│   ├── central/
│   │   └── aggregation_server.py   # 中央聚合服务+产线看板路由
│   ├── auth/
│   │   ├── jwt_handler.py          # JWT 签发与校验
│   │   └── role_checker.py         # RBAC 角色权限
│   ├── middleware/
│   │   ├── auth_middleware.py       # JWT 鉴权中间件
│   │   └── error_handler.py        # 全局异常处理
│   ├── reports/
│   │   ├── report_generator.py     # 质检报告生成
│   │   ├── pdf_renderer.py         # PDF 报告渲染（reportlab）
│   │   └── excel_renderer.py       # Excel 报告渲染（openpyxl）
│   ├── repositories/               # 数据访问层
│   └── api/v1/                     # REST API 路由
│       ├── health.py               # 健康检查
│       ├── sop.py                  # SOP 管理
│       ├── camera.py               # 摄像头控制
│       ├── video.py                # MJPEG/快照 视频流
│       ├── records.py              # 执行记录
│       ├── auth.py                 # 认证与用户管理
│       └── reports.py              # 质检报告与告警
├── frontend/                       # React 前端
│   ├── src/
│   │   ├── App.tsx                 # 主应用（组合 hooks）
│   │   ├── components/
│   │   │   ├── ErrorBoundary.tsx    # 错误边界+Toast+连接状态栏
│   │   │   ├── VideoView.tsx        # 视频渲染
│   │   │   ├── StepList.tsx         # 步骤列表
│   │   │   ├── StepThumbnails.tsx   # 步骤缩略图
│   │   │   ├── ControlPanel.tsx     # 控制面板
│   │   │   ├── HandPanel.tsx        # 手部检测面板
│   │   │   ├── SopSwitcher.tsx      # SOP 切换器
│   │   │   ├── SopEditor.tsx        # SOP 可视化编辑器
│   │   │   ├── StepEditor.tsx       # 步骤编辑器
│   │   │   ├── RecordList.tsx       # 执行记录列表
│   │   │   ├── CameraSelector.tsx   # 摄像头选择器
│   │   │   ├── Login.tsx            # 登录页
│   │   │   ├── LineDashboard.tsx    # 产线看板
│   │   │   ├── ReportExport.tsx     # 质检报告导出
│   │   │   └── ZoneCalibrator.tsx   # 工作区域标定工具（管理员）
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts      # WebSocket/REST 封装
│   │   │   ├── useAuth.ts           # 登录态
│   │   │   ├── useToast.ts          # Toast 消息
│   │   │   ├── useSopStatus.ts      # SOP 状态快照
│   │   │   └── useSopControl.ts     # SOP 控制操作
│   │   ├── utils/api.ts             # fetch 封装（携带JWT）
│   │   ├── types.ts                 # TypeScript 类型
│   │   └── index.css                # 全局样式
│   ├── vite.config.ts
│   └── package.json
├── sops/                           # SOP 工序定义
│   └── assembly_demo.json          # PCB装配演示工序
├── docs/                           # 产品规划文档
│   ├── P0-稳定性与工程化.md
│   ├── P1-核心功能增强.md
│   ├── P2-体验与部署.md             # 识别精度与生产化
│   └── P3-商业化与规模化.md         # 商业化与规模化
└── README.md
```

## 环境要求

- Python >= 3.11
- Node.js >= 18
- Windows（使用 MSMF 摄像头后端）

## 快速开始

### 1. 安装后端依赖

```powershell
cd g:\ai_sop\backend
pip install -r requirements.txt
```

> 若 `mediapipe` 安装较慢，可使用国内镜像：
> `pip install mediapipe -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 2. 启动后端服务

```powershell
cd g:\ai_sop\backend
python main.py
```

后端启动后：
- API 文档：http://localhost:8000/docs
- 视频WebSocket：ws://localhost:8000/ws/video
- 状态WebSocket：ws://localhost:8000/ws/status
- MJPEG视频流：http://localhost:8000/api/v1/video/mjpeg

### 3. 启动前端

```powershell
cd g:\ai_sop\frontend
npm install
npm run dev
```

访问 http://localhost:5173

默认账号：`admin` / `admin123`（管理员）、`supervisor` / `super123`（线长）、`operator` / `op123`（操作员）

## 部署形态

系统支持两种部署形态，通过环境变量切换：

### 单机部署（默认）
- 工位识别与中央聚合在同一进程运行
- `ENABLE_LOCAL_AGGREGATION=true`（默认）
- 不设置 `CENTRAL_SERVER_URL`，或指向自身时自动跳过工位上报（避免 httpx 回环）

### 多工位部署
- 各工位独立运行后端，仅做识别与上报
- `ENABLE_LOCAL_AGGREGATION=false`（关闭本地聚合路由）
- `CENTRAL_SERVER_URL=http://中央服务地址:端口` 指向独立部署的中央服务
- 中央服务保持 `ENABLE_LOCAL_AGGREGATION=true`，接收多工位上报并对外提供产线看板

> 强制让工位上报给自己（仅自测）：设置 `STATION_REPORT_TO_SELF=true`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务监听端口 |
| `CORS_ORIGINS` | dev默认 | 允许跨域来源（逗号分隔） |
| `CAMERA_INDEX` | `0` | 摄像头索引 |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` / `CAMERA_FPS` | `1280`/`720`/`30` | 摄像头参数 |
| `JPEG_QUALITY` | `75` | 视频帧JPEG质量 |
| `STATUS_INTERVAL` | `0.2` | 状态推送节流间隔(秒) |
| `OBJECT_DETECTION_ENABLED` | `true` | 是否启用物体检测 |
| `OBJECT_DETECTION_CONFIDENCE` | `0.5` | 物体检测置信度阈值 |
| `YOLO_MODEL_PATH` | - | YOLOv8 模型路径 |
| `ALARM_WEBHOOK_URL` | - | 告警 Webhook 地址 |
| `ALARM_LEVEL_FILTER` | `warning` | Webhook 告警级别过滤 |
| `ALARM_SOUND_ENABLED` | `true` | 是否启用声音告警 |
| `JWT_SECRET` | - | JWT 签名密钥 |
| `CENTRAL_SERVER_URL` | - | 中央聚合服务地址（多工位上报目标） |
| `STATION_ID` | `W-001` | 当前工位ID |
| `STATION_NAME` | `工位1` | 当前工位名称 |
| `ENABLE_LOCAL_AGGREGATION` | `true` | 是否在本进程挂载聚合路由 |
| `STATION_REPORT_TO_SELF` | `false` | 自调用时是否仍上报 |

## SOP 工序定义

SOP 以 JSON 文件存放在 `sops/` 目录，也支持通过数据库管理。字段说明：

| 字段 | 说明 |
|------|------|
| `sop_name` | 工序名称 |
| `steps` | 步骤数组 |
| `step.step_id` | 步骤ID |
| `step.name` | 步骤名称 |
| `step.target_zone` | 目标区域：`left_area` / `center_area` / `right_area` / `top_area` |
| `step.required_gesture` | 所需手势：`open` / `fist` / `pinch` / `point` / `unknown`(不限) |
| `step.hold_duration_sec` | 条件持续时长（秒），满足后判定完成 |
| `step.required_objects` | 步骤要求物体（class_name/target_zone/min_count） |
| `step.description` | 步骤描述 |

## REST API

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |

### SOP 管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sop/list` | 列出可用SOP |
| POST | `/api/v1/sop/load` | 加载SOP |
| POST | `/api/v1/sop/start` | 开始/恢复 |
| POST | `/api/v1/sop/pause` | 暂停 |
| POST | `/api/v1/sop/reset` | 重置 |
| POST | `/api/v1/sop/skip` | 跳过当前步骤 |
| GET | `/api/v1/sop/status` | 获取当前状态 |
| GET | `/api/v1/sop/zones` | 获取工作区域定义 |
| POST | `/api/v1/sop/zones` | 更新工作区域（管理员） |

### 视频与摄像头
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/video/mjpeg` | MJPEG视频流 |
| GET | `/api/v1/video/snapshot` | 单帧快照 |
| GET | `/api/v1/camera/list` | 列出可用摄像头 |
| POST | `/api/v1/camera/switch` | 切换摄像头 |

### 认证与用户（JWT）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 登录获取Token |
| GET | `/api/v1/auth/me` | 获取当前用户 |
| GET | `/api/v1/auth/users` | 用户列表（管理员） |
| POST | `/api/v1/auth/users` | 创建用户（管理员） |
| DELETE | `/api/v1/auth/users/{id}` | 删除用户（管理员） |

### 执行记录
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/records` | 查询执行记录 |
| GET | `/api/v1/records/{id}` | 执行记录详情 |

### 质检报告与告警
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/reports/generate` | 生成JSON报告 |
| POST | `/api/v1/reports/export/text` | 导出文本报告 |
| POST | `/api/v1/reports/export/csv` | 导出CSV报告 |
| POST | `/api/v1/reports/export/pdf` | 导出PDF报告（需 reportlab） |
| POST | `/api/v1/reports/export/excel` | 导出Excel报告（需 openpyxl） |
| GET | `/api/v1/reports/alarms` | 获取告警历史 |
| POST | `/api/v1/reports/alarms/{id}/acknowledge` | 确认告警 |
| DELETE | `/api/v1/reports/alarms` | 清除活跃告警 |

### 产线看板（中央聚合）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/station/report` | 工位上报状态 |
| GET | `/api/v1/stations` | 所有工位状态 |
| GET | `/api/v1/stations/{id}` | 单工位详情 |
| GET | `/api/v1/line/summary` | 产线整体摘要 |
| DELETE | `/api/v1/stations/{id}` | 移除工位 |

### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/video` | 推送带骨架标注的视频帧(JPEG二进制) |
| `/ws/status` | 推送步骤状态更新(JSON) |

## 调试建议

1. **摄像头无法打开**：确认索引正确，运行 `python test_camera.py` 排查
2. **手部检测不灵敏**：调整 `config.py` 中 `min_detection_confidence`（降低阈值更灵敏）
3. **步骤误触发**：增大 `hold_duration_sec` 提高确认时长
4. **区域不准**：通过视频画面观察手部位置，调整 `WORK_ZONES` 坐标
5. **视频画面镜像**：已在 `VideoView.tsx` 中通过 `transform: scaleX(-1)` 处理
6. **多工位上报无数据**：检查 `CENTRAL_SERVER_URL` 是否指向中央服务，且非自身端口（否则会被自调用检测跳过）
7. **声音告警无播放**：确认 `ALARM_SOUND_ENABLED=true`；Windows 下确认系统未静音且浏览器允许自动播放音频
8. **PDF/Excel 导出报 503**：后端未安装 `reportlab`（PDF）或 `openpyxl`（Excel），在 `backend/` 执行 `pip install -r requirements.txt`
9. **区域标定不生效**：通过 `/api/v1/sop/zones` 保存后需重启后端以加载 `data/zones.json`
