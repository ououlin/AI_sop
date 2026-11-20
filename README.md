# AI SOP · 装配线工序识别系统

<p>
  <img alt="Python" src="https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white">
  <img alt="Node" src="https://img.shields.io/badge/node-18%2B-339933?logo=node.js&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white">
  <img alt="Stage" src="https://img.shields.io/badge/P3-多租户进行中-fbbf24">
</p>

> 用普通 USB 摄像头 + 一台工位机，把装配工序变成可追溯的数据。
> 摄像头看手、模型看物、状态机看顺序，替代人工巡检做 SOP 合规检查。

面向中小制造企业的**轻量级 SOP 合规检查工具**：不需要工业相机，不需要改造产线，一台普通 PC 加一个摄像头即可部署。

---

## 目录

- [为什么用它](#为什么用它)
- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [测试](#测试)
- [部署形态](#部署形态)
- [文档](#文档)
- [路线图](#路线图)
- [贡献](#贡献)
- [许可](#许可)

---

## 为什么用它

| 传统做法 | 本系统 |
|----------|--------|
| 人工巡检，抽查靠人眼 | 摄像头全程判定，每一步都有时间戳与结果 |
| 出了问题靠回忆和纸单 | 执行记录自动落库，可筛选、可导出质检报告 |
| 换一条工序要重新培训 | SOP 可视化编辑，产线工程师自助配置 |
| 多工位各自为政 | 工位 Agent + 中央聚合，产线看板一屏掌握 |
| 试用一个点就得部署一套 | 数据面多租户，一套服务支撑多家客户 |

差异化：**轻量**（USB 摄像头即可）、**低门槛**（SOP 可自助配置）、**可追溯**（每次执行有完整记录）、**可扩展**（手势 + 物体 + 时序多模态判定）。

## 核心能力

| 能力 | 说明 |
|------|------|
| 手部识别 | MediaPipe 双手 21 点骨架，4 种手势（张开 / 握拳 / 捏合 / 指向） |
| 区域判定 | 左 / 中 / 右 / 上区域划分，支持运行时标定并立即生效 |
| 物体检测 | YOLOv8 融合判定；未安装时自动降级为颜色追踪 |
| 步骤状态机 | 7 态（待执行 / 进行中 / 已完成 / 跳过 / 错误 / 超时 / 未授权跳过），支持持续时长确认 |
| 异常告警 | 超时、顺序错误、物体缺失；日志 / Webhook / 声音多渠道 |
| 执行记录 | 每次执行落库，支持按时间、状态、SOP 筛选 |
| 质检报告 | JSON / 文本 / CSV / PDF / Excel 五种格式 |
| 权限体系 | JWT + RBAC，四角色：操作员 / 线长 / 管理员 / 平台管理员 |
| 多工位 | 工位 Agent 上报 → 中央聚合 → 产线看板 |
| 多租户 | 租户数据隔离、订阅套餐、工位数配额、到期只读 |

## 系统架构

```
┌──────────┐   ┌──────────────┐   ┌─────────────────┐   ┌────────────────┐
│ USB 摄像头│ → │ MediaPipe    │ → │ 步骤识别状态机   │ → │ WebSocket 推送 │
│ 线程化采集│   │ 手部 21 点   │   │ 手势+区域+物体   │   │ MJPEG 视频流   │
└──────────┘   └──────────────┘   └─────────────────┘   └────────────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                    ┌──────────┐    ┌────────────┐   ┌──────────────┐
                    │ 异常告警 │    │ 执行记录落库│   │ 质检报告导出 │
                    └──────────┘    └────────────┘   └──────────────┘

                      多工位部署：工位 Agent ──HTTP──▶ 中央聚合服务 ──▶ 产线看板
```

技术栈：后端 FastAPI + SQLAlchemy + MediaPipe + OpenCV；前端 React 18 + Vite + TypeScript；数据默认 SQLite，可切 PostgreSQL。

## 快速开始

**前置条件**：Python 3.8+、Node.js 18+、Windows（摄像头采集使用 MSMF 后端）、一个 USB 摄像头。

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 模型文件

模型权重体积较大，不纳入版本库，首次运行前需放到 `backend/`：

| 文件 | 用途 | 获取方式 |
|------|------|----------|
| `hand_landmarker.task` | 手部检测（必需） | 缺失时启动会报错并给出下载命令 |
| `yolov8n.pt` | 物体检测（可选） | 安装 `ultralytics` 后首次运行自动下载；缺失时降级为颜色追踪 |

```powershell
Invoke-WebRequest `
  -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task' `
  -OutFile 'backend\hand_landmarker.task'
```

### 3. 配置与启动

```powershell
copy .env.example .env      # 默认值即可跑通；生产务必修改 JWT_SECRET 与 STATION_API_KEY
python main.py
```

启动后：API 文档 <http://localhost:8000/docs>，前端 <http://localhost:8000>（已构建前端时）。

### 4. 前端

```powershell
cd frontend
npm install
npm run dev          # 开发：http://localhost:5173
npm run build        # 生产：产物由后端 /assets 静态托管
```

### 5. 默认账号

租户编码 `default`：`admin / admin123`（管理员）、`supervisor / super123`（线长）、`operator / op123`（操作员）。

> 平台管理员账号通过 `PLATFORM_ADMIN_USERNAME` / `PLATFORM_ADMIN_PASSWORD` 环境变量创建，未配置密码则不创建。

## 项目结构

```
AI_sop/
├── backend/                 # FastAPI 服务
│   ├── api/v1/              # REST 路由（sop / camera / video / records / auth / reports / tenant）
│   ├── alarm/               # 告警管理与通知渠道
│   ├── agent/ central/      # 工位上报与产线聚合
│   ├── auth/ middleware/    # JWT + RBAC、认证与租户中间件
│   ├── detectors/           # YOLOv8 物体检测
│   ├── repositories/        # 数据访问层（按租户过滤）
│   ├── saas/ tenancy/       # 租户、订阅与请求级租户上下文
│   ├── schema.py            # 建表与轻量迁移
│   └── tests/               # 单元测试
├── frontend/                # React + Vite 前端
│   └── src/                 # 组件、hooks、类型与样式
├── docs/                    # 产品与工程文档（见下方「文档」）
├── sops/                    # 示例 SOP 定义
└── README.md
```

## 测试

```powershell
cd backend
python -m unittest discover -s tests -t .
```

当前覆盖：权限依赖、步骤状态机、区域热更新、执行记录落库、租户隔离与迁移、租户/套餐接口、到期只读、工位配额。

## 部署形态

| 形态 | 适用场景 | 关键配置 |
|------|----------|----------|
| 单机部署 | 单工位试点 | 默认即可，聚合路由内嵌 |
| 多工位 | 整条产线 | 工位侧 `ENABLE_LOCAL_AGGREGATION=false` + `CENTRAL_SERVER_URL`；中央侧配 `STATION_API_KEY` |
| SaaS 多租户 | 多客户托管 | `DATABASE_URL` 指向 PostgreSQL，配置平台管理员后开通租户 |

> 识别流水线是**单工位单租户**的：一个进程服务一台设备。多租户共享的是 API 与数据库，不是同一路视频。

详细步骤见 [部署指南](docs/部署指南.md)，环境变量见 [配置参考](docs/配置参考.md)。

## 文档

| 文档 | 内容 |
|------|------|
| [文档索引](docs/README.md) | 全部文档导航、阶段总览与撰写规范 |
| [API 参考](docs/API.md) | REST 接口、WebSocket、错误结构、SOP 格式、角色权限 |
| [配置参考](docs/配置参考.md) | 环境变量清单与部署配置组合 |
| [部署指南](docs/部署指南.md) | 单机 / 多工位 / SaaS / Docker 部署 |
| [P2 识别精度与生产化](docs/P2-体验与部署.md) | 当前能力是怎么来的 |
| [P3-M1 多租户实施计划](docs/P3-M1-多租户实施计划.md) | 当前正在做的事 |

## 路线图

| 阶段 | 主题 | 状态 |
|------|------|------|
| P0 | 稳定性与工程化 | ✅ 已完成 |
| P1 | 核心功能增强 | ✅ 已完成 |
| P2 | 识别精度与生产化 | ✅ 已完成 |
| P3 | 商业化与规模化 | 🚧 进行中 |
| P3-M1 | SaaS 多租户（隔离 / 管理 / 订阅 / 前端 / 部署） | ✅ 已完成 |
| P3-M2 ~ M5 | 算法市场 / 设备运维 / BI 报表 / 开放平台 | 📋 规划中 |

## 贡献

- 提交信息遵循 Conventional Commits：`feat(backend): ...`、`fix(frontend): ...`、`docs: ...`
- 改动需配套测试；后端至少保证 `python -m unittest discover -s tests -t .` 全绿
- 前端改动需通过 `npm run build`（含 TypeScript 类型检查）
- 文档改动同步更新 [文档索引](docs/README.md)

## 许可

本项目暂未指定开源许可证。如需对外开源，请补充 `LICENSE` 文件（如 MIT / Apache-2.0）。
