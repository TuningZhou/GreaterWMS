# GreaterWMS 项目整体分析报告（详细版）

> 本文档在《GreaterWMS 项目整体分析报告》基础上进行了结构化扩写，补充了业务流程、数据模型、接口清单、请求链路、部署细节、风险登记册与 Cloudflare 迁移工作分解，作为后续技术改造与迁移评审的基线材料。

## 文档信息

| 项 | 内容 |
|---|---|
| 文档名称 | GreaterWMS 项目整体分析报告（详细版） |
| 分析对象 | 仓库根目录下除 `000newPlatform/`、`Docs/` 之外的全部内容 |
| 分析方式 | 静态阅读源码与配置（未修改代码、未安装依赖、未启动服务） |
| 代码基线 | 分支 `S2B2B2C`，最新提交 `8344f387 V2.1.54`（2026-10-13） |
| 代码声明版本 | 2.1.48（`greaterwms/settings.py`、`templates/package.json`、`app/package.json`） |
| 数据库 | SQLite（仓库内无 `db.sqlite3`，运行时生成） |
| 许可证 | Apache License 2.0（`LICENSE`） |
| 结论可信度 | 所有结论均标注依据文件；无法从代码确认的内容统一标注「未找到相关依据」 |

## 阅读指南

- 第 1-2 章：面向管理者，快速了解系统定位、规模与技术底座。
- 第 3-5 章：面向架构师/开发者，逐模块说明职责、模型、接口与基础设施。
- 第 6-8 章：面向运维与安全负责人，说明部署方式、工程规范与风险。
- 第 9 章：面向决策者，给出优先级排序的改进路线。
- 第 10 章：面向迁移项目组，给出 Cloudflare 技术栈的完整落地方案。
- 附录：数据表清单、接口清单、关键文件索引、统计口径、未确认事项。

## 目录

- [0. 执行摘要](#0-执行摘要)
- [1. 项目定位与概况](#1-项目定位与概况)
- [2. 技术栈与架构](#2-技术栈与架构)
- [3. 后端模块划分](#3-后端模块划分)
- [4. 前端结构](#4-前端结构)
- [5. 公共与基础设施](#5-公共与基础设施)
- [6. 构建、部署与运维](#6-构建部署与运维)
- [7. 工程规范与质量保障](#7-工程规范与质量保障)
- [8. 安全与风险点](#8-安全与风险点)
- [9. 总结与建议](#9-总结与建议)
- [10. Cloudflare 迁移方案](#10-cloudflare-迁移方案)
- [附录](#附录)

---

## 0. 执行摘要

### 0.1 一句话结论

GreaterWMS 是一套**业务闭环完整、模块高度同构、二次开发友好**的开源仓储管理系统（Django REST Framework + Quasar），但其**安全默认值、数据一致性保障、部署脚本与测试体系均停留在演示/开发级**，距离生产级交付仍有明显差距；若要迁移到 Cloudflare，建议采用「边缘前置 → 主数据重写 → 库存单据重写 → 下线 Django」的四阶段路线，而不是原样搬迁。

### 0.2 关键发现 Top 10

| # | 发现 | 影响 | 依据 |
|---|---|---|---|
| 1 | 仓库**没有任何数据库迁移文件**，容器启动时才 `makemigrations` | schema 不可审计、不可回滚、多环境漂移 | 30 个 `migrations/` 目录仅有 `__init__.py`；`backend_start.sh` |
| 2 | 全仓库**无事务、无行锁、无幂等** | 库存超卖、丢更新、部分成功 | 检索 `transaction.atomic` / `select_for_update` / `F()` 均为 0 命中 |
| 3 | 认证令牌 = 用户 `openid`，永久有效、无刷新/吊销 | 令牌泄露即永久接管租户 | `utils/auth.py`、`userlogin/views.py`、`templates/src/boot/axios_request.js` |
| 4 | 权限类恒真，`staff_type` 不做服务端校验 | 任意登录用户可执行全部操作 | `utils/permission.py` |
| 5 | 商品「初始化导入」会**无条件清空 7 张字典表** | 跨租户数据被删除 | `uploadfile/views.py` 第 61-69 行 |
| 6 | 生产配置为开发默认值：`DEBUG=True`、`ALLOWED_HOSTS=['*']`、CORS 全开、CSRF 关闭 | 信息泄露、CSRF、跨站数据读取 | `greaterwms/settings.py` 第 16、18、72、314-316 行 |
| 7 | 前端容器启动 `quasar d`（开发服务器） | 生产性能与安全均不达标 | `web_start.sh` |
| 8 | 测试文件全空，CI 的 Postgres 服务未被使用，安全扫描不阻断 | 质量门禁形同虚设 | 30 个 `tests.py`；`.github/workflows/ci.yml` |
| 9 | 两套前端并存（Vue 2/Webpack 与 Vue 3/Vite），请求层能力差距大 | 长期维护成本高、行为不一致 | `templates/`、`app/` |
| 10 | 版本号三处 2.1.48，Git 标签已到 2.1.54 | 发布溯源困难 | `settings.py`、两个 `package.json`、`git tag` |

### 0.3 风险热力图

| 领域 | 可能性 | 影响 | 等级 |
|---|---|---|---|
| 认证与授权 | 高 | 高 | 极高 |
| 库存数据一致性 | 高 | 高 | 极高 |
| 多租户隔离 | 中 | 高 | 高 |
| 部署与配置 | 高 | 中 | 高 |
| 依赖与供应链 | 中 | 中 | 中 |
| 测试与回归 | 高 | 中 | 高 |
| 前端双轨维护 | 高 | 低 | 中 |
| 可观测性缺失 | 高 | 中 | 高 |

### 0.4 建议行动清单（摘要）

| 优先级 | 事项 | 预估工作量 | 收益 |
|---|---|---|---|
| P0 | 配置外部化（SECRET_KEY/DEBUG/ALLOWED_HOSTS/CORS） | 1-2 人日 | 消除最高危配置风险 |
| P0 | 认证改造为可过期、可吊销的 JWT + 角色校验 | 5-8 人日 | 消除永久令牌与越权 |
| P0 | 修复跨租户批量删除 | 0.5 人日 | 避免数据事故 |
| P0 | 库存路径加事务、行锁、幂等键 | 8-12 人日 | 保障核心资产准确 |
| P0 | 修复部署脚本与镜像 | 3-5 人日 | 可交付生产 |
| P1 | 提交初始迁移、CI 强制校验 | 2-3 人日 | schema 可治理 |
| P1 | 建立核心流程集成测试 | 10-15 人日 | 回归可保障 |
| P1 | 拆分巨型 `views.py` 为 service 层 | 10-15 人日 | 可测试、可迁移 |
| P2 | 前端收敛与 SDK 统一 | 15-20 人日 | 降低长期成本 |
| P2 | 可观测性与备份体系 | 5-8 人日 | 可运维 |

---

## 1. 项目定位与概况

### 1.1 系统是什么

GreaterWMS 是一套**开源仓储管理系统（Warehouse Management System）**，采用前后端分离架构，后端 Django REST Framework 提供 RESTful API，前端 Quasar（Vue）提供 Web 与移动/PDA 界面，默认使用 SQLite 存储数据。

README 对定位的表述（`README.md`、`README.zh-CN.md`）：

- 传统商业 WMS 闭源、二开成本高、易被原厂绑定；
- GreaterWMS 以「**为定制而生**」为设计初衷，作为企业自建库存/仓储能力的基础平台；
- 强调「模块化业务设计」「统一多端（OneAPP）」「可对接 IoT/ERP/分销系统」。

代码层面可以确认：系统并非仅做「库存记录」，而是覆盖了**收货—上架—库存—拣货—发货—回单—盘点—结算**的完整作业链（详见 1.4 功能地图）。

### 1.2 解决的业务问题

| 业务痛点 | GreaterWMS 的对应能力 | 依据 |
|---|---|---|
| 到货无计划、收货数量对不上 | ASN 单头/明细、实收/短缺/多货/破损数量、预加载/预分拣/上架状态机 | `asn/models.py`、`asn/views.py` |
| 拣货靠纸单、发错货 | DN 单、订单释放、拣货任务（按库位）、已拣/发货/POD | `dn/models.py`、`dn/views.py` |
| 库存账实不符 | 库存总账 17 个数量维度 + 库位库存 + 移库 + 盘点（按日/全量/手工） | `stock/models.py`、`cyclecount/` |
| 库位管理粗放 | 库位、库位尺寸、库位属性（Normal/Holding/Damage/Inspection）、空库位状态 | `binset/`、`binsize/`、`binproperty/` |
| 商品资料分散 | 商品主数据 + 7 类字典（单位/类别/品牌/颜色/形状/规格/产地） | `goods/` 及 7 个字典应用 |
| PDA 无法离线作业 | 条码即「JWT 指令包」，扫码后解析还原业务动作 | `scanner/views.py`、`utils/jwt.py` |
| 批量建档效率低 | Excel/CSV 初始化导入与追加导入、CSV 导出 | `uploadfile/views.py`、各 `files.py` |
| 运费不透明 | 运输费用表（重量费/体积费/最低收费）+ 运费计算函数 | `payment/models.py`、`utils/datasolve.py` |
| 多货主/多租户 | 所有业务表以 `openid` 为租户键隔离 | 各 `models.py`、`views.py` |

### 1.3 目标用户与典型场景

README 列出了已落地的定制场景（`README.md`「Real-World Customization Scenarios」）：

| 行业 | 定制内容 | 与代码的对应关系 |
|---|---|---|
| 第三方物流/云仓（3PL） | 多仓集群、一车多仓、冷链温控、批次效期、多货主隔离 | 多租户 `openid` 已具备；多仓/批次/温控**未找到相关依据**（应为定制分支） |
| 医药流通 | 批次管理、效期预警、GSP 温湿度 | 批次/效期字段**未找到相关依据** |
| 冷链仓储 | 温度记录与告警 | **未找到相关依据** |
| 跨境电商 | 国际物流、报关接口 | **未找到相关依据** |
| 制造业 | 批次追溯、FIFO、MES 对接 | FIFO/批次**未找到相关依据**；库存维度具备基础 |

> 结论：README 中的行业定制案例属于「基于本项目的二次开发成果」，**并非本仓库开箱即用的功能**。本仓库提供的是通用 WMS 底座。

### 1.4 功能地图

```
GreaterWMS
├─ 入库 Inbound
│  ├─ ASN 到货通知（单头/明细/打印）
│  ├─ 预加载 PreLoad
│  ├─ 预分拣 PreSort
│  ├─ 分拣 Sorted（短缺/多货/破损）
│  └─ 上架 MoveToBin
├─ 出库 Outbound
│  ├─ DN 发货单（单头/明细/打印）
│  ├─ 新订单 / 订单释放
│  ├─ 拣货任务（按库位）
│  ├─ 已拣 Picked / 发货 Dispatch
│  └─ POD 回单 / 欠货补发 Back Order
├─ 库存 Inventory
│  ├─ 库存总账（17 个数量维度）
│  ├─ 库位库存（含拣货占用）
│  ├─ 移库（库位属性转换）
│  ├─ 空库位 / 占用库位
│  ├─ 动态盘点（按日）
│  ├─ 全量盘点
│  └─ 手工盘点
├─ 基础资料 Master Data
│  ├─ 商品 + 单位/类别/品牌/颜色/形状/规格/产地
│  ├─ 供应商 / 客户 / 公司
│  ├─ 仓库 / 库位 / 库位尺寸 / 库位属性
│  ├─ 员工 / 员工类型 / 司机
│  ├─ 固定资产 / 运输费用
│  └─ 用户注册 / 登录 / 资料
├─ 作业工具
│  ├─ PDA 扫码（商品标签、库位标签、DN 拣货）
│  ├─ Excel/CSV 导入（初始化/追加）
│  ├─ CSV 导出（单据/库存/主数据）
│  └─ 站内聊天（WebSocket）
└─ 分析
   └─ 仪表盘（收货趋势/发货趋势）
```

### 1.5 版本、许可与维护状态

| 项 | 结论 | 依据 |
|---|---|---|
| 许可证 | Apache License 2.0 | `LICENSE` |
| 代码声明版本 | 2.1.48 | `greaterwms/settings.py`（`SPECTACULAR_SETTINGS.VERSION`）、`templates/package.json`、`app/package.json` |
| Git 标签 | V2.1.54 / V2.1.52 / V2.1.49 / V2.1.48 / V2.1.47 / V2.1.42 / V2.1.38 / V2.1.37… | `git tag` |
| 最新提交 | `8344f387 V2.1.54`，2026-10-13 | `git log` |
| 提交节奏 | 2025-09 至 2026-10 期间持续提交 | `git log` |
| 当前分支 | `S2B2B2C`（存在 `master` 与多个 Dependabot 分支） | `git branch -a` |
| 官方主线 | README 宣布 3.0 已用 Bomiot（Rust 插件化框架）重构，开发者文档迁至 Bomiot | `README.md` |
| 版本一致性 | 代码 2.1.48 vs 标签 2.1.54，**不一致** | 同上 |

**维护状态判断**：本仓库是「2.x Django 版」的活跃维护分支，功能完整、仍有提交；但官方战略重心已转向 Bomiot 3.0。对于基于本仓库做二次开发的团队，需要明确「跟随 2.x 修复」还是「评估迁移 Bomiot/自研」的长期策略。

### 1.6 工程规模度量

| 指标 | 数值 | 统计口径 |
|---|---|---|
| Django 应用 | 30 个 | `INSTALLED_APPS` |
| 后端 Python 代码 | 约 14,500 行 | 排除 `000newPlatform` 的 `*.py` |
| 最大单文件 | `dn/views.py` 约 144 KB | 文件大小 |
| 次大单文件 | `asn/views.py` 约 77 KB、`uploadfile/views.py` 约 59 KB、`stock/views.py` 约 36 KB | 文件大小 |
| 旧版前端 | 约 37,000 行 Vue/JS，78 个页面文件 | `templates/src` |
| 新版前端 | 约 14,000 行 Vue/JS，20 个页面文件 | `app/src` |
| 数据表 | 33 张业务表（不含 Django 内置表） | 各 `models.py` 的 `db_table` |
| 迁移文件 | 0 个 | `migrations/` 仅有 `__init__.py` |
| 已提交构建产物 | 421 个文件（`templates/dist` 220 + `static_new` 201） | `git ls-files` |
| 测试用例 | 0 个 | 30 个 `tests.py` 均为空或空壳 |

### 1.7 核心术语表

| 术语 | 含义 | 代码位置 |
|---|---|---|
| ASN | Advance Shipping Notice，到货通知单 | `asn/` |
| DN | Delivery Note，发货单 | `dn/` |
| Bin | 库位 | `binset/` |
| Bin Property | 库位属性：Normal/Holding/Damage/Inspection | `binproperty/`、`stock/views.py` |
| PreLoad | 预加载（收货前的装载/到货准备） | `asn/views.py` |
| PreSort | 预分拣 | `asn/views.py` |
| Sorted | 分拣完成（含短缺/多货） | `asn/views.py` |
| MoveToBin | 上架到库位 | `asn/views.py` |
| Picking | 拣货任务（DN 明细 × 库位） | `dn/models.py` `PickingListModel` |
| Picked | 已拣货 | `dn/views.py` |
| POD | Proof of Delivery，签收回单 | `dn/views.py` |
| Back Order | 欠货补发单 | `dn/models.py` `back_order_label` |
| Cycle Count | 盘点 | `cyclecount/` |
| openid | 租户标识，同时被当作 API 令牌 | `userprofile/models.py`、`utils/auth.py` |
| operator | 当前操作员工 id（请求头） | `settings.py` `CORS_ALLOW_HEADERS`、各 `views.py` |

---

## 2. 技术栈与架构

### 2.1 总体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                          客户端层                                    │
│  templates/ (Quasar 1 + Vue 2 + Webpack)    app/ (Quasar 2 + Vue 3)  │
│  后台管理 Web / 打印 / ECharts / i18n        PDA / Cordova / Electron │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTP(S) JSON，token / operator / language 头
┌───────────────────────────▼──────────────────────────────────────────┐
│                     接入层（可选 Nginx）                              │
│  TLS 终止 / 反向代理 8008 / WebSocket 升级 / static 与 media alias     │
└───────────────────────────┬──────────────────────────────────────────┘
┌───────────────────────────▼──────────────────────────────────────────┐
│                   Django 4.1.2 + DRF（Daphne/ASGI）                   │
│  Middleware: CORS → Security → Session → Common → Auth → Message      │
│              → XFrameOptions（CSRF 已禁用）                           │
│  DRF: 自定义鉴权 → 恒真权限 → 自定义限流 → ViewSet → Serializer        │
│       → django-filter → 自定义分页 → 自定义异常处理                    │
│  横切: 日志(logs/*.log) / OpenAPI(/api/) / CSV 渲染 / WebSocket 聊天   │
└───────────┬──────────────────────────────────┬───────────────────────┘
            │ ORM                              │ 文件 IO
┌───────────▼──────────────┐      ┌────────────▼───────────────────────┐
│ SQLite (db.sqlite3)      │      │ media/<openid>/... （上传/头像）    │
│ 33 张业务表 + Django 内置 │      │ static/、static_new/、templates/dist│
└──────────────────────────┘      └────────────────────────────────────┘
```

### 2.2 后端技术栈（版本矩阵）

| 类别 | 组件 | 版本 | 用途 | 依据 |
|---|---|---|---|---|
| 语言 | Python | 3.8（镜像）/ 3.9（CI） | 运行时 | `Dockerfile`、`.github/workflows/ci.yml` |
| Web 框架 | Django | 4.1.2 | ORM、路由、Admin、Session | `requirements.txt` |
| API 框架 | djangorestframework | 3.14.0 | ViewSet/Serializer/分页/渲染 | `requirements.txt` |
| 过滤 | django-filter | 2.4.0 | 声明式字段过滤 | `requirements.txt`、各 `filter.py` |
| OpenAPI | drf-spectacular | 0.26.2 | Schema/Swagger/Redoc | `settings.py`、`greaterwms/urls.py` |
| OpenAPI UI | drf-spectacular-sidecar | 2023.6.1 | 离线 Swagger/Redoc 静态资源 | `settings.py` |
| CSV | djangorestframework-csv | 2.1.1 | 流式 CSV 导出 | 各 `files.py` |
| ASGI 服务器 | daphne | 4.0.0 | HTTP + WebSocket | `backend_start.sh`、`supervisord.conf` |
| ASGI 适配 | asgihandler | 0.5.9 | 请求上下文注入 | `greaterwms/asgi.py` |
| WebSocket | Twisted / Autobahn / txaio | 22.10.0 / 23.1.2 / 23.1.1 | 聊天通道 | `requirements.txt`、`utils/websocket.py` |
| JWT | PyJWT | 2.8.0 | 扫码条码签发/校验 | `utils/jwt.py` |
| 数据处理 | pandas / numpy / openpyxl | 1.5.1 / 1.23.4 / 3.0.10 | Excel/CSV 导入 | `uploadfile/views.py` |
| 数据库驱动 | 内置 sqlite3 | — | 默认且唯一配置 | `settings.py` |

**依赖特征**：

- 全部依赖为**精确版本固定**（`==`），但**无哈希校验**（无 `--require-hashes`、无 `poetry.lock`/`uv.lock`）。
- 版本集中在 2022-2023 年，Django 4.1.2 已停止安全支持，存在此后披露的 CVE 风险。
- 未包含 `psycopg2`/`mysqlclient`/`dj-database-url`，因此 README 宣称的 MySQL/PostgreSQL 支持**未找到相关依据**。

### 2.3 前端技术栈（版本矩阵）

| 类别 | `templates/`（主前端） | `app/`（移动端） |
|---|---|---|
| 框架 | Quasar 1.15.x | Quasar 2.6.x |
| Vue | Vue 2.6 | Vue 3.x |
| 构建 | `@quasar/app` 2.2.10 + Webpack 5 | `@quasar/app-vite` 1.x + Vite |
| 路由 | `vue-router` 3（hash 模式） | `vue-router` 4 |
| 状态 | `vuex` 3 | `vuex` 4 + `vuex-persist` |
| i18n | `vue-i18n` 8 | `vue-i18n` 9 |
| HTTP | `axios` 0.21 | `axios` 0.21 |
| 图表 | `echarts` 5 + `vue-echarts-v3` | 无 |
| 打印/条码 | `vue-print-nb`、`qrcode` | `lottie-web`、`vconsole` |
| 本地存储 | `dexie`（IndexedDB） | `LocalStorage` |
| 多端 | Web | Cordova / Capacitor / Electron / BEX |
| ESLint | 6 + `standard` + `vue/essential` | 8 + `vue/vue3-essential` + `prettier` |
| 测试 | 无（`echo` 占位） | 无 |
| 页面文件数 | 78 | 20 |

### 2.4 数据存储

- **引擎**：SQLite，文件 `BASE_DIR/db.sqlite3`，`OPTIONS.timeout=20`（`settings.py`）。
- **表命名**：全部显式声明 `db_table`，名称短小（`asnlist`、`dndetail`、`stockbin` 等），不使用 Django 默认的 `<app>_<model>`。
- **主键**：`DEFAULT_AUTO_FIELD = BigAutoField`。
- **通用字段模式**：
  - `openid`：租户键，几乎所有表都有（`Users` 使用 `user_profile` 表）。
  - `creater`：创建人姓名（字符串，不是外键）。
  - `is_delete`：软删除标记（布尔），查询层手工过滤。
  - `create_time` / `update_time`：`auto_now_add` / `auto_now`。
  - `t_code`：事务码（MD5），用于标识一次操作（部分表）。
  - `bar_code`：单据/库位/商品的条码（MD5 或业务编码）。
- **JSON 字段**：`asnlist.transportation_fee`、`dnlist.transportation_fee` 使用 `JSONField(default=dict)`。
- **无外键、无数据库级约束**：`goods_code`、`supplier`、`customer`、`bin_name`、`staff` 等均为字符串关联；删除/改名不会级联，也不会被数据库阻止。
- **索引**：`models.py` 中**未声明任何 `indexes` 或 `unique_together`**；查询性能依赖 `id` 主键与选择性过滤。
- **时间语义**：`USE_TZ=False`，`TIME_ZONE='Asia/Shanghai'`，存本地时间；跨时区部署需特别注意。

### 2.5 请求生命周期（以一次受保护的 API 调用为例）

```
1. 客户端发起请求，携带请求头
   token: <Users.openid>   operator: <staff.id>   language: zh-CN|en-US

2. CorsMiddleware
   - CORS_ORIGIN_ALLOW_ALL=True，回显 Origin，允许 credentials

3. SecurityMiddleware / SessionMiddleware / CommonMiddleware / AuthenticationMiddleware
   - CsrfViewMiddleware 被注释，不做 CSRF 校验

4. DRF 初始化 Request
   - DEFAULT_AUTHENTICATION_CLASSES = utils.auth.Authtication
     a. 若路径属于 /api/、/api/docs/、/api/debug/ → 直接返回 (False, None)
     b. 读取 HTTP_TOKEN；为空 → 抛 APIException("Please Add Token To Your Request Headers")
     c. 以 openid 精确匹配 Users；不存在 → 抛 APIException("User Does Not Exists")
     d. 命中 → 返回 (True, user)   ← 注意：request.user 是布尔值，request.auth 才是用户对象

5. DEFAULT_PERMISSION_CLASSES = utils.permission.Normalpermission
   - has_permission() 恒返回 True

6. DEFAULT_THROTTLE_CLASSES = utils.throttle.VisitThrottle
   - 取 X-Forwarded-For 或 REMOTE_ADDR 作为 IP
   - 按 HTTP 方法分别统计；每次请求先删除 1 秒前的同方法记录
   - 同一 openid+appid+ip+method 计数超过 500 且间隔 < 1 秒 → 拒绝

7. ViewSet.dispatch → 具体 action（list/create/retrieve/update/partial_update/destroy）
   - get_queryset() 强制 openid=self.request.auth.openid
   - 业务校验（utils.datasolve）
   - 写库（通常跨多张表、无事务）

8. Serializer 序列化 → 分页器包装
   - utils/page.py: page_size=30，max_page_size=1000，参数名 page/max_page
   - asn/page.py、dn/page.py 额外返回 supplier_list / customer_list

9. 异常处理 utils/my_exceptions.custom_exception_handler
   - 统一转换为 {detail: ...} 结构

10. 响应：JSON（默认）或 CSV（指定 renderer）
```

> 该链路中有三个关键设计取舍需要特别注意：
> 1. `authenticate()` 返回顺序与 DRF 约定相反，导致 `request.user` 不可用于常规权限体系；
> 2. 权限恒真，所有授权语义都落在 `get_queryset()` 的 `openid` 过滤上；
> 3. 限流把状态写进业务库（`throttle` 表），与业务请求共享同一个 SQLite 写锁。

### 2.6 前后端契约

| 契约项 | 约定 | 依据 |
|---|---|---|
| 内容类型 | JSON（写），CSV（部分导出） | `settings.py` `DEFAULT_RENDERER_CLASSES` |
| 认证头 | `token` = `Users.openid` | `utils/auth.py`、`templates/src/boot/axios_request.js` |
| 操作人头 | `operator` = `staff.id` | 各 `views.py`（如 `dn/views.py` 取 `HTTP_OPERATOR`） |
| 语言 | `language`: `zh-CN` / `en-US`，影响枚举文案与 CSV 表头 | `utils/apitag.py`、各 `files.py`、`uploadfile/views.py` |
| 分页参数 | `page`、`max_page`（默认 30，最大 1000） | `utils/page.py` |
| 分页响应 | `count`、`next`、`previous`、`results`（ASN/DN 另有业务字典） | `utils/page.py`、`asn/page.py`、`dn/page.py` |
| 过滤 | `django-filter` 查询参数，如 `?goods_code__icontains=A` | 各 `filter.py` |
| 排序 | `ordering=id,-create_time` | `OrderingFilter`、`ordering_fields` |
| 错误结构 | `{"detail": "..."}`，文案来自 `utils/fbmsg.py` | `utils/my_exceptions.py`、`utils/fbmsg.py` |
| API 文档 | `/api/`（schema）、`/api/debug/`（Swagger）、`/api/docs/`（Redoc） | `greaterwms/urls.py` |
| 版本化 | 未启用（`DEFAULT_VERSIONING_CLASS=None`） | `settings.py` |

### 2.7 运行时拓扑

**开发态**

```
浏览器 ──> Quasar Dev Server (:8080) ──axios(baseurl.txt)──> Daphne (:8008) ──> SQLite
```

**容器态（docker-compose）**

```
浏览器 ──> greaterwms_front (:8080, quasar dev)
                     │ depends_on
                     ▼
           greaterwms_backend (:8008, supervisor + daphne)
                     │ bind mount ./ -> /GreaterWMS
                     ▼
              ./db.sqlite3（宿主机文件）
```

**生产态（README/Nginx 推断）**

```
用户 ──443──> Nginx（TLS、静态 alias、WebSocket 升级）──> Daphne 127.0.0.1:8008 ──> SQLite
```

> 上述三种拓扑中，**只有开发态可以确认被完整跑通**；容器态因前端镜像构建缺陷与 `quasar d` 存在明显问题（见第 6 章）；生产态依赖手工替换 `nginx.conf` 占位符。

### 2.8 架构评价

**优点**

1. **分层可预期**：URL → ViewSet → Serializer → Model 的路径统一，新人上手成本低。
2. **模块同构**：30 个应用结构一致，复制改造即可扩展新主数据。
3. **API 优先**：所有能力先暴露为 REST 接口，前端只是消费者，便于多端复用。
4. **过滤/导出能力强**：`django-filter` 字段白名单 + CSV 渲染，满足运营侧复杂查询与导出。
5. **轻量部署**：无中间件依赖、无外部数据库，单机即可运行，适合演示与小规模部署。

**架构债务**

1. **业务逻辑与 HTTP 层耦合**：库存过账、状态机全部写在 `views.py`，无法在不启动 HTTP 的情况下测试或复用。
2. **无服务层/领域层**：跨应用直接操作对方 ORM，模块边界失效。
3. **无事务边界**：一次业务动作涉及 3-6 张表的写入，但没有原子性保证。
4. **认证/权限/限流为「占位实现」**：满足演示，不满足生产。
5. **SPA 由 Django 托管**：`greaterwms/views.py` 手写文件流，绕过 `staticfiles`，缓存与安全头不可控。
6. **双前端并存**：技术栈跨代，请求层/错误处理/i18n 行为不一致。

---

## 3. 后端模块划分

### 3.1 分层约定（每个应用的同构模板）

| 文件 | 职责 | 典型内容 | 缺失/异常情况 |
|---|---|---|---|
| `models.py` | 数据模型与 `db_table` 声明 | 业务字段、`is_delete`、`create_time` | 无外键、无索引、无约束 |
| `views.py` | HTTP 层 + 业务逻辑（混写） | `ModelViewSet` 子类、状态机、跨表写入 | ASN/DN/stock 达数千行 |
| `serializers.py` | 字段校验与输出 | `serializers.ModelSerializer`、`validate_*` | 部分应用只有一个通用序列化器 |
| `urls.py` | 路由映射 | `path` + `re_path` | `userprofile` 无 `urls.py`，`throttle/urls.py` 为空 |
| `filter.py` | 查询过滤白名单 | `FilterSet` + `CharFilter(method='filter_*')` | dashboard 无 filter |
| `page.py` | 自定义分页 | 附加业务字典（供应商/客户） | 仅 asn、dn、goods 等少数应用有 |
| `files.py` | CSV 导出 | `CSVRenderer` + 表头国际化 | 部分应用无 |
| `tests.py` | 单元/集成测试 | 空 | 30 个应用均无有效用例 |
| `admin.py` | Django Admin 注册 | 部分应用注册 | 注册不完整 |
| `apps.py` | 应用配置 | `XxxConfig` | 无特殊逻辑 |

### 3.2 应用清单总览

| # | 应用 | 数据表 | URL 前缀 | 职责 | 关键端点 |
|---|---|---|---|---|---|
| 1 | `asn` | `asnlist`、`asndetail` | `/asn/` | 入库单、预加载、预分拣、分拣、上架、打印、导出 | `list/`、`detail/`、`preload/`、`presort/`、`sorted/`、`movetobin/` |
| 2 | `dn` | `dnlist`、`dndetail`、`pickinglist` | `/dn/` | 出库单、订单释放、拣货、发货、POD、欠货 | `list/`、`detail/`、`orderrelease/`、`pickinglist/`、`picked/`、`dispatch/`、`pod/` |
| 3 | `stock` | `stocklist`、`stockbin` | `/stock/` | 库存总账、库位库存、移库、导出 | `list/`、`bin/` |
| 4 | `goods` | `goods` | `/goods/` | 商品主数据、扫码标签 | `""`、`goodstag/<bar_code>/` |
| 5 | `goodsunit` | `goodsunit` | `/goodsunit/` | 计量单位字典 | CRUD |
| 6 | `goodsclass` | `goodsclass` | `/goodsclass/` | 商品类别字典 | CRUD |
| 7 | `goodsbrand` | `goodsbrand` | `/goodsbrand/` | 品牌字典 | CRUD |
| 8 | `goodscolor` | `goodscolor` | `/goodscolor/` | 颜色字典 | CRUD |
| 9 | `goodsshape` | `goodsshape` | `/goodsshape/` | 形状字典 | CRUD |
| 10 | `goodsspecs` | `goodsspecs` | `/goodsspecs/` | 规格字典 | CRUD |
| 11 | `goodsorigin` | `goodsorigin` | `/goodsorigin/` | 产地字典 | CRUD |
| 12 | `warehouse` | `warehouse` | `/warehouse/` | 仓库主数据 | CRUD、`multiple/` |
| 13 | `binset` | `binset` | `/binset/` | 库位主数据、空库位标记、扫码标签 | CRUD、`scannerbintag/<bar_code>/` |
| 14 | `binsize` | `binsize` | `/binsize/` | 库位尺寸字典 | CRUD |
| 15 | `binproperty` | `binproperty` | `/binproperty/` | 库位属性字典（只读） | `list` |
| 16 | `supplier` | `supplier` | `/supplier/` | 供应商主数据 | CRUD、`file/` |
| 17 | `customer` | `customer` | `/customer/` | 客户主数据 | CRUD、`file/` |
| 18 | `company` | `company` | `/company/` | 公司主体 | CRUD |
| 19 | `staff` | `staff`、`stafftype` | `/staff/` | 员工与员工类型 | CRUD、`type/`、`file/` |
| 20 | `driver` | `driver`、`dispatchlist` | `/driver/` | 司机与派车单 | CRUD、`dispatchlist/` |
| 21 | `capital` | `capital` | `/capital/` | 固定资产 | CRUD、`file/` |
| 22 | `payment` | `transportationfee` | `/payment/` | 运输费用配置 | `freight/`、`freightfile/` |
| 23 | `cyclecount` | `qtyrecorder`、`cyclecountday`、`manualcyclecount` | `/cyclecount/` | 盘点（按日/全量/手工） | `""`、`cyclecountrecorder/`、`manualcyclecount/` |
| 24 | `scanner` | `scanner` | `/scanner/` | 条码指令签发与解析 | `""`、`query/`、`list/<bar_code>/` |
| 25 | `dashboard` | 无 | `/dashboard/` | 收货/发货趋势 | `receipts/`、`sales/` |
| 26 | `uploadfile` | 无 | `/uploadfile/` | Excel/CSV 初始化与追加导入 | 10 个上传端点 |
| 27 | `throttle` | `throttle` | 未挂载 | 限流计数表 | 无业务端点 |
| 28 | `userlogin` | 使用 `auth_user`、`user_profile` | `/login/` | 账号密码登录 | `""` |
| 29 | `userregister` | 使用 `auth_user`、`user_profile`、`staff` | `/register/` | 注册 + 演示数据初始化 | `""` |
| 30 | `userprofile` | `user_profile` | 未挂载 | 仅提供 `Users` 模型 | `views.py` 为空文件 |

> 说明：`throttle` 与 `userprofile` 虽在 `INSTALLED_APPS` 中，但未在 `greaterwms/urls.py` 注册路由；`userprofile/views.py` 为 0 字节，`throttle/views.py`、`throttle/urls.py` 亦为 0 字节。

### 3.3 模块依赖关系

```
greaterwms (settings/urls/asgi/views)
   │
   ├── utils（auth / permission / throttle / page / jwt / md5 / datasolve /
   │          fbmsg / my_exceptions / websocket / apitag / upload）
   │
   ├── 身份与租户域
   │     userprofile（Users 模型） ←── userlogin / userregister / utils.auth / utils.datasolve
   │     staff（staff / stafftype）
   │
   ├── 主数据域（彼此以字符串关联，无 ORM 依赖）
   │     company / supplier / customer / warehouse
   │     binset / binsize / binproperty
   │     goods / goodsunit / goodsclass / goodsbrand / goodscolor /
   │     goodsshape / goodsspecs / goodsorigin
   │     driver / capital / payment
   │
   ├── 作业域（依赖主数据与库存）
   │     asn ──写──> stocklist / stockbin / qtyrecorder / binset
   │     dn  ──写──> stocklist / stockbin / pickinglist / scanner
   │     stock ──写──> stocklist / stockbin / binset / qtyrecorder
   │     cyclecount ──写──> stocklist / stockbin / qtyrecorder
   │     scanner ──读──> dn / goods / binset
   │
   └── 支撑域
         uploadfile（依赖 goods + 6 字典 + supplier + customer + capital + payment）
         dashboard（只读 asnlist / dnlist / dndetail）
         throttle（自维护计数表）
```

**依赖特征**：

1. 依赖关系**只存在于 Python import 层**，数据库层没有任何外键约束，删除主数据不会报错也不会级联。
2. 作业域应用直接 `from stock.models import ...` 并写入对方表，没有服务层封装。
3. `utils.datasolve` 同时依赖 `Users` 与 `staff`，被 ASN/DN/stock 多处调用，是事实上的「隐式领域服务」。

### 3.4 身份与租户域

#### 3.4.1 `userprofile`：用户与租户模型

`userprofile/models.py` 定义 `Users`，表名 `user_profile`：

| 字段 | 类型 | 含义 | 说明 |
|---|---|---|---|
| `user_id` | int | 关联 `auth_user.id` | 非外键 |
| `name` | char | 用户名/登录名 | 与 `auth_user.username` 重复 |
| `openid` | char | **租户键 + API 令牌** | 由 MD5 生成 |
| `appid` | char | 应用标识 | 参与限流键 |
| `vip` | bool | 是否付费 | 无业务校验 |
| `vip_time` | datetime | 到期时间 | 无校验逻辑 |
| `developer` | bool | 开发者标记 | 未找到使用点 |
| `is_delete` | bool | 软删除 | 登录时不校验 |
| `t_code` | char | 事务码 | MD5 |
| `ip` | char | 注册 IP | 明文存储 |
| `link_to` / `link_to_id` | char/int | 关联对象 | 未找到明确用途 |
| `avatar` | char | 头像路径 | 位于 `media/<openid>/` |
| `create_time` / `update_time` | datetime | 时间戳 | 本地时区 |

**关键问题**：`openid` 既是租户标识，又是认证令牌，且没有过期/轮换/吊销机制。任何能读到 `openid` 的地方（前端 LocalStorage、日志、导出文件）都等于拿到该租户的永久钥匙。

#### 3.4.2 `userlogin`：登录

- 路由：`POST /login/`
- 逻辑（`userlogin/views.py`）：
  1. `django.contrib.auth.authenticate(username, password)` 校验 Django 账号；
  2. `auth.login(request, user)` 建立 Session（但前端并不使用 Session）；
  3. 查询 `Users.objects.get(user_id=user.id)`，返回 `openid`、`user_id`（实际是 `staff.id`）、`name`、`avatar` 等；
  4. 失败统一返回 `FBMsg.err_ret()` 结构。
- 无失败次数限制、无验证码、无锁定、无登录审计（未找到相关依据）。

#### 3.4.3 `userregister`：注册与演示数据

- 路由：`POST /register/`
- 逻辑（`userregister/views.py`，约 488 行）：
  1. 创建 `auth.User`；
  2. 创建 `Users`，`openid = Md5.md5(name)`（`MD5(name + str(datetime.now()))`）；
  3. 创建管理员 `staff` 记录；
  4. **批量生成演示数据**：公司、仓库、库位、41 个供应商/客户、商品、ASN、DN、司机、固定资产等；
  5. 创建 `media/<openid>/` 目录树。
- 风险：注册接口无频率限制、无邮箱/手机验证、无邀请码；**任意人可注册并触发大量写入**。

#### 3.4.4 `staff`：员工与角色

`staff/models.py`：

| 模型 | 表 | 关键字段 |
|---|---|---|
| `ListModel` | `staff` | `staff_name`、`staff_type`、`check_code`(默认 8888)、`error_check_code_counter`、`is_lock`、`openid`、`is_delete` |
| `TypeListModel` | `stafftype` | `staff_type`、`openid`、`is_delete` |

- `check_code` 是**作业复核码**，不是登录密码；默认 8888。
- `staff_type` 仅作为数据字段返回前端，**服务端不做任何权限判断**（`utils/permission.py` 恒真）。
- 端点：`GET/POST /staff/`、`GET /staff/type/`、`GET /staff/file/`、`GET|PUT|PATCH|DELETE /staff/<pk>/`。

### 3.5 主数据域

主数据域的共同特征：

- 表结构几乎一致：`*_name`、`*_city`、`*_address`、`*_contact`、`*_manager`、`creater`、`openid`、`is_delete`、`create_time`、`update_time`。
- 视图全部是 `ModelViewSet` 的 CRUD 包装，删除即 `is_delete=True`（软删除）。
- 序列化器基本是 `ModelSerializer` 全字段暴露，无字段级权限。
- 均提供 CSV 导出（部分应用有 `files.py`）。

#### 3.5.1 供应商 / 客户 / 公司

| 应用 | 表 | 字段（除公共字段外） | 排序 |
|---|---|---|---|
| `supplier` | `supplier` | `supplier_name`、`supplier_city`、`supplier_address`、`supplier_contact`、`supplier_manager`、`supplier_level` | `supplier_name` |
| `customer` | `customer` | `customer_name`、`customer_city`、`customer_address`、`customer_contact`、`customer_manager`、`customer_level` | `customer_name` |
| `company` | `company` | `company_name`、`company_city`、`company_address`、`company_contact`、`company_manager` | `company_name` |

- `*_level` 为 `BigIntegerField(default=1)`，语义上可能是分级/优先级，但**代码中未找到基于 level 的任何业务规则**。
- 三个应用的结构完全同构，属于典型的「复制粘贴式建模」。

#### 3.5.2 仓库 / 库位 / 库位尺寸 / 库位属性

| 应用 | 表 | 字段 | 说明 |
|---|---|---|---|
| `warehouse` | `warehouse` | `warehouse_name/city/address/contact/manager` | 仓库主数据；另有 `multiple/` 端点返回仓库下拉 |
| `binset` | `binset` | `bin_name`、`bin_size`、`bin_property`、`empty_label`、`bar_code` | 库位主数据；`empty_label` 由库存操作维护 |
| `binsize` | `binsize` | `bin_size` 等尺寸字典 | 字典表 |
| `binproperty` | `binproperty` | `bin_property` 等属性字典 | 只读端点，无写接口 |

**库位属性语义**（从 `stock/views.py` 反推）：

| 属性值 | 含义 | 对应库存字段 |
|---|---|---|
| `Normal` | 正常可售区 | `can_order_stock` |
| `Holding` | 暂存/待处理区 | `hold_stock` |
| `Damage` | 破损区 | `damage_stock` |
| `Inspection` | 质检区 | `inspect_stock` |

`binset.empty_label` 的维护逻辑：移库/上架时，源库位库存清零则置 `True`，目标库位入库则置 `False`。该字段是「空库位」查询的唯一依据，与 `stockbin` 实际记录可能不一致（无事务时可出现漂移）。

#### 3.5.3 商品与 7 类字典

`goods/models.py` 的 `ListModel`（表 `goods`）核心字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `goods_code` | char | 商品编码（业务主键，非数据库主键） |
| `goods_desc` | char | 描述 |
| `goods_supplier` | char | 默认供应商（字符串） |
| `goods_weight` | float | 单件重量 |
| `goods_w` / `goods_d` / `goods_h` | float | 长宽高 |
| `unit_volume` | float | 单件体积 |
| `goods_unit` | char | 单位（关联 `goodsunit`） |
| `goods_class` | char | 类别 |
| `goods_brand` | char | 品牌 |
| `goods_color` | char | 颜色 |
| `goods_shape` | char | 形状 |
| `goods_specs` | char | 规格 |
| `goods_origin` | char | 产地 |
| `safety_stock` | int | 安全库存 |
| `goods_cost` | float | 成本价 |
| `goods_price` | float | 销售价 |
| `bar_code` | char | 条码（扫码用） |
| `openid` / `is_delete` / `creater` / 时间戳 | — | 公共字段 |

7 类字典应用（`goodsunit`、`goodsclass`、`goodsbrand`、`goodscolor`、`goodsshape`、`goodsspecs`、`goodsorigin`）结构一致：

- 表名与 app 同名；
- 只有一个名称字段 + 公共字段；
- 提供完整 CRUD；
- 被 `goods` 以字符串引用，**删除字典项不会校验是否仍被商品使用**。

#### 3.5.4 司机与派车单

| 模型 | 表 | 字段 |
|---|---|---|
| `ListModel` | `driver` | `driver_name`、`license_plate`、`contact` |
| `DispatchListModel` | `dispatchlist` | `driver_name`、`dn_code`、`contact`（BigInteger，与 driver 的字符串类型不一致） |

- `DispatchListModel.contact` 使用 `BigIntegerField`，而 `driver.contact` 是 `CharField`，同一语义字段类型不一致。
- 派车单只提供 `list`/`retrieve`，创建逻辑在 DN 的 `dispatch` 动作中完成。

#### 3.5.5 固定资产

`capital/models.py`：`capital_name`、`capital_qty`、`capital_cost`，用于记录叉车、货架等资产的数量与单价。无折旧、无领用/归还记录（未找到相关依据）。

#### 3.5.6 运输费用

`payment/models.py` 的 `TransportationFeeListModel`（表 `transportationfee`）：

| 字段 | 含义 |
|---|---|
| `send_city` / `receiver_city` | 发货城市 / 收货城市 |
| `weight_fee` | 每单位重量费用 |
| `volume_fee` | 每单位体积费用 |
| `min_payment` | 最低收费 |
| `transportation_supplier` | 承运商 |

计费公式（`utils/datasolve.py` 的 `transportation_calculate`）：

```
费用 = max(重量 × weight_fee, 体积 × volume_fee, min_payment)
```

- 计费结果以 JSON 形式写入 `asnlist.transportation_fee` / `dnlist.transportation_fee`，**不生成独立账单**。
- 仅按「城市对」匹配，无时效、重量段、体积段、燃油附加费等维度。

#### 3.5.7 主数据域的共性问题

1. **无唯一约束**：供应商名、商品编码、库位名均可重复；重复数据只能靠人工发现。
2. **无引用完整性**：删除商品/库位/供应商不会检查是否被单据引用。
3. **软删除不彻底**：`is_delete=True` 后仍可能被 `get_object()` 直接取到（部分视图未过滤）。
4. **无审计**：`creater` 只记录姓名，修改人不记录，历史不可追溯。
5. **复制粘贴建模**：同类实体字段不一致（如 `contact` 类型），长期演进易出错。

### 3.6 入库作业域：`asn`

#### 3.6.1 数据模型

**`AsnListModel`（表 `asnlist`）**

| 字段 | 类型 | 含义 | 备注 |
|---|---|---|---|
| `asn_code` | char | 入库单号 | `ASN` + 日期 + 序号 |
| `asn_status` | int | 状态机（1-5） | 默认 1 |
| `total_weight` | float | 总重量 | 由明细汇总 |
| `total_volume` | float | 总体积 | 由明细汇总 |
| `total_cost` | float | 总成本 | 由明细汇总 |
| `supplier` | char | 供应商名称 | 字符串关联 |
| `bar_code` | char | 单据条码 | MD5 |
| `transportation_fee` | JSON | 运费明细 | `{weight_fee, volume_fee, ...}` |
| `creater` / `openid` / `is_delete` / 时间戳 | — | 公共字段 | — |

**`AsnDetailModel`（表 `asndetail`）**

| 字段 | 类型 | 含义 |
|---|---|---|
| `asn_code` | char | 所属单号 |
| `asn_status` | int | 明细级状态（与单头同步） |
| `supplier` | char | 供应商 |
| `goods_code` / `goods_desc` | char | 商品编码 / 描述 |
| `goods_qty` | int | 应收数量 |
| `goods_actual_qty` | int | 实收数量 |
| `sorted_qty` | int | 已分拣数量 |
| `goods_shortage_qty` | int | 短缺数量 |
| `goods_more_qty` | int | 多货数量 |
| `goods_damage_qty` | int | 破损数量 |
| `goods_weight` / `goods_volume` / `goods_cost` | float | 单件重量/体积/成本 |

> 注意：**明细表同样冗余了 `asn_status` 和 `supplier`**，状态需要单头/明细双写，天然存在不一致风险。

#### 3.6.2 状态机

```
[1] 草稿（新建，可编辑明细）
      │ POST /asn/preload/<pk>/   预加载（确认到货信息）
      ▼
[2] PreLoad
      │ POST /asn/presort/<pk>/   预分拣
      ▼
[3] PreSort
      │ POST /asn/sorted/<pk>/    分拣（登记短缺/多货/破损）
      ▼
[4] Sorted（部分收货） ── 全部收货 ──▶ [5] Sorted（完成）
      │ POST /asn/movetobin/<pk>/ 上架
      ▼
[5] 已上架（写入 stocklist / stockbin，后续由库存域接管）
```

| 状态码 | 业务含义（从代码反推） | 允许动作 |
|---|---|---|
| 1 | 草稿/待收货 | 编辑明细、预加载、删除 |
| 2 | 已预加载 | 预分拣 |
| 3 | 已预分拣 | 分拣（可多次，部分收货） |
| 4 | 分拣完成（存在差异） | 继续分拣或上架 |
| 5 | 已上架 | 只读 |

#### 3.6.3 端点清单

| 方法 | 路径 | ViewSet | 说明 |
|---|---|---|---|
| GET/POST | `/asn/list/` | `AsnListViewSet` | 列表 / 新建单头 |
| GET/PUT/PATCH/DELETE | `/asn/list/<pk>/` | `AsnListViewSet` | 详情 / 编辑 / 软删除 |
| GET/POST/PUT | `/asn/detail/` | `AsnDetailViewSet` | 明细列表 / 批量新增 / 批量更新 |
| GET | `/asn/detail/<pk>/` | `AsnDetailViewSet` | 明细详情 |
| GET | `/asn/viewprint/<pk>/` | `AsnViewPrintViewSet` | 打印数据（单头+明细聚合） |
| POST | `/asn/preload/<pk>/` | `AsnPreLoadViewSet` | 预加载 |
| POST | `/asn/presort/<pk>/` | `AsnPreSortViewSet` | 预分拣 |
| PUT | `/asn/sorted/` | `AsnSortedViewSet` | 批量分拣（按单号） |
| POST | `/asn/sorted/<pk>/` | `AsnSortedViewSet` | 单订单分拣 |
| PUT | `/asn/movetobin/` | `MoveToBinViewSet` | 批量上架 |
| POST | `/asn/movetobin/<pk>/` | `MoveToBinViewSet` | 单订单上架 |
| GET | `/asn/filelist/` | `FileListDownloadView` | 导出单头 CSV |
| GET | `/asn/filedetail/` | `FileDetailDownloadView` | 导出明细 CSV |

#### 3.6.4 关键实现细节

**（1）单号生成**

`asn/views.py` 中创建单头时：

```
order_day = timezone.now().strftime('%Y%m%d')
若最近一张单号中间 8 位等于今天 → 序号 + 1
否则 → 从 0001 重新开始
最终 asn_code = 'ASN' + yyyymmdd + 4 位序号
```

并发下两个请求可能拿到同一序号（无唯一约束、无锁）。

**（2）GET 请求的写副作用**

`get_queryset()` 中会清理**本月之前**的空草稿：

```python
empty_qs = AsnListModel.objects.filter(
    Q(openid=..., asn_status=1, is_delete=False) & Q(supplier=''))
cur_date = timezone.now()
date_check = relativedelta(day=1)
if empty_qs[i].create_time <= cur_date - date_check:
    empty_qs[i].delete()
```

影响：

- 一个「列表查询」会触发物理删除，无法审计；
- 该逻辑在 `AsnListViewSet` 与 `AsnViewPrintViewSet` 中各写了一遍（重复代码）；
- 删除条件依赖 `supplier=''`，若前端允许空供应商建单，数据会被静默清理。

**（3）分拣与上架的库存过账**

`AsnSortedViewSet` 与 `MoveToBinViewSet` 会：

1. 更新 `asndetail` 的 `goods_actual_qty`、`sorted_qty`、差异数量；
2. 写入/更新 `stocklist`（`asn_stock`、`can_order_stock` 等维度）；
3. 写入/更新 `stockbin`（库位库存）；
4. 写入 `qtyrecorder`（盘点流水）；
5. 更新 `binset.empty_label`；
6. 同步 `asnlist.asn_status` 与汇总重量/体积/成本。

上述 6 类写入**没有事务包裹**，任何一步异常都会留下半成品数据。

**（4）运费计算时机**

创建单头或预加载时，根据 `supplier`/`customer` 城市、总重量、总体积调用 `transportation_calculate`，结果写入 `transportation_fee` JSON。运费表缺失时返回 0，不报错。

### 3.7 出库作业域：`dn`

#### 3.7.1 数据模型

**`DnListModel`（表 `dnlist`）**

| 字段 | 类型 | 含义 |
|---|---|---|
| `dn_code` | char | 出库单号（`DN` + 日期 + 序号） |
| `dn_status` | int | 状态机（1-3，另有完成态） |
| `customer` | char | 客户名称 |
| `back_order_label` | bool | 是否欠货补发单 |
| `transportation_fee` | JSON | 运费 |
| `creater` / `bar_code` / `openid` / `is_delete` / 时间戳 | — | 公共字段 |

**`DnDetailModel`（表 `dndetail`）**

| 字段 | 含义 |
|---|---|
| `dn_code` / `dn_status` / `customer` | 单号 / 状态 / 客户 |
| `goods_code` / `goods_desc` | 商品 |
| `goods_qty` | 应收数量 |
| `pick_qty` | 应拣数量 |
| `picked_qty` | 已拣数量 |
| `intransit_qty` | 在途数量 |
| `delivery_qty` / `delivery_actual_qty` | 发货数量 / 实发数量 |
| `back_order_qty` | 欠货数量 |
| `goods_weight` / `goods_volume` / `goods_cost` | 单件属性 |

**`PickingListModel`（表 `pickinglist`）**

| 字段 | 含义 |
|---|---|
| `dn_code` / `dn_detail_id` | 所属单据 |
| `bin_name` | 拣货库位 |
| `goods_code` | 商品 |
| `pick_qty` / `picked_qty` | 应拣 / 已拣 |
| `picking_status` | 拣货状态 |
| `t_code` | 事务码（同一次拣货的批次标识） |
| `creater` / `openid` / 时间戳 | 公共字段 |

#### 3.7.2 状态机

```
[1] 新订单（可编辑）
      │ POST /dn/neworder/<pk>/      生成新订单（可选）
      │ POST /dn/orderrelease/       订单释放（分配库存）
      ▼
[2] 已释放（生成 pickinglist，占用 stockbin.pick_qty）
      │ GET  /dn/pickinglist/<pk>/  查看拣货任务
      │ PUT  /dn/picked/            确认拣货（可多次）
      ▼
[3] 已拣货（全部拣完）
      │ POST /dn/dispatch/<pk>/      发货（扣减库存、生成派车单）
      ▼
[3/完成] 已发货
      │ POST /dn/pod/<pk>/          签收回单
      ▼
完成
```

| 状态码 | 含义 | 关键动作 |
|---|---|---|
| 1 | 新订单/待释放 | 编辑明细、释放 |
| 2 | 已释放/拣货中 | 拣货、查看拣货单 |
| 3 | 已拣货/已发货 | 发货、POD |
| — | 欠货 | 生成 `back_order_label=True` 的新 DN |

#### 3.7.3 端点清单

| 方法 | 路径 | ViewSet | 说明 |
|---|---|---|---|
| GET/POST | `/dn/list/` | `DnListViewSet` | 列表 / 新建 |
| GET/PUT/PATCH/DELETE | `/dn/list/<pk>/` | `DnListViewSet` | 详情 / 编辑 / 删除 |
| GET/POST/PUT | `/dn/detail/` | `DnDetailViewSet` | 明细列表 / 新增 / 更新 |
| GET/DELETE | `/dn/detail/<pk>/` | `DnDetailViewSet` | 明细详情 / 删除 |
| GET | `/dn/viewprint/<pk>/` | `DnViewPrintViewSet` | 打印数据 |
| POST | `/dn/neworder/<pk>/` | `DnNewOrderViewSet` | 拆分/新建订单 |
| POST | `/dn/orderrelease/` | `DnOrderReleaseViewSet` | 订单释放（批量） |
| PUT | `/dn/orderrelease/<pk>/` | `DnOrderReleaseViewSet` | 单订单释放 |
| GET | `/dn/pickinglistfilter/` | `DnPickingListFilterViewSet` | 拣货任务筛选 |
| GET | `/dn/pickinglist/<pk>/` | `DnPickingListViewSet` | 拣货任务详情 |
| PUT | `/dn/picked/` | `DnPickedViewSet` | 批量确认拣货 |
| POST/PUT | `/dn/picked/<pk>/` | `DnPickedViewSet` | 单订单拣货 |
| POST | `/dn/dispatch/<pk>/` | `DnDispatchViewSet` | 发货 |
| POST | `/dn/pod/<pk>/` | `DnPODViewSet` | 签收回单 |
| GET | `/dn/filelist/` | `FileListDownloadView` | 导出单头 |
| GET | `/dn/filedetail/` | `FileDetailDownloadView` | 导出明细 |

#### 3.7.4 关键实现细节

**（1）订单释放（`DnOrderReleaseViewSet`）**

- 按商品汇总需求数量，从 `stockbin` 中按库位顺序查找可用数量；
- 写入 `pickinglist`（一个 DN 明细可能拆成多条拣货任务）；
- 增加 `stockbin.pick_qty`、`stocklist.pick_stock`；
- 若可用库存不足，按策略生成欠货（`back_order_label=True` 的新 DN）。

**（2）拣货确认（`DnPickedViewSet`）**

- 更新 `pickinglist.picked_qty`；
- 回写 `dndetail.picked_qty`；
- 更新 `stockbin.picked_qty`、`stocklist.picked_stock`；
- 全部拣完后将 `dn_status` 置为 3。

**（3）发货（`DnDispatchViewSet`）**

- 按已拣数量扣减 `stockbin.goods_qty`、`stocklist.goods_qty` / `can_order_stock`；
- 清理拣货占用（`pick_qty`、`picked_qty`）；
- 创建 `dispatchlist`（司机 + DN 号）；
- 更新 `binset.empty_label`。

**（4）POD（`DnPODViewSet`）**

- 记录签收结果，回写 `dndetail.delivery_actual_qty`；
- 差异部分可选择生成欠货单。

**（5）重复代码与体积**

- `dn/views.py` 约 144 KB，包含 12 个 ViewSet，多个类内部重复实现「汇总、校验、写库存」的代码块；
- `DnListViewSet.create()` 与 `DnNewOrderViewSet.create()` 逻辑高度重叠，但各自维护一份，修 bug 需双改。

### 3.8 库存与盘点域

#### 3.8.1 `stock`：库存总账与库位库存

**`StockListModel`（表 `stocklist`）—— 15 个数量维度**

| 维度 | 含义 | 主要变更时机 |
|---|---|---|
| `goods_qty` | 总库存 | 上架、发货、盘盈亏 |
| `onhand_stock` | 实有库存 | 同上 |
| `can_order_stock` | 可接单库存 | 上架、释放订单、发货 |
| `ordered_stock` | 已下单占用 | 订单释放/取消 |
| `inspect_stock` | 质检区库存 | 移库 |
| `hold_stock` | 暂存区库存 | 移库 |
| `damage_stock` | 破损区库存 | 移库、分拣破损 |
| `asn_stock` | 入库在途 | ASN 创建/预加载/上架 |
| `dn_stock` | 出库占用 | DN 创建/释放/发货 |
| `pre_load_stock` | 预加载量 | 预加载 |
| `pre_sort_stock` | 预分拣量 | 预分拣 |
| `sorted_stock` | 已分拣量 | 分拣 |
| `pick_stock` | 拣货占用量 | 释放订单 |
| `picked_stock` | 已拣量 | 拣货确认 |
| `back_order_stock` | 欠货量 | 欠货生成/补发 |

> 字段之间没有派生关系校验（例如 `goods_qty = onhand_stock + asn_stock + ...` 未在代码中强制），完全依赖每个 ViewSet 手工维护，是数据漂移的根源。

**`StockBinModel`（表 `stockbin`）**

| 字段 | 含义 | 备注 |
|---|---|---|
| `bin_name` / `goods_code` | 库位 + 商品 | 二元组合即业务主键 |
| `goods_qty` | 库位库存 | — |
| `pick_qty` | 拣货占用量 | 释放订单时增加 |
| `picked_qty` | 已拣未发量 | 拣货时增加，发货时扣减 |
| `bin_size` / `bin_property` | 冗余自 `binset` | 冗余导致两边不一致 |
| `t_code` | 事务码 | 用于追溯一次操作 |
| `create_time` | `auto_now_add=False` | **必须由代码显式赋值**，否则为 NULL/报错 |

**`StockBinViewSet.create()` 实为移库操作**（`stock/views.py`）：

```
输入：源库位 bin_name、目标库位、商品、数量
1. 校验源库位库存是否充足
2. 根据源/目标库位的 bin_property 决定增减哪个维度：
   Normal     → can_order_stock
   Holding    → hold_stock
   Damage     → damage_stock
   Inspection → inspect_stock
3. 扣减源 stockbin，新建/累加目标 stockbin
4. 更新 binset.empty_label
5. 写 qtyrecorder
```

风险点：

- 无事务：源扣减成功、目标写入失败 → 库存凭空消失；
- 无锁：并发移库可能超扣；
- `stockbin` 无 `is_delete` 字段，删除即物理删除；
- `create_time` 未显式赋值时行为依赖数据库默认值（SQLite 允许 NULL）。

#### 3.8.2 `cyclecount`：盘点

| 模型 | 表 | 用途 |
|---|---|---|
| `QTYRecorder` | `qtyrecorder` | 所有库存变动的流水（上架/移库/盘点/发货） |
| `CyclecountModeDayModel` | `cyclecountday` | 按日动态盘点任务 |
| `ManualCyclecountModeModel` | `manualcyclecount` | 手工盘点任务 |

盘点流程（`cyclecount/views.py`）：

1. 生成盘点任务：按库位/商品抽取账面数量 `goods_qty`；
2. 录入实盘数 `physical_inventory`，计算 `difference`；
3. 审核后按差异调整 `stockbin.goods_qty` 与 `stocklist` 对应维度；
4. 写 `qtyrecorder` 留痕。

盘点端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/PUT | `/cyclecount/` | 盘点任务列表 / 生成 / 更新 |
| GET | `/cyclecount/cyclecountrecorder/` | 全量盘点记录 |
| GET | `/cyclecount/qtyrecorviewset/` | 库存流水 |
| GET | `/cyclecount/getgoodscyclecount/` | 按商品聚合盘点 |
| GET/POST | `/cyclecount/manualcyclecount/` | 手工盘点 |
| GET | `/cyclecount/manualcyclecountrecorder/` | 手工盘点记录 |
| GET | `/cyclecount/filecyclecountday/` | 导出日盘点 |
| GET | `/cyclecount/filecyclecountall/` | 导出全量盘点 |
| GET | `/cyclecount/manualfilecyclecount/` | 导出手工盘点 |

问题：盘点调整同样无事务；`difference` 允许为负，但未校验调整后库存是否为负。

### 3.9 扫码域：`scanner`

#### 3.9.1 设计思路

GreaterWMS 的 PDA 扫码不是「扫一个码查一条数据」，而是**把一整段业务指令序列化后签名，生成一个条码**，扫码端解析后还原为本地操作队列。核心在 `utils/jwt.py`：

```python
JWT_SALT = "<硬编码常量，见 utils/jwt.py>"   # 不应入库

def create_token(payload):
    return jwt.encode(payload, JWT_SALT, algorithm='HS256')

def parse_payload(token):
    return jwt.decode(token, JWT_SALT, algorithms=['HS256'])
```

`scanner/views.py` 的 `ListViewSet.create()`：

1. 接收 `goods_code`、`bin_name`、`qty`、`dn_code` 等字段；
2. 生成 `bar_code = create_token(jwt_data)`；
3. 写入 `scanner` 表；
4. 前端将 `bar_code` 渲染为二维码/条码打印。

扫码端通过 `/scanner/list/<bar_code>/` 取回记录，或 `/scanner/query/` 解析 `bar_code` 得到原始 payload。

#### 3.9.2 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/scanner/` | 条码任务列表 / 生成指令 |
| POST | `/scanner/query/` | 解析 JWT 条码 |
| GET | `/scanner/list/<bar_code>/` | 按条码取任务 |
| GET | `/scanner/sanerpicking/` | 拣货任务（拼写错误：saner） |

#### 3.9.3 已确认缺陷

`scanner/views.py` 的 `get_queryset()` 中存在：

```python
if id is None:
    ...
```

但该作用域内只定义了 `bar_code`，没有 `id` 变量，**一旦执行到该分支会抛 `NameError`**。由于 `/scanner/sanerpicking/` 走 list 分支，该缺陷可能已被触发但被全局异常处理掩盖为 500。

### 3.10 支撑域

#### 3.10.1 `uploadfile`：批量导入

**端点（10 个）**

| 类型 | 路径 | 目标 |
|---|---|---|
| 初始化 | `/uploadfile/goodslistfile/` | 商品（先清空再导入） |
| 初始化 | `/uploadfile/supplierfile/` | 供应商 |
| 初始化 | `/uploadfile/customerfile/` | 客户 |
| 初始化 | `/uploadfile/capitalfile/` | 固定资产 |
| 初始化 | `/uploadfile/freightfile/` | 运费 |
| 追加 | `/uploadfile/goodslistfileadd/` | 商品 |
| 追加 | `/uploadfile/supplierfileadd/` | 供应商 |
| 追加 | `/uploadfile/customerfileadd/` | 客户 |
| 追加 | `/uploadfile/capitalfileadd/` | 固定资产 |
| 追加 | `/uploadfile/freightfileadd/` | 运费 |

**实现要点**

- 使用 `pandas.read_excel` / `read_csv` 解析，`openpyxl` 作为 xlsx 引擎；
- 表头支持中英文，根据 `language` 头映射列；
- 扩展名通过 `files.name.split('.')[1]` 判断 —— 文件名含多个点时（如 `a.b.xlsx`）会取错；
- 逐行插入，**不使用 `bulk_create`**，大文件性能差；
- 无文件大小/行数限制，无 MIME 校验（仅看扩展名）。

**高危逻辑（`uploadfile/views.py` 第 61-69 行）**

商品「初始化导入」在执行前会：

```python
self.get_queryset().delete()
goodsunit.objects.all().delete()
goodsclass.objects.all().delete()
goodsbrand.objects.all().delete()
goodscolor.objects.all().delete()
goodsshape.objects.all().delete()
goodsspecs.objects.all().delete()
goodsorigin.objects.all().delete()
```

后果：

1. 7 个 `objects.all().delete()` **没有 `openid` 条件**，会清空所有租户的字典数据；
2. 即使商品删除按 `get_queryset()` 限定了租户，字典表仍被全局清空；
3. `delete()` 为物理删除，无法恢复；
4. 操作无二次确认、无审计。

#### 3.10.2 `dashboard`：仪表盘

| 端点 | 逻辑 |
|---|---|
| `GET /dashboard/receipts/` | 近 14 天 `asn_status >= 4` 的收货量，按日期聚合为 `{date, value}` |
| `GET /dashboard/sales/` | 近 14 天 `dnlist` 发货量，按日期聚合 |

- 直接返回 ECharts 可消费的结构，无 serializer、无 filter；
- 聚合在 Python 侧完成（`for` 循环 + 字典计数），数据量大时性能差；
- 未按仓库/供应商/客户维度下钻。

#### 3.10.3 `throttle`：限流计数

- 仅有一个模型 `ListModel`（表 `throttle`），字段为 `openid`、`appid`、`ip`、`method`、`create_time` 等；
- `views.py`、`urls.py` 为空文件，**无对外端点**；
- 由 `utils/throttle.py` 直接读写。

### 3.11 `utils`：隐式基础库

| 文件 | 作用 | 关键实现/风险 |
|---|---|---|
| `auth.py` | DRF 认证类 | 令牌=openid；返回 `(True, user)` 顺序错误 |
| `permission.py` | DRF 权限类 | 恒 `True` |
| `throttle.py` | 自定义限流 | 读 `X-Forwarded-For`（可伪造）；每请求写库 |
| `page.py` | 分页器 | `page_size=30`，`max_page_size=1000` |
| `my_exceptions.py` | 全局异常处理 | 统一 `{detail: ...}` |
| `fbmsg.py` | 响应消息常量 | 中英文文案 |
| `datasolve.py` | 业务校验/编号/条码/运费 | `data_validate` 用正则拦 `script/select` |
| `jwt.py` | 条码签名 | `JWT_SALT` 硬编码 |
| `md5.py` | MD5 工具 | 用于 `openid`/`bar_code`/`t_code` |
| `upload.py` | 文件落盘 | 按 `openid` 分目录 |
| `websocket.py` | 站内聊天 | 模块级字典，单进程有效 |
| `apitag.py` | 枚举国际化 | 状态码 → 文案 |
| `views.py`（utils 下如有） | 通用视图 | 未找到相关依据 |

#### 3.11.1 `datasolve` 详解

| 函数 | 作用 | 实现要点 |
|---|---|---|
| `data_validate` | 输入安全校验 | 正则匹配 `script`、`select` 等关键字，命中即报错 |
| `asn_data_validate` | 生成 ASN 单号 | `ASN` + 日期 + 4 位序号 |
| `dn_data_validate` | 生成 DN 单号 | `DN` + 日期 + 4 位序号 |
| `secret_bar_code` | 生成条码 | **仅 Base64 编码，不是加密** |
| `transportation_calculate` | 计算运费 | `max(重量费, 体积费, 最低费)` |

> `data_validate` 的黑名单方式只能拦截最基础的注入尝试，且 Django ORM 本身已参数化查询，该函数更多是「形式合规」而非实质防护。

### 3.12 后端横切问题清单

| # | 问题 | 影响面 | 证据 |
|---|---|---|---|
| 1 | 无事务边界 | ASN/DN/stock/cyclecount 全部写路径 | 全仓库 `transaction.atomic` 0 命中 |
| 2 | 无行锁/乐观锁 | 同一库位并发移库、并发拣货 | `select_for_update` 0 命中 |
| 3 | 无幂等键 | 重试/双击导致重复扣减 | 无 `request_id`/`idempotency_key` |
| 4 | 状态双写 | 单头与明细各存 `status` | `asnlist`/`asndetail`、`dnlist`/`dndetail` |
| 5 | 读接口有写副作用 | 列表查询触发删除 | `asn/views.py` 第 62-68、1150-1157 行 |
| 6 | 跨租户写入 | 字典表全局 `delete()` | `uploadfile/views.py` 第 61-69 行 |
| 7 | 软删除不统一 | 部分表无 `is_delete` | `stockbin`、`cyclecountday`、`manualcyclecount` |
| 8 | 巨型视图文件 | 可维护性差 | `dn/views.py` 144 KB、`asn/views.py` 77 KB |
| 9 | 序列化器过宽 | 全字段暴露，含 `openid` | 各 `serializers.py` |
| 10 | 无审计日志 | 无法追责 | 仅有 `creater` 字段 |

---

## 4. 前端结构

### 4.1 两套前端的关系

仓库中存在两套并行前端：

| 目录 | 定位 | 技术栈 | 页面数 | 是否被后端托管 |
|---|---|---|---|---|
| `templates/` | **主前端**（PC 后台、全功能） | Quasar 1 + Vue 2 + Webpack 5 | 78 | 是（`templates/dist/spa`） |
| `app/` | **移动/PDA 前端**（功能子集） | Quasar 2 + Vue 3 + Vite | 20 | 否（独立构建/打包） |

从代码痕迹判断，`app/` 是后期新增的移动端工程，只实现了扫码与库存查询等少数场景；`templates/` 是历史主力，功能完整但技术栈停留在 Vue 2。

### 4.2 `templates/`（主前端）

#### 4.2.1 目录结构

```
templates/
├── public/
│   └── statics/baseurl.txt        # 后端地址（同步 XHR 读取）
├── src/
│   ├── boot/                      # 启动引导
│   │   ├── axios_request.js       # 5 个 axios 实例 + 拦截器（639 行）
│   │   ├── i18n.js                # 多语言
│   │   └── ...
│   ├── components/                # 通用组件
│   ├── layouts/                   # 布局（侧边栏/顶栏）
│   ├── pages/                     # 78 个页面，按业务分目录
│   ├── router/routes.js           # 14 个一级模块（406 行）
│   ├── store/                     # Vuex
│   └── statics/                   # 图片、字体
├── dist/spa/                      # 已提交的构建产物（220 个文件）
├── quasar.config.js
├── package.json
└── .eslintrc.js
```

#### 4.2.2 路由结构

`templates/src/router/routes.js` 定义 14 个一级模块：

| 模块 | 子页面 | 说明 |
|---|---|---|
| `dashboard` | 首页 | 收货/发货趋势 |
| `inbound` | `asn`、`preload`、`presort`、`sort`、`shortage`、`more`、`asnfinish` | 入库全流程 |
| `outbound` | `dn`、`freshorder`、`neworder`、`pickstock`、`pickedstock`、`pickinglist`、`shippedstock`、`backorder`、`pod` | 出库全流程 |
| `stock` | 库存总账、库位库存、移库、空库位 | 库存 |
| `goods` | 商品、单位、类别、品牌、颜色、形状、规格、产地 | 商品主数据 |
| `baseinfo` | 供应商、客户、公司、司机、资产、运费 | 基础资料 |
| `warehouse` | 仓库、库位、库位尺寸、库位属性 | 仓储配置 |
| `finance` | 运费、资产 | 财务辅助 |
| `staff` | 员工、员工类型 | 组织 |
| `driver` | 司机、派车单 | 运输 |
| `customerdn` | 按客户查看 DN | 查询视图 |
| `supplierasn` | 按供应商查看 ASN | 查询视图 |
| `uploadcenter` | 5 类初始化/追加导入 | 数据导入 |
| `downloadcenter` | 各类 CSV 导出 | 数据导出 |

#### 4.2.3 启动与请求链路

`templates/src/boot/axios_request.js` 的关键行为：

1. **同步 XHR 读配置**：页面加载时用 `XMLHttpRequest` 同步读取 `../../statics/baseurl.txt`，拿到后端地址；
2. **创建 5 个 axios 实例**：分别对应不同模块（避免全局拦截器互相干扰）；
3. **请求拦截器注入请求头**：
   - `token`：`LocalStorage.getItem('openid')`
   - `operator`：`LocalStorage.getItem('login_id')`
   - `language`：当前语言
4. **响应拦截器**：
   - 重写分页 `next`/`previous` 的相对路径；
   - 统一错误提示（按状态码 + 多语言）；
   - 401/403 清理本地登录态。

问题：

- 同步 XHR 已被现代浏览器标记为不推荐，主线程阻塞；
- 后端地址写在静态文件里，多环境部署需要改文件重新构建；
- 令牌存在 `LocalStorage`，任意 XSS 可直接窃取（且令牌永久有效）。

#### 4.2.4 构建与部署

| 项 | 内容 |
|---|---|
| 构建命令 | `quasar build`（输出 `dist/spa`） |
| 开发命令 | `quasar dev` |
| 产物托管 | 复制到 `templates/dist/spa`，由 Django `TemplateView` + 手写静态路由返回 |
| 已提交产物 | `git ls-files templates/dist` 共 220 个文件 |
| 环境变量 | 未使用 `.env`，无 `process.env` 区分环境（未找到相关依据） |

#### 4.2.5 依赖要点（`templates/package.json`）

| 依赖 | 版本 | 用途 |
|---|---|---|
| `quasar` | ^1.15.23 | UI 框架 |
| `@quasar/app` | ^2.2.10 | 构建工具 |
| `vue` | ^2.6 | 框架 |
| `vue-i18n` | ^8.24.4 | 多语言 |
| `echarts` / `vue-echarts-v3` | ^5 / — | 图表 |
| `qrcode` | — | 条码/二维码 |
| `vue-print-nb` | — | 单据打印 |
| `jszip` | — | 批量导出压缩 |
| `dexie` | — | IndexedDB 本地缓存 |
| `axios` | ^0.21 | HTTP |

### 4.3 `app/`（移动端）

#### 4.3.1 目录与路由

`app/src/router/routes.js` 仅 37 行，页面清单：

| 路径 | 页面 | 功能 |
|---|---|---|
| `/` | 首页 | 入口 |
| `/server` | 服务器配置 | 设置后端地址 |
| `/login` | 登录 | 账号密码 |
| `/scanapp` | 扫码容器 | 子路由容器 |
| `/scanapp/goods` | 商品查询 | 扫码查商品 |
| `/scanapp/goodsstock` | 商品库存 | 按商品查库存 |
| `/scanapp/binstock` | 库位库存 | 按库位查库存 |
| `/scanapp/emptybin` | 空库位 | 查询可用库位 |
| `/scanapp/handcount` | 手工盘点 | 录入实盘数 |
| `/scanapp/asnlist` / `asndetail` | 入库单 | 查看/收货 |
| `/scanapp/dnlist` / `dndetail` | 出库单 | 查看/拣货 |
| `/scanapp/pickinglist` | 拣货任务 | 拣货 |
| `/scanapp/equipment` | 设备信息 | 关于 |

#### 4.3.2 请求层

`app/src/boot/axios.js` 只有 7 行：

```javascript
import axios from 'axios'
export default ({ app }) => {
  app.config.globalProperties.$axios = axios
}
```

即：**没有拦截器、没有 baseURL、没有统一错误处理、没有令牌注入**。各页面自行拼接地址与请求头，导致：

- 令牌与 `operator` 传递不一致；
- 错误处理分散，用户体验不统一；
- 后端地址切换需要逐页修改。

#### 4.3.3 多端配置

`app/` 包含 Cordova、Capacitor、Electron、BEX 配置，可打包为 Android/iOS/桌面应用。但：

- 无签名/发布流水线（未找到相关依据）；
- 无离线同步机制（仅 LocalStorage 存登录态）；
- 无版本升级通道（未找到相关依据）。

### 4.4 两套前端对比

| 维度 | `templates/` | `app/` |
|---|---|---|
| 框架代际 | Vue 2 / Quasar 1 | Vue 3 / Quasar 2 |
| 构建工具 | Webpack 5 | Vite |
| 页面数 | 78 | 20 |
| 路由数 | 14 个一级模块 | 13 个页面 |
| 请求层 | 5 个 axios 实例 + 拦截器 | 全局裸 axios |
| 令牌注入 | 自动（拦截器） | 手写 |
| 错误处理 | 统一 + 多语言 | 分散 |
| i18n | vue-i18n 8 | vue-i18n 9 |
| 图表/打印 | 支持 | 不支持 |
| 离线能力 | Dexie（IndexedDB） | 无 |
| 构建产物 | 已提交到仓库 | 未提交（需本地构建） |
| 代码规范 | ESLint 6 + standard | ESLint 8 + prettier |

### 4.5 前端与后端的集成方式

1. **`templates/`**：构建产物放入 `templates/dist/spa`，Django 用 `TemplateView(template_name='dist/spa/index.html')` 返回首页，再由 `views.py` 的 `css/js/statics/fonts` 正则路由返回静态文件。
2. **`app/`**：不经过 Django 托管，直接访问后端 8008 端口（或 Nginx 反向代理），需要解决 CORS（当前全开，所以能跑通）。
3. **配置下发**：`templates` 靠 `baseurl.txt`，`app` 靠 `/server` 页面手工设置并存入 LocalStorage。

### 4.6 前端问题清单

| # | 问题 | 影响 |
|---|---|---|
| 1 | 双技术栈并存 | 维护成本翻倍、组件无法复用 |
| 2 | 同步 XHR 读配置 | 首屏阻塞、不推荐 |
| 3 | 令牌存 LocalStorage 且永久有效 | XSS 即接管 |
| 4 | 移动端无拦截器 | 请求头不一致、错误无统一处理 |
| 5 | 构建产物入库 | 仓库体积膨胀、产物与源码可能不同步 |
| 6 | 无前端测试 | 回归靠人工 |
| 7 | 无环境配置 | 多环境需改文件重构建 |
| 8 | i18n 文案分散 | 新增语言成本高 |

---

## 5. 公共与基础设施

### 5.1 `greaterwms/settings.py` 逐段解读

| 段落 | 内容 | 生产风险 |
|---|---|---|
| 基础路径与密钥 | `BASE_DIR`、`SECRET_KEY = get_random_secret_key()` | **每次启动密钥变化**，Session/签名全部失效，多进程也会不一致 |
| 调试与主机 | `DEBUG = True`、`ALLOWED_HOSTS = ['*']` | 异常页泄露堆栈与配置；任意 Host 头 |
| 应用注册 | 30 个业务应用 + `rest_framework`、`django_filters`、`corsheaders`、`drf_spectacular`、sidecar | — |
| 中间件 | CORS → Security → Session → Common → **（CSRF 已注释）** → Auth → Message → XFrameOptions | 无 CSRF 防护 |
| 模板 | `DIRS=[BASE_DIR/'templates']`，`APP_DIRS=True` | 与前端 `templates/` 同名，容易混淆 |
| 数据库 | SQLite + `timeout=20` | 单写锁、并发差、无连接池 |
| 国际化 | `LANGUAGE_CODE='en'`、`USE_I18N=True`、`USE_L10N=True`、`USE_TZ=False`、`TIME_ZONE='Asia/Shanghai'` | 本地时间存储，跨时区易错 |
| 静态/媒体 | `STATIC_URL='/static/'`、`STATIC_ROOT=static_new`、`MEDIA_ROOT=media` | 静态目录命名混乱（static / static_new / statics） |
| OpenAPI | `SPECTACULAR_SETTINGS`，版本 2.1.48，禁用 schema 校验 | 文档与实际不一致时无告警 |
| DRF | 异常处理器、JSON+CSV 渲染、自定义认证/权限/限流、`DjangoFilterBackend` | 见第 2.5 节 |
| 日志 | `logs/server.log`（100MB×5）、`logs/error.log`（100MB×3）、console | 日志写仓库目录，容器重建丢失 |
| CORS | 允许凭证 + 允许所有源 | 任意站点可带 Session 读取数据 |
| 限流参数 | `ALLOCATION_SECONDS=1`，各方法 500 次 | 阈值形同虚设 |
| JWT | `JWT_TIME = 20 年` | 与扫码条码共用常量，语义混淆 |

### 5.2 `greaterwms/urls.py` 路由总表

| 路径 | 目标 | 说明 |
|---|---|---|
| `/admin/` | `admin.site.urls` | Django Admin，无额外保护 |
| `/` | `TemplateView('dist/spa/index.html')` | SPA 首页 |
| `/myip/` | `views.myip` | 返回服务器出口 IP（依赖 `8.8.8.8`） |
| `/asn/`、`/dn/`、`/stock/` … | 30 个应用 include | 业务 API |
| `/login/`、`/register/` | 认证应用 | 登录/注册 |
| `/api-auth/` | `rest_framework.urls` | DRF 登录/登出（Session） |
| `/favicon.ico`、`/css/*`、`/js/*`、`/statics/*`、`/fonts/*` | `views.*` 手写文件流 | SPA 静态资源 |
| `/robots.txt` | `views.robots` | **读取 `BASE_DIR + path`，但仓库无 `robots.txt`**，必然 500/404 |
| `/media/<path>` | `django.views.static.serve` | 上传文件 |
| `/static/<path>` | `views.return_static` | `static_new/` |
| `/api/` | `SpectacularAPIView` | OpenAPI schema |
| `/api/debug/` | `SpectacularSwaggerView` | Swagger UI |
| `/api/docs/` | `SpectacularRedocView` | Redoc |

### 5.3 SPA 静态托管实现（`greaterwms/views.py`）

```python
def css(request):
    path = BASE_DIR + request.path_info
    return StreamingHttpResponse(FileWrapper(open(path, 'rb')))
```

- 四个函数（`css`、`js`、`statics`、`fonts`）逻辑相同，只靠正则前缀区分；
- `open()` 未关闭（依赖 `FileWrapper` 与 GC）；
- 路径直接拼接 `request.path_info`，**存在路径穿越风险**（`../`），但 Django 会先规范化 URL；
- 无 `Cache-Control`、`ETag`、`Content-Type` 显式设置；
- `robots()` 直接 `open(BASE_DIR + request.path_info)`，仓库无该文件，必然异常。

### 5.4 `asgi.py`：HTTP 与 WebSocket 分发

```python
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(websocket_application)),
})
```

- HTTP 走 Django；WebSocket 走 `utils/websocket.py` 的自定义路由；
- WebSocket 使用 `AuthMiddlewareStack`，但聊天逻辑并未校验用户身份；
- 未配置 `ALLOWED_HOSTS` 校验的 WS 来源限制。

### 5.5 WebSocket 聊天实现

`utils/websocket.py`：

```python
CONECTINGS = {}   # 模块级字典，进程内有效

async def websocket_application(scope, receive, send):
    # 按 channel 名保存 send，收到消息后转发给对端
```

限制：

- **仅单进程有效**：多 worker 部署时对端可能不在同一进程；
- 无鉴权、无房间权限、无消息持久化；
- 无心跳/重连策略（前端未找到相关依据）；
- 断线不清理字典，长期运行内存泄漏。

### 5.6 日志

| 项 | 配置 |
|---|---|
| 文件 | `logs/server.log`（INFO+，100MB×5）、`logs/error.log`（ERROR+，100MB×3） |
| 控制台 | StreamHandler，INFO+ |
| 格式 | `[时间][模块.函数():行号] [级别] 消息` |
| 目录创建 | 启动时若不存在则 `os.makedirs` |

问题：

- 日志目录在仓库根，容器重建即丢失（无卷挂载）；
- 无请求 ID/租户 ID/操作人上下文，无法串联一次业务；
- 无访问日志（`django.server` 未配置）；
- 日志中可能包含请求体（部分视图 `print`/`logger.info` 直接输出 data），有敏感信息泄露风险。

### 5.7 国际化与本地化

- 前端内置 11 种语言包：`ar`、`de`、`en-US`、`fr`、`it`、`ja`、`pt`、`ru`、`sp`、`zh-hans`、`zh-hant`（`templates/src/i18n`、`app/src/i18n`）；
- 默认语言 `en-US`：`LocalStorage` 无 `lang` 时写入并固定为 `en-US`（`templates/src/boot/i18n.js`）；
- 语言通过请求头 `language` 传递，后端在导出/枚举文案时使用；
- 前端 `templates` 使用 `vue-i18n` 8，`app` 使用 `vue-i18n` 9；
- 后端未使用 Django 的 `gettext` 体系（未找到 `locale/` 目录与 `.po` 文件）。

### 5.8 静态资源与媒体目录

| 目录 | 用途 | 是否入库 | 说明 |
|---|---|---|---|
| `static/` | 早期静态资源 | 少量 | 与 `static_new` 共存 |
| `static_new/` | `collectstatic` 目标 | 201 个文件 | 已被提交 |
| `templates/dist/` | SPA 构建产物 | 220 个文件 | 已被提交 |
| `media/` | 用户上传（头像、导入文件） | 仅 `__init__.py` | 运行时按 `openid` 建子目录 |
| `statics/` | 前端 `public/statics` | `baseurl.txt` | 与 `static` 命名冲突 |

> 三种命名（`static` / `static_new` / `statics`）并存，是历史遗留，新人极易踩坑。

### 5.9 异常处理与响应

- `utils/my_exceptions.py` 的 `custom_exception_handler` 将 DRF 异常统一为 `{detail: ...}`；
- 业务错误使用 `APIException({"detail": ...})`；
- 成功响应直接返回序列化数据，无统一 `code/message/data` 包装；
- 未捕获异常在 `DEBUG=True` 下返回 HTML 调试页，前端 axios 解析 JSON 会二次报错。

### 5.10 分页与过滤

```python
class MyPageNumberPagination(PageNumberPagination):
    page_size = 30
    max_page_size = 1000
    page_size_query_param = 'max_page'
    page_query_param = 'page'
```

- 列表接口默认 30 条，最大 1000 条；
- 前端通过 `max_page` 控制每页数量；
- 无游标分页，深分页（`page=10000`）性能差；
- `asn/page.py`、`dn/page.py` 在分页响应中附加 `supplier_list` / `customer_list`，属于「接口内嵌字典」的耦合设计。

### 5.11 OpenAPI 文档

- `drf-spectacular` 自动生成 schema；
- `/api/debug/`（Swagger）与 `/api/docs/`（Redoc）在 `utils/auth.py` 中被显式跳过认证；
- schema 未声明安全方案（`SECURITY`），文档与实际鉴权不一致；
- 由于 `ALLOWED_HOSTS=['*']` 且无认证，**任何能访问站点的人都能看到全部接口结构**。

---

## 6. 构建、部署与运维

### 6.1 部署相关文件清单

| 文件 | 作用 | 状态 |
|---|---|---|
| `Dockerfile` | 多阶段构建（backend / front） | 存在缺陷 |
| `Dockerfile.txt` | 与 `Dockerfile` 内容一致的副本 | 冗余 |
| `docker-compose.yml` | 两服务编排（front / backend） | 使用预构建镜像 |
| `nginx.conf` | TLS 终止、反向代理、静态 alias | 含占位符与旧协议 |
| `supervisord.conf` | 守护 Daphne | 配置可用但权限过高 |
| `backend_start.sh` | 生成迁移、执行迁移、启 supervisor | 不推荐 |
| `web_start.sh` | 安装依赖、构建、运行开发服务器 | 不推荐 |
| `.github/workflows/ci.yml` | CI | 见第 7 章 |
| `.github/workflows/security.yml` | 安全扫描 | 见第 7 章 |
| `.dockerignore` | — | **不存在** |

### 6.2 `Dockerfile` 逐段分析

#### 6.2.1 backend 阶段

```dockerfile
FROM --platform=linux/amd64 python:3.8.10-slim AS backend
RUN mkdir -p /GreaterWMS/templates
ADD ./requirements.txt /GreaterWMS/requirements.txt
COPY ./backend_start.sh /GreaterWMS/backend_start.sh
WORKDIR /GreaterWMS
ENV port = ${port}
RUN apt-get update --fix-missing && apt-get upgrade -y
RUN apt-get install build-essential -y
RUN apt-get install supervisor -y
RUN python3 -m pip install --upgrade pip
RUN pip3 install supervisor
RUN pip3 install -U 'Twisted[tls,http2]'
RUN pip3 install -r requirements.txt
RUN pip3 install daphne
RUN chmod +x /GreaterWMS/backend_start.sh
CMD ["/GreaterWMS/backend_start.sh"]
```

问题：

| # | 问题 | 影响 |
|---|---|---|
| 1 | `ENV port = ${port}` 语法错误（等号两侧有空格，变量未定义） | 构建告警/行为不确定 |
| 2 | `apt-get upgrade -y` | 镜像不可重现，可能引入不兼容 |
| 3 | 固定 `--platform=linux/amd64` | ARM 主机需模拟，性能差 |
| 4 | 反复 `pip install` | 层数多，缓存未利用（`requirements.txt` 先 COPY 是对的，但后续又单独装包） |
| 5 | 未创建非 root 用户 | 容器内 root，配合 compose `privileged: true` 风险放大 |
| 6 | 未执行 `collectstatic` | 依赖仓库内已提交的 `static_new` |
| 7 | 未声明 `EXPOSE`/健康检查 | 无法探活 |

#### 6.2.2 front 阶段

```dockerfile
FROM --platform=linux/amd64 node:14.19.3-buster-slim AS front
COPY ./templates/package.json /GreaterWMS/templates/package.json
COPY ./web_start.sh /GreaterWMS/templates/web_start.sh
ENV port = ${port}
RUN cd  /GreaterWMS/templates
RUN npm install -g npm --force
RUN npm install -g yarn --force
RUN npm install -g @quasar/cli --force
RUN yarn install
RUN chmod +x /GreaterWMS/templates/web_start.sh
ENTRYPOINT ["/GreaterWMS/templates/web_start.sh"]
```

问题：

| # | 问题 | 影响 |
|---|---|---|
| 1 | `RUN cd /GreaterWMS/templates` 在子 shell 中执行，**不改变后续层的工作目录** | 下一层仍在 `/` |
| 2 | 未设置 `WORKDIR` | `yarn install` 在 `/` 找不到 `package.json`，**单独构建 front 阶段会失败** |
| 3 | 只 COPY 了 `package.json`，没有 `yarn.lock` | 依赖版本不可重现 |
| 4 | 未 COPY 源码 | 镜像内无 `src/`，只能靠 compose 绑定宿主机目录 |
| 5 | `ENTRYPOINT` 指向脚本，运行时才 `yarn install --force` | 启动慢、需联网、不可离线部署 |
| 6 | `web_start.sh` 最后执行 `quasar d` | **生产环境跑开发服务器** |

### 6.3 `docker-compose.yml` 分析

```yaml
version: '3.9'
services:
  front:
    # build: ...（已注释）
    image: greaterwms/greaterwms:front
    restart: always
    privileged: true
    ports: ['8080:8080']
    depends_on: [backend]
    volumes:
      - ./templates:/GreaterWMS/templates:rw
      - ./web_start.sh:/GreaterWMS/templates/web_start.sh
  backend:
    # build: ...（已注释）
    image: greaterwms/greaterwms:backend
    restart: always
    privileged: true
    volumes:
      - ./:/GreaterWMS/:rw
      - ./supervisord.conf:/etc/supervisor/supervisord.conf
    ports: ['8008:8008']
    environment:
      PYTHONUNBUFFERED: 1
```

问题：

1. **无法从源码直接构建**：`build:` 段被注释，只能拉取 Docker Hub 镜像；若镜像未更新，源码与运行不一致。
2. **`privileged: true`**：容器拥有宿主全部能力，违背最小权限。
3. **整仓 bind mount 到 `/GreaterWMS`**：宿主机任何改动直接生效，无发布边界；同时在 Linux 下会把宿主文件权限带入容器。
4. **数据库无独立服务**：SQLite 文件落在 bind mount 的仓库根，备份/迁移靠手工拷贝。
5. **无健康检查**：`depends_on` 只保证启动顺序，不保证后端可用。
6. **无资源限制**：CPU/内存无上限，异常时可拖垮宿主。
7. **无日志驱动配置**：日志无限增长（除应用自身 rotate）。
8. **端口直接暴露 8008**：绕过 Nginx，可被直接访问。

### 6.4 `nginx.conf` 分析

| 项 | 现状 | 问题 |
|---|---|---|
| 域名 | `{{ Domin Name }}` | 占位符未替换，且拼写错误（Domain） |
| 根目录 | `/path/to/GreaterWMS` | 占位符 |
| 证书 | `/path/to/GreaterWMS.pem/.key` | 占位符 |
| 80 端口 | `rewrite ^(.*)$ https://...$1` | 无 ACME 验证路径例外 |
| TLS 协议 | `TLSv1 TLSv1.1 TLSv1.2` | TLS 1.0/1.1 已废弃，缺少 1.3 |
| 加密套件 | 含 `!MD5` 等 | 未启用现代套件优先级 |
| HSTS | 未配置 | 无 `Strict-Transport-Security` |
| 访问日志 | `access_log off` | 无审计/排障依据 |
| WebSocket | `/websocket/` → `http://GreaterWMS/` | `X-Real_IP`、`X-Forwarded-for` 头名不规范，且 `proxy_pass` 多了尾斜杠会改写路径 |
| 超时 | 300s 全局 | 长事务易堆积 |
| 静态 | `/static/` → `static_new/`；`/media/` → `media/` | 与 Django 路由重复，职责不清 |
| HTTP/2 | 未启用 | 性能损失 |
| 安全头 | `X-Frame-Options`、`X-XSS-Protection`、`X-Content-Type-Options` | 缺少 CSP、Referrer-Policy、Permissions-Policy |

### 6.5 `supervisord.conf`

```ini
[program:greaterwms]
directory=/GreaterWMS/
user=root
command=daphne -b 0.0.0.0 -p 8008 greaterwms.asgi:application
autostart=true
autorestart=true
startsecs=0
stopwaitsecs=0
stdout_logfile=/GreaterWMS/greaterwms_server_access.log
stderr_logfile=/GreaterWMS/greaterwms_server_err.log
redirect_stderr=true
```

问题：

- `user=root`：应用以 root 运行；
- `startsecs=0`：进程刚启动就算成功，崩溃循环无法识别；
- `stopwaitsecs=0`：直接 SIGKILL，可能中断写库；
- 单进程 Daphne：无多 worker，CPU 利用不足；
- 日志写仓库根，未接入轮转（与 Django logging 重复）；
- 无 `environment` 注入，配置完全依赖代码默认值。

### 6.6 启动脚本

**`backend_start.sh`**

```bash
python3 manage.py makemigrations
python3 manage.py migrate
supervisord -c /etc/supervisor/supervisord.conf
```

- 在**生产容器启动时生成迁移**：不同实例可能生成不同迁移文件，schema 不可审计；
- `makemigrations` 无 `--check`，错误被忽略；
- `migrate` 失败后仍然启动 supervisor（无 `set -e`）；
- 无 `collectstatic`、无 `check --deploy`。

**`web_start.sh`**

```bash
cd /GreaterWMS/templates
yarn install --force
quasar build
quasar d
```

- 每次启动重新安装依赖并构建，启动时间以分钟计；
- 需要外网访问 npm registry；
- `quasar d` 是开发服务器（HMR、未压缩、无缓存头），不适合生产；
- 无失败退出处理。

### 6.7 人工部署流程（从脚本反推）

```
1. 准备 Linux 主机，安装 Docker / Docker Compose
2. git clone 仓库
3. 修改 nginx.conf 中的域名、路径、证书
4. docker compose up -d
   ├─ backend 容器：makemigrations → migrate → supervisord → daphne:8008
   └─ front 容器：yarn install → quasar build → quasar dev:8080
5. 宿主机安装 Nginx，将 nginx.conf 放入 conf.d 并 reload
6. 浏览器访问 https://<domain>/，由 Nginx 反代到 8008，Django 返回 SPA
7. 首次使用 /register/ 注册账号并生成演示数据
```

未找到依据的环节：数据库备份、日志收集、监控告警、升级回滚、多实例部署。

### 6.8 部署风险汇总

| 等级 | 风险 | 说明 |
|---|---|---|
| 高 | 生产跑 `quasar d` | 性能、安全、稳定性均不达标 |
| 高 | 启动时生成迁移 | schema 不可控 |
| 高 | 随机 `SECRET_KEY` | 重启后 Session/签名失效，多实例不一致 |
| 高 | root + privileged | 容器逃逸风险放大 |
| 中 | SQLite 单文件 | 并发写瓶颈、备份粒度粗 |
| 中 | 无健康检查 | 故障不能自愈 |
| 中 | Nginx 占位符/旧 TLS | 上线需人工改，易漏 |
| 低 | 无 `.dockerignore` | 构建上下文包含 `node_modules`、`.git`，镜像膨胀 |

### 6.9 改进建议（可直接落地）

**（1）Dockerfile（建议稿）**

```dockerfile
# ---------- front build ----------
FROM node:18-bullseye AS front-build
WORKDIR /app
COPY templates/package.json templates/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY templates/ ./
RUN yarn build

# ---------- runtime ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN adduser --disabled-password --uid 10001 appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=front-build /app/dist/spa ./templates/dist/spa
RUN python manage.py collectstatic --noinput && chown -R appuser:appuser /app
USER appuser
EXPOSE 8008
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8008/api/')"
CMD ["daphne","-b","0.0.0.0","-p","8008","greaterwms.asgi:application"]
```

**（2）启动脚本（建议稿）**

```bash
#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec daphne -b 0.0.0.0 -p 8008 greaterwms.asgi:application
```

**（3）配置外部化清单**

| 变量 | 建议来源 | 默认值 |
|---|---|---|
| `DJANGO_SECRET_KEY` | Secret Manager / K8s Secret | 无（必填） |
| `DJANGO_DEBUG` | 环境变量 | `false` |
| `DJANGO_ALLOWED_HOSTS` | 环境变量（逗号分隔） | 无 |
| `CORS_ALLOWED_ORIGINS` | 环境变量 | 无 |
| `DATABASE_URL` | 环境变量 | `sqlite:///db.sqlite3` |
| `LOG_LEVEL` | 环境变量 | `INFO` |

---

## 7. 工程规范与质量保障

### 7.1 命名与目录规范

| 维度 | 现状 | 评价 |
|---|---|---|
| 应用命名 | 全小写、无下划线（`goodsbrand`、`goodsspecs`） | 一致性好 |
| 模型命名 | 大量重复的 `ListModel` | 可读性差，需靠文件名区分 |
| 表名 | 短名（`asnlist`、`dndetail`） | 简洁但丢失领域前缀 |
| URL | 有的带尾斜杠、有的不带（`/goods/<pk>/` 正则未锚定 `$`） | 不一致 |
| 字段 | 部分拼写错误（`sanerpicking`、`Sanner`、`Domin Name`） | 影响可维护性 |
| 前端目录 | `pages/` 按业务分目录 | 合理 |

### 7.2 Python 代码规范

| 项 | 现状 |
|---|---|
| 格式化工具 | 无（无 `black`/`ruff`/`isort` 配置） |
| Lint 配置 | 根目录无 `.flake8`、`setup.cfg`、`pyproject.toml` |
| CI Lint | `flake8 --select=E9,F63,F7,F82`（仅语法级错误阻断），其余 `--exit-zero` |
| 类型检查 | 无 `mypy`/`pyright` |
| 导入规范 | 无 isort，部分文件内函数级 import |
| 行长度 | CI 第二遍限制 100，但不阻断 |

结论：Python 侧**实际上没有代码风格门禁**，只有「能否被解析」的检查。

### 7.3 前端代码规范

| 项 | `templates/` | `app/` |
|---|---|---|
| ESLint 版本 | 6 | 8 |
| 规则集 | `standard` + `plugin:vue/essential` | `plugin:vue/vue3-essential` + `prettier` |
| 解析器 | `babel-eslint` | `vue-eslint-parser` |
| EditorConfig | 有 | 有 |
| Prettier | 无独立配置 | 通过 ESLint 集成 |
| CI Lint | `npm run lint`（仅 templates） | **未纳入 CI** |

### 7.4 Git 与协作规范

| 项 | 现状 |
|---|---|
| 分支模型 | `master` + `S2B2B2C` + 多个 `dependabot/*` |
| 提交信息 | 以版本号为主（`V2.1.54`），无 Conventional Commits |
| 标签 | `V2.1.x` 格式，但代码内版本号滞后 |
| PR 模板 | `.github/PULL_REQUEST_TEMPLATE.md` |
| Issue 模板 | `bug_report.md`、`feature_request.md` |
| 依赖更新 | `.github/dependabot.yml` + 自动分支 |
| 发布说明 | `release-drafter.yml` |
| CODEOWNERS | 无 |
| 贡献指南 | README 中有简要说明 |

### 7.5 `ci.yml` 逐 Job 分析

| Job | 触发 | 关键步骤 | 问题 |
|---|---|---|---|
| `python-quality` | push / PR | 启 Postgres 13 → `check` → `makemigrations --check` → `migrate` → flake8 → `manage.py test` → coverage | Postgres 服务**未被使用**（settings 不读 `DATABASE_URL`，只支持 SQLite）；`makemigrations --check` 在无迁移文件时**应返回非零**；测试为空；覆盖率无阈值 |
| `frontend-quality` | push / PR | `npm ci` → lint → build（失败回退）→ `npm test` | 仅覆盖 `templates/`，不含 `app/`；`npm test` 是 `echo` 占位；构建失败可回退，不阻断 |
| `docker-build` | push / PR | Buildx 构建镜像 → `docker compose config` | 仅验证能构建，不启动/不探测；未扫描镜像漏洞 |
| `integration-tests` | push / PR | 启 Postgres → `manage.py test --tag=integration` | 仓库中**没有任何 `@tag('integration')` 用例**，该 Job 无实际验证 |
| `security-check` | push / PR | `safety check`、`bandit` | 第二次复跑会阻断（真实门禁），但报告生成与门禁混在同一 step，日志难读 |
| `deployment-readiness` | main/master | 仅 `echo` | 无实际部署动作 |

**关于 `makemigrations --check` 的说明**：本机未安装 Django，**未实测退出码**；按 Django 语义，当应用存在模型变更而未生成迁移文件时，该命令返回 1。本仓库 30 个应用均无迁移文件，因此该步骤在真实环境中极可能失败。若 GitHub Actions 显示为绿色，需核对：

1. 该工作流是否在该分支/该提交上实际执行；
2. 是否被 `continue-on-error` 或分支保护规则跳过；
3. 是否存在本地未提交的迁移文件。

### 7.6 `security.yml` 逐 Job 分析

| Job | 工具 | 门禁行为 | 问题 |
|---|---|---|---|
| `dependency-scan` | safety、pip-audit、npm audit | 先 `\|\| true` 生成 JSON，再复跑一次作为门禁 | 依赖版本老旧，复跑很可能直接失败；无豁免机制 |
| `code-security-scan` | bandit、semgrep | 同上（复跑不带 `\|\| true`） | bandit 默认低危也报，噪声大；semgrep `--config=auto` 结果不稳定 |
| `secrets-scan` | trufflehog | 复跑作为门禁 | 仓库内含 `utils/jwt.py` 硬编码盐值、`nginx.conf` 证书路径，可能被扫出 |
| `docker-security-scan` | trivy | 只上传 SARIF，不设置 `exit-code` | 发现漏洞也不阻断 |
| `security-summary` | — | 汇总 echo；“Fail on critical” 仅注释 | **关键的“严重漏洞阻断”未实现** |

### 7.7 测试现状

| 类型 | 数量 | 说明 |
|---|---|---|
| 单元测试 | 0 | 30 个 `tests.py` 均为空或只 import |
| 集成测试 | 0 | 无 `@tag('integration')` |
| API 测试 | 0 | 无 `APITestCase`/`APIClient` 使用 |
| 前端单测 | 0 | `npm test` 为占位 |
| E2E | 0 | 无 Playwright/Cypress |
| 性能测试 | 0 | 无 locust/k6 |
| 覆盖率 | 0% | coverage 可生成报告，但无阈值 |

### 7.8 仓库卫生

| # | 问题 | 依据 |
|---|---|---|
| 1 | 构建产物入库 | `templates/dist` 220 个文件、`static_new` 201 个文件 |
| 2 | 文件重复 | `Dockerfile` 与 `Dockerfile.txt` 内容一致 |
| 3 | 无 `.dockerignore` | 构建上下文包含 `.git`、`node_modules`、`dist` |
| 4 | 编码混用 | 部分中文文件在 UTF-8/GBK 下表现不一致 |
| 5 | 字符集声明不规范 | HTML 中 `charset="utf-8"` 写法 |
| 6 | 冗余应用 | `userprofile`、`throttle` 未挂载路由，`views.py` 为空 |
| 7 | 无效路由 | `/robots.txt` 指向不存在的文件 |
| 8 | 拼写错误 | `sanerpicking`、`Sanner`、`Domin Name` |
| 9 | 备份/临时文件 | `.github/trufflehog-exclude.txt` 存在，说明曾忽略扫描 |
| 10 | 无 CHANGELOG | 发布说明靠 Release Drafter 自动生成 |

### 7.9 质量门禁改进建议

| 优先级 | 措施 | 验证方式 |
|---|---|---|
| P0 | 提交初始迁移 + CI 强制 `makemigrations --check` | CI 红灯即阻断 |
| P0 | 为核心流程写 API 测试（下单→释放→拣货→发货） | 覆盖率 ≥ 60% |
| P0 | 修复 `DATABASE_URL` 或删除 Postgres service | CI 与实际一致 |
| P1 | 引入 ruff/black/isort | 统一格式 |
| P1 | 引入 mypy（至少 utils/ 与核心应用） | 类型检查通过 |
| P1 | 前端纳入 `app/` lint 与测试 | 两套前端同标准 |
| P2 | Trivy 设置 `exit-code: 1`（CRITICAL/HIGH） | 镜像漏洞阻断 |
| P2 | 增加契约测试（OpenAPI schema diff） | API 变更可见 |

---

## 8. 安全与风险点

### 8.1 威胁模型概述

| 项 | 内容 |
|---|---|
| 核心资产 | 库存数量与金额、客户/供应商资料、单据与作业记录、租户身份（openid） |
| 信任边界 | 浏览器 ↔ Nginx ↔ Django ↔ SQLite；租户 ↔ 租户 |
| 主要对手 | 外部未授权访问者、已登录的低权限员工、恶意/失误的内部操作 |
| 主要入口 | 30 个应用的 REST 端点、`/admin/`、`/register/`、`/uploadfile/`、文件上传、WebSocket |
| 现有防护 | 仅有一个「有 token 即放行」的认证类；无授权、无审计、无 WAF、无速率限制（有效阈值 500/s） |

### 8.2 认证风险

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| A1 | 令牌 = `openid`，永久有效 | `utils/auth.py`、`JWT_TIME=20 年` | 令牌泄露 = 永久接管租户 |
| A2 | 无刷新/轮换/吊销 | 无相关端点 | 无法强制下线 |
| A3 | 令牌存于 `LocalStorage` | `templates/src/boot/axios_request.js` | 任意 XSS 可窃取 |
| A4 | DRF 认证返回顺序错误 | `return (True, user)` | `request.user` 为布尔值，标准权限体系失效 |
| A5 | 登录无锁定/无验证码/无审计 | `userlogin/views.py` | 可暴力破解 |
| A6 | 注册无验证/无邀请码 | `userregister/views.py` | 任意人可开租户并写入大量演示数据 |
| A7 | `openid` 由 `MD5(name + 时间)` 生成 | `utils/md5.py` | 可预测性高；同名用户可被猜解 |
| A8 | 文档端点跳过认证 | `utils/auth.py` 首行判断 | `/api/`、`/api/debug/`、`/api/docs/` 全公开 |

### 8.3 授权与多租户隔离

**（1）权限类恒真**

```python
class Normalpermission(BasePermission):
    def has_permission(self, request, view):
        return True
    def has_object_permission(self, request, view, obj):
        return True
```

所有「权限」完全依赖每个视图的 `get_queryset()` 手写 `openid` 过滤，漏写一处就是越权。

**（2）已确认的跨租户读取（`warehouse/views.py` 第 145-153 行）**

```python
def get_queryset(self):
    id = self.get_project()
    if self.request.user:
        if id is None:
            return ListModel.objects.filter(is_delete=False)      # 无 openid
        else:
            return ListModel.objects.filter(id=id, is_delete=False) # 无 openid
```

`MultipleViewSet` 的列表与详情都未按租户过滤，任意登录用户可枚举**所有租户的仓库**。

**（3）已确认的跨租户删除（`uploadfile/views.py` 第 61-69 行）**

7 个字典表使用 `objects.all().delete()`，无 `openid` 条件，一次导入清空全平台字典。

**（4）其他风险**

- 大量视图用 `get_object()` + 手写 `openid` 校验，模式不统一，难以审计；
- `staff_type` 未参与任何判断，普通员工可调用管理员接口；
- 软删除记录可能被 `retrieve` 直接取到（取决于各视图是否过滤 `is_delete`）。

### 8.4 传输与会话安全

| # | 问题 | 证据 |
|---|---|---|
| T1 | CSRF 中间件被注释 | `settings.py` 第 72 行 |
| T2 | `CORS_ORIGIN_ALLOW_ALL=True` + `CORS_ALLOW_CREDENTIALS=True` | `settings.py` |
| T3 | 无 HSTS/CSP/Referrer-Policy | `nginx.conf` 仅 3 个安全头 |
| T4 | TLS 1.0/1.1 开启 | `ssl_protocols TLSv1 TLSv1.1 TLSv1.2` |
| T5 | `access_log off` | 无访问审计 |
| T6 | 8008 端口直接映射 | `docker-compose.yml` |

### 8.5 输入与文件安全

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| I1 | 输入校验为黑名单正则（`script`/`select`） | `utils/datasolve.py` | 绕过容易；对 ORM 无实质意义 |
| I2 | 条码「加密」仅 Base64 | `secret_bar_code` | 可伪造/篡改 |
| I3 | JWT 盐硬编码在源码 | `utils/jwt.py` | 可伪造扫码指令 |
| I4 | 文件类型仅看扩展名，且取 `split('.')[1]` | `uploadfile/views.py` | 多后缀文件名解析错误；可上传恶意内容 |
| I5 | 无文件大小/行数限制 | 同上 | DoS |
| I6 | 上传目录按 `openid` 拼接 | `utils/upload.py` | 若 `openid` 可控则路径穿越 |
| I7 | SPA 静态文件直接 `open(BASE_DIR + path)` | `greaterwms/views.py` | 路径拼接风险 |
| I8 | `robots()` 打开不存在的文件 | 同上 | 必然异常 |

### 8.6 数据一致性风险

| # | 问题 | 影响 |
|---|---|---|
| D1 | 无事务 | 多表写入部分成功，库存/单据不一致 |
| D2 | 无行锁/乐观锁 | 并发移库、并发拣货超扣 |
| D3 | 无幂等键 | 网络重试/双击导致重复扣减 |
| D4 | 单号生成无唯一约束 | 并发下重号 |
| D5 | 单头/明细状态双写 | 状态不一致 |
| D6 | 无迁移文件 | schema 不可审计、不可回滚 |
| D7 | 读接口删除数据 | 不可预期 |
| D8 | 软删除不统一 | 已删数据可能被引用/展示 |

### 8.7 敏感信息暴露

| # | 位置 | 内容 | 风险 |
|---|---|---|---|
| S1 | `utils/auth.py` | 错误信息区分「无 token」「用户不存在」 | 用户枚举 |
| S2 | `settings.py` | `DEBUG=True` | 堆栈/配置泄露 |
| S3 | `settings.py` | `ALLOWED_HOSTS=['*']` | Host 头攻击 |
| S4 | 各 serializer | 返回 `openid` | 令牌直接回显 |
| S5 | 日志 | 可能打印请求体 | 敏感数据落盘 |
| S6 | `/admin/` | 默认路径无 IP 限制 | 后台暴露 |
| S7 | `/myip/` | 返回服务器出口 IP | 信息泄露 |
| S8 | `/api/docs/` | 全量接口结构 | 攻击面泄露 |
| S9 | `nginx.conf` | 证书路径占位符 | 配置错误 |
| S10 | `utils/jwt.py` | 签名盐硬编码 | 条码伪造 |

### 8.8 依赖与供应链

| # | 风险 | 说明 |
|---|---|---|
| C1 | Django 4.1.2 已停止安全支持 | 后续 CVE 不再修复 |
| C2 | 依赖无哈希锁定 | 供应链投毒无法发现 |
| C3 | `node:14` / `python:3.8` 均已 EOL | 基础镜像无安全更新 |
| C4 | `apt-get upgrade -y` | 构建不可重现 |
| C5 | pandas 1.5.1 / numpy 1.23.4 | 旧版本，存在已知问题 |
| C6 | `djangorestframework-csv` 维护不活跃 | 长期风险 |

### 8.9 部署与运维安全

| # | 问题 | 证据 |
|---|---|---|
| O1 | 容器 root + `privileged: true` | `Dockerfile`、`docker-compose.yml` |
| O2 | 整仓 bind mount | 同上 |
| O3 | 生产跑 `quasar d` | `web_start.sh` |
| O4 | 启动时 `makemigrations` | `backend_start.sh` |
| O5 | 无备份/恢复脚本 | 未找到相关依据 |
| O6 | 无监控/告警 | 未找到相关依据 |
| O7 | 日志无集中收集 | `supervisord.conf` 写仓库根 |

### 8.10 风险登记册

| ID | 风险 | 等级 | 证据 | 修复建议 | 工作量 |
|---|---|---|---|---|---|
| R-01 | 令牌永久有效且可预测 | 极高 | `utils/auth.py`、`utils/md5.py` | 改用短时 JWT + 刷新令牌 + 吊销列表 | 5-8 人日 |
| R-02 | 权限恒真 | 极高 | `utils/permission.py` | 引入 RBAC（角色-权限表）+ 对象级校验 | 8-12 人日 |
| R-03 | 跨租户删除字典 | 极高 | `uploadfile/views.py` 61-69 | 加 `openid` 过滤 + 二次确认 | 0.5 人日 |
| R-04 | 跨租户读取仓库 | 高 | `warehouse/views.py` 145-153 | 统一 `get_queryset` 基类 | 2-3 人日 |
| R-05 | 无事务/无锁 | 极高 | 全仓库检索为 0 | 引入 service 层 + `transaction.atomic` + `select_for_update` | 8-12 人日 |
| R-06 | `DEBUG=True`/`ALLOWED_HOSTS=*` | 高 | `settings.py` | 配置外部化 | 1 人日 |
| R-07 | CORS 全开 + 凭证 | 高 | `settings.py` | 白名单 | 0.5 人日 |
| R-08 | CSRF 关闭 | 高 | `settings.py` 72 | 启用并配合 SameSite | 1 人日 |
| R-09 | 无迁移文件 | 高 | `migrations/` | 生成初始迁移并纳入 CI | 2-3 人日 |
| R-10 | 生产跑 dev server | 高 | `web_start.sh` | 改为静态产物 + Nginx | 2 人日 |
| R-11 | JWT 盐硬编码 | 高 | `utils/jwt.py` | 移入环境变量/密钥管理 | 0.5 人日 |
| R-12 | 任意注册 | 中 | `userregister/views.py` | 邀请码/邮箱验证/限流 | 2 人日 |
| R-13 | 文档全公开 | 中 | `utils/auth.py` | 生产关闭或加认证 | 0.5 人日 |
| R-14 | 依赖 EOL | 中 | `requirements.txt` | 升级 Django/Python/Node | 5-10 人日 |
| R-15 | 无审计日志 | 中 | 全仓库 | 增加操作日志表 + 中间件 | 3-5 人日 |
| R-16 | 限流可绕过且写库 | 中 | `utils/throttle.py` | 改用 Redis/边缘限流 | 1-2 人日 |
| R-17 | 文件上传无校验 | 中 | `uploadfile/views.py` | 类型/大小/病毒扫描 | 2 人日 |
| R-18 | 无备份/监控 | 中 | — | 定时备份 + 指标告警 | 3-5 人日 |
| R-19 | WebSocket 无鉴权 | 中 | `utils/websocket.py` | 握手校验 + 房间隔离 | 2 人日 |
| R-20 | 单号并发重号 | 低 | `utils/datasolve.py` | 数据库序列/唯一索引 | 1 人日 |

### 8.11 典型攻击路径（示例）

**路径 1：从注册到全平台数据**

```
POST /register/  → 获得 openid
GET  /warehouse/multiple/  → 列出所有租户仓库（无 openid 过滤）
POST /uploadfile/goodslistfile/  → 清空全平台 7 张字典表
```

**路径 2：令牌窃取**

```
任意 XSS/浏览器插件/共享终端 → 读取 LocalStorage.openid
→ 该 openid 永久有效，无需要密码即可调用全部接口
```

**路径 3：扫码条码伪造**

```
从公开仓库获取 JWT_SALT → 自行签发任意 payload 的条码
→ /scanner/query/ 解析后驱动 PDA 执行非法作业
```

### 8.12 STRIDE 映射

| 威胁 | 对应风险 |
|---|---|
| Spoofing（伪造） | R-01、R-11、R-12 |
| Tampering（篡改） | R-05、R-20、I2 |
| Repudiation（否认） | R-15（无审计） |
| Information Disclosure（泄露） | R-04、R-06、R-13、S1-S10 |
| Denial of Service（拒绝服务） | R-16、I5、SQLite 单写锁 |
| Elevation of Privilege（提权） | R-02、R-03 |

---

## 9. 总结与建议

### 9.1 值得肯定的方面

| # | 优点 | 证据 |
|---|---|---|
| 1 | **业务闭环完整** | ASN/DN/库存/盘点/扫码/导入导出/报表全链路均有实现 |
| 2 | **模块高度同构** | 30 个应用统一分层，新增主数据只需复制改造 |
| 3 | **多租户基础已具备** | 全表 `openid`，查询层已形成习惯 |
| 4 | **API 优先** | 所有能力都有 REST 端点，便于多端与集成 |
| 5 | **开箱即用** | 无外部中间件依赖，单机 + SQLite 即可跑通 |
| 6 | **二开友好** | 代码直白、无过度抽象，改动成本低 |
| 7 | **文档与模板齐全** | OpenAPI 三端点、PR/Issue 模板、Release Drafter |
| 8 | **国际化基础** | 中英文文案与导出已具备 |

### 9.2 主要问题（按领域）

| 领域 | 问题概要 |
|---|---|
| 安全 | 令牌永久、权限恒真、CORS 全开、CSRF 关闭、文档公开、JWT 盐硬编码 |
| 数据 | 无事务/无锁/无幂等/无迁移/双写状态/跨租户删除 |
| 工程 | 测试为 0、CI 与实际脱节、巨型视图文件、无服务层 |
| 部署 | 生产跑 dev server、启动时建迁移、root + privileged、无健康检查 |
| 前端 | 双技术栈并存、请求层不统一、构建产物入库 |
| 运维 | 无备份、无监控、无审计、日志不集中 |

### 9.3 改进路线图

#### 阶段一：止血（2-3 周）

| 任务 | 产出 | 验收 |
|---|---|---|
| 配置外部化 | `.env` + 环境变量读取 | `DEBUG=false` 下可启动 |
| 修复跨租户删除 | `openid` 过滤 + 二次确认 | 代码评审通过 |
| 修复跨租户读取 | 统一 `TenantQuerysetMixin` | 单测覆盖 |
| 关闭公开文档/Admin 限制 | 生产环境禁用或加认证 | 未登录不可访问 |
| 修正部署脚本 | 静态产物 + 非 root + 健康检查 | 镜像可启动并通过探活 |
| 告警：JWT 盐入环境变量 | 密钥管理 | 代码中无硬编码 |

#### 阶段二：筑基（4-6 周）

| 任务 | 产出 | 验收 |
|---|---|---|
| 认证重构 | 短时 JWT + 刷新 + 吊销 | 令牌 2h 过期，可强制下线 |
| RBAC | 角色-权限表 + 装饰器 | 越权返回 403 |
| 事务与锁 | service 层 + `atomic` + `select_for_update` | 并发测试无超扣 |
| 幂等 | 请求幂等键表 | 重试不重复扣减 |
| 迁移治理 | 初始迁移 + CI 校验 | `makemigrations --check` 通过 |
| 测试体系 | 核心流程 API 测试 | 覆盖率 ≥ 60% |

#### 阶段三：提质（6-8 周）

| 任务 | 产出 | 验收 |
|---|---|---|
| 拆分巨型视图 | `services/` + `selectors/` | 单文件 < 500 行 |
| 审计日志 | `audit_log` 表 + 中间件 | 关键操作可追溯 |
| 可观测性 | 指标 + 日志 + 告警 | 有 SLO 仪表盘 |
| 前端收敛 | 统一请求 SDK + 组件库 | 两套前端共用 |
| 性能优化 | 索引 + 分页优化 | P95 < 500ms |

#### 阶段四：演进（按需）

- 数据库切 PostgreSQL（引入 `DATABASE_URL`、`psycopg`）；
- 引入缓存（Redis）与异步任务（Celery/RQ）；
- 拆分为多服务（库存服务/单据服务/主数据服务）；
- 或迁移至 Cloudflare（见第 10 章）/ Bomiot 3.0。

### 9.4 目标分层架构（建议）

```
api/            # DRF ViewSet：参数解析、权限、序列化
  └─ services/  # 业务用例：事务边界、跨聚合编排
       └─ domain/   # 实体、值对象、状态机、领域规则
            └─ repositories/  # ORM 访问封装（可按需替换）
```

关键原则：

1. **一个业务动作 = 一个事务**；
2. **状态机只在一处实现**，单头/明细由领域对象统一推进；
3. **库存变更只能通过 `StockService`**，禁止视图直接写 `stocklist`/`stockbin`；
4. **所有写操作带幂等键与操作人**。

### 9.5 验收指标（建议）

| 维度 | 指标 | 目标 |
|---|---|---|
| 安全 | 高危风险关闭率 | 100% |
| 安全 | 未授权访问测试通过率 | 100% |
| 数据 | 并发移库差异数 | 0 |
| 数据 | 库存对账差异率 | < 0.01% |
| 质量 | 核心流程测试覆盖率 | ≥ 60% |
| 质量 | 迁移文件与模型一致性 | 100% |
| 性能 | 列表接口 P95 | < 500ms |
| 运维 | 备份恢复演练 | 每季度 1 次 |

### 9.6 技术路线选择建议

| 选项 | 适合场景 | 代价 | 建议 |
|---|---|---|---|
| **A. 继续维护 2.x Django** | 已有二开、团队熟悉 Python | 安全/一致性问题需自修 | 短期首选（配合阶段一/二） |
| **B. 迁移 Bomiot 3.0** | 希望跟随官方主线 | 生态/资料较少，需评估 | 先做 PoC |
| **C. 迁移 Cloudflare** | 希望免运维、全球加速、边缘计算 | 重写成本高 | 按第 10 章分阶段 |
| **D. 自研重写** | 业务差异大 | 成本最高 | 不推荐全量重写 |

**推荐组合**：短期 A（止血 + 筑基）→ 中期评估 C 的边缘前置（方案 C）→ 长期根据业务量决定是否重写核心。

---

## 10. Cloudflare 迁移方案

> 说明：本章中的产品能力、配额与计费均以 Cloudflare 官方文档当前口径为准；具体数值会随套餐与时间变化，落地前需再次核对。工期与人力为基于代码规模的估算（假设团队熟悉 TypeScript）。

### 10.1 可行性判断

#### 10.1.1 可以直接搬迁的部分

| 能力 | 目标实现 | 说明 |
|---|---|---|
| 静态前端 | Cloudflare Pages | `templates/dist/spa` 直接上传，全球 CDN |
| REST API | Workers + Hono | 路由、中间件、校验均可实现 |
| 关系数据 | D1（SQLite） | 与现有 SQLite 语义最接近 |
| 文件/导入导出 | R2 | 替代 `media/`，支持预签名 URL |
| 定时任务 | Cron Triggers | 替代「读接口删草稿」等副作用 |
| 异步任务 | Queues | 导入、导出、通知 |
| 站内聊天 | Durable Objects + WebSocket Hibernation | 替代进程内字典 |
| 报表缓存 | KV / Cache API | 仪表盘聚合结果 |
| 安全防护 | WAF + Rate Limiting + Turnstile + Access | 替代自研限流 |
| 可观测 | Logpush + Tail Workers + Analytics Engine | 替代本地日志 |

#### 10.1.2 不能直接搬迁、必须重写的部分

| 现有实现 | 原因 | 处理方式 |
|---|---|---|
| Django ORM / migrations | Workers 无 Python 运行时（Python Workers 能力有限） | 重写为 TypeScript + SQL |
| DRF ViewSet / Serializer | 框架不存在 | 用 Hono + zod 重写 |
| pandas 导入 | Workers 无文件系统、CPU 受限、无 pandas | 前端 SheetJS 解析后上传 JSON，或转 Container |
| `transaction.atomic` / `select_for_update` | D1 不支持交互式事务与行锁 | Durable Object 串行化 + 乐观锁 |
| 本地文件系统（`media/`、`logs/`） | Workers 无持久文件系统 | R2 + Logpush |
| 进程内 WebSocket 字典 | 多实例不共享 | Durable Object |
| SQLite 自定义函数/复杂 JOIN | D1 能力受限（无自定义函数、部分 PRAGMA） | 改写 SQL / 应用层聚合 |
| `pandas` 导出 Excel | 无 openpyxl | 改为 CSV / 前端生成 xlsx |

#### 10.1.3 结论

- **不能「原样搬运」**：Django 应用整体无法在 Workers 上运行。
- **可以「分阶段重建」**：数据模型与 API 契约可保留，业务逻辑需重写。
- **推荐路径**：先边缘前置（低风险验证），再主数据重写，最后库存/单据重写。

### 10.2 三种迁移方案对比

| 维度 | 方案 A：边缘原生重写 | 方案 B：Containers 托管 Django | 方案 C：仅边缘前置 |
|---|---|---|---|
| 架构 | Pages + Workers + D1 + R2 + DO | Cloudflare Containers 跑现有镜像 + Hyperdrive | Cloudflare CDN/WAF/DNS + 源站 Django |
| 代码改动 | 全量重写（TypeScript） | 几乎不改 | 不改 |
| 工期（估） | 10-14 周 / 2-3 人 | 1-2 周 / 1-2 人 | 3-5 天 / 1 人 |
| 运维负担 | 最低（无服务器） | 中（仍需维护镜像/DB） | 高（继续维护服务器） |
| 性能 | 边缘低延迟；D1 有单写限制 | 取决于容器区域与 DB | 源站性能不变 |
| 成本 | 按量，低基数高弹性 | 容器常驻 + DB + 流量 | CDN 费用 + 源站 |
| 风险 | 重写风险、D1/DO 适配 | 冷启动/区域限制 | 不解决根本问题 |
| 适合 | 长期产品化 | 快速上云/过渡 | 立即降风险 |

**推荐组合**：**C → B（可选） → A**。先用 C 在 1 周内获得 WAF/缓存/TLS 收益，同时用 B 验证容器化可行性；确认长期投入后再启动 A。

### 10.3 目标架构（方案 A）

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare 边缘                            │
│                                                                 │
│  Pages（Quasar 产物）                                            │
│      │                                                          │
│      ▼                                                          │
│  Workers（Hono API Gateway）                                     │
│   ├─ 认证/租户解析（JWT + KV 吊销列表）                          │
│   ├─ 限流（Rate Limiting + 租户配额）                            │
│   ├─ 路由：/asn /dn /stock /goods …（保持兼容）                   │
│   ├─ 读：D1（主数据 + 单据 + 余额快照）                           │
│   ├─ 写：Durable Object「TenantWriter」串行化                     │
│   ├─ 文件：R2（预签名上传/下载）                                  │
│   └─ 异步：Queues（导入/导出/通知）                               │
│                                                                 │
│  Durable Objects                                                 │
│   ├─ TenantWriter（每租户一个）：库存过账、单号生成、状态机         │
│   └─ ChatRoom（每租户/频道一个）：WebSocket 聊天                   │
│                                                                 │
│  Cron Triggers：草稿清理、盘点任务生成、日报聚合                   │
│  Workflows：大文件导入、跨系统同步（可选）                         │
└─────────────────────────────────────────────────────────────────┘
        │                    │                     │
        ▼                    ▼                     ▼
      D1                   R2                   KV
  （关系数据）          （对象存储）          （会话/缓存/开关）
```

### 10.4 组件映射表

| 现有组件 | Cloudflare 替代 | 迁移要点 |
|---|---|---|
| Django URLconf | Hono 路由 | 保留路径与尾斜杠兼容 |
| DRF ViewSet | Hono handler + service | 拆分「解析/校验/业务/序列化」 |
| DRF Serializer | zod schema | 入参校验 + 出参 DTO |
| django-filter | 查询构造器 | 白名单字段 + 参数化 SQL |
| 分页器 | 统一分页工具 | 保持 `count/next/previous/results` |
| `utils/auth.py` | JWT 中间件 | `Authorization: Bearer`，兼容 `token` 头过渡 |
| `utils/permission.py` | RBAC 中间件 | 角色-权限表 + 资源级校验 |
| `utils/throttle.py` | Rate Limiting + DO 计数 | 阈值按租户/IP/端点配置 |
| `transaction.atomic` | DO 串行 + `batch()` | 单租户写入串行化 |
| `select_for_update` | 乐观锁 `version` 字段 | `UPDATE ... WHERE version = ?` |
| `JSONField` | TEXT 存 JSON | 查询用 `json_extract` |
| `auto_now_add` | 应用层写入 | 统一 UTC ISO8601 |
| `MEDIA_ROOT` | R2 bucket | 按 `tenant_id/` 前缀 |
| `LOGGING` | Logpush + Tail Worker | 结构化 JSON 日志 |
| `manage.py` 命令 | `wrangler` 脚本 + Cron | 迁移/回填用脚本 |
| WebSocket 聊天 | Durable Object + Hibernation | 按租户分房间 |
| `drf-spectacular` | OpenAPI 手写/生成 | 用 `@hono/zod-openapi` |

### 10.5 数据模型与 D1 设计

#### 10.5.1 命名与类型映射

| Django/SQLite | D1 建议 | 说明 |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `TEXT PRIMARY KEY`（ULID） | 分布式友好、可排序 |
| `CharField(max_length=255)` | `TEXT` | D1 不强制长度 |
| `BigIntegerField` | `INTEGER` | 数量 |
| `FloatField`（金额） | `INTEGER`（分） | 避免浮点误差 |
| `BooleanField` | `INTEGER`（0/1） | SQLite 习惯 |
| `DateTimeField` | `TEXT`（ISO8601 UTC）或 `INTEGER`（epoch ms） | 二选一，全局统一 |
| `JSONField` | `TEXT` + `json_extract` | 或拆表 |
| `is_delete` | `deleted_at TEXT` | 可审计的软删除 |
| `openid` | `tenant_id TEXT NOT NULL` | 保留兼容列名也可 |
| `creater` | `created_by TEXT` | 存用户 ID 而非姓名 |

#### 10.5.2 必备新增表

**（1）租户与用户**

```sql
CREATE TABLE tenant (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',
  created_at    TEXT NOT NULL
);

CREATE TABLE app_user (
  id            TEXT PRIMARY KEY,
  tenant_id     TEXT NOT NULL,
  username      TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role_id       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',
  created_at    TEXT NOT NULL,
  UNIQUE (tenant_id, username)
);

CREATE TABLE role (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  name       TEXT NOT NULL,
  permissions TEXT NOT NULL   -- JSON 数组
);
```

**（2）库存台账（append-only）**

```sql
CREATE TABLE stock_ledger (
  id              TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  bin_id          TEXT NOT NULL,
  goods_id        TEXT NOT NULL,
  event_type      TEXT NOT NULL,   -- ASN_SORT/ASN_PUTAWAY/MOVE/PICK/DISPATCH/COUNT_ADJUST
  qty_delta       INTEGER NOT NULL,
  state_from      TEXT,
  state_to        TEXT,
  ref_type        TEXT,            -- ASN/DN/CYCLE_COUNT
  ref_id          TEXT,
  idempotency_key TEXT,
  created_by      TEXT,
  created_at      TEXT NOT NULL
);
CREATE INDEX idx_ledger_tenant_bin ON stock_ledger(tenant_id, bin_id, goods_id);
CREATE UNIQUE INDEX uq_ledger_idem ON stock_ledger(tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
```

**（3）余额快照（可重建）**

```sql
CREATE TABLE stock_balance (
  tenant_id      TEXT NOT NULL,
  goods_id       TEXT NOT NULL,
  goods_qty      INTEGER NOT NULL DEFAULT 0,
  can_order_qty  INTEGER NOT NULL DEFAULT 0,
  asn_qty        INTEGER NOT NULL DEFAULT 0,
  pick_qty       INTEGER NOT NULL DEFAULT 0,
  picked_qty     INTEGER NOT NULL DEFAULT 0,
  version        INTEGER NOT NULL DEFAULT 0,
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (tenant_id, goods_id)
);

CREATE TABLE bin_balance (
  tenant_id  TEXT NOT NULL,
  bin_id     TEXT NOT NULL,
  goods_id   TEXT NOT NULL,
  qty        INTEGER NOT NULL DEFAULT 0,
  pick_qty   INTEGER NOT NULL DEFAULT 0,
  picked_qty INTEGER NOT NULL DEFAULT 0,
  version    INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, bin_id, goods_id)
);
```

**（4）幂等与审计**

```sql
CREATE TABLE idempotency_key (
  tenant_id  TEXT NOT NULL,
  key        TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response   TEXT,
  status     TEXT NOT NULL,   -- processing/done/failed
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, key)
);

CREATE TABLE audit_log (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  actor_id   TEXT,
  action     TEXT NOT NULL,
  resource   TEXT NOT NULL,
  resource_id TEXT,
  before     TEXT,
  after      TEXT,
  ip         TEXT,
  created_at TEXT NOT NULL
);
```

**（5）Outbox（异步可靠性）**

```sql
CREATE TABLE outbox (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  topic      TEXT NOT NULL,
  payload    TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
```

#### 10.5.3 初始数据迁移规则

1. `openid` → `tenant_id`（保持值不变，降低兼容成本）；
2. `id` → ULID，同时保留 `legacy_id` 列用于对账；
3. 金额 `Float` → `INTEGER` 分（乘以 100 后四舍五入）；
4. 时间：`Asia/Shanghai` 本地时间 → UTC ISO8601；
5. `is_delete=True` → `deleted_at = update_time`；
6. 库存余额：以当前 `stockbin` 数值作为**期初余额**写入 `stock_ledger`（`event_type='OPENING'`），后续差异才能通过台账追溯；
7. `JSONField` 保留原文 TEXT，避免结构丢失。

### 10.6 API 设计规范

#### 10.6.1 路径兼容策略

为降低前端改造成本，**第一阶段保持现有路径不变**：

```
GET  /asn/list/?page=1&max_page=30
POST /asn/preload/:pk/
PUT  /dn/picked/
GET  /stock/bin/
POST /uploadfile/goodslistfile/
```

Hono 路由示例（尾斜杠兼容）：

```typescript
import { Hono } from 'hono'

const app = new Hono()

app.use('*', requestId())
app.use('*', authMiddleware())
app.use('*', tenantMiddleware())
app.use('*', rateLimitMiddleware())

app.route('/asn', asnRoutes)
app.route('/dn', dnRoutes)
app.route('/stock', stockRoutes)
app.route('/goods', goodsRoutes)
app.route('/uploadfile', uploadRoutes)

export default app
```

> 若未来要版本化，可增加 `/v1/` 前缀，旧路径作为别名保留一个周期。

#### 10.6.2 认证与租户

```typescript
// Authorization: Bearer <access_token>
// 过渡期兼容：token: <openid>

type Claims = {
  sub: string        // user id
  tid: string        // tenant id
  role: string
  exp: number
  jti: string
}
```

- Access Token：2 小时，EdDSA/HS256 签名；
- Refresh Token：30 天，一次性轮换，存入 D1/KV；
- 吊销：`jti` 黑名单存 KV（带 TTL），登出/改密时写入；
- 租户：**只信令牌中的 `tid`**，绝不从请求参数/请求头取租户；
- 兼容：迁移期允许 `token` 头映射到 `tenant_id`，但仅限只读接口，写接口必须用 JWT。

#### 10.6.3 响应契约

保持与现有前端一致：

```json
{
  "count": 128,
  "next": "/asn/list/?page=2&max_page=30",
  "previous": null,
  "results": [ ... ]
}
```

错误：

```json
{ "detail": "Goods Does Not Exists" }
```

- HTTP 状态码语义化：400 参数、401 未认证、403 越权、404 不存在、409 冲突/幂等冲突、422 业务校验、429 限流；
- 所有错误带 `request_id`，便于日志关联。

#### 10.6.4 分页、过滤、排序

| 能力 | 参数 | 实现 |
|---|---|---|
| 分页 | `page`、`max_page`（≤1000） | `LIMIT/OFFSET`，深分页改用游标 |
| 过滤 | `field=value`、`field__icontains`、`field__in`、`field__gte/lte` | 白名单映射到 SQL，禁止拼接列名 |
| 排序 | `ordering=id,-create_time` | 白名单字段 |
| 搜索 | `q=` | 多列 `LIKE`（小写归一） |

```typescript
const FILTERS: Record<string, string> = {
  goods_code: 'goods_code = ?',
  goods_code__icontains: 'LOWER(goods_code) LIKE ?',
  create_time__gte: 'create_time >= ?',
}
```

#### 10.6.5 幂等

- 写接口要求 `Idempotency-Key` 头（前端为每次用户动作生成 UUID）；
- 中间件在 `idempotency_key` 表中抢占记录：
  - 已存在且 `status=done` → 直接返回缓存的响应；
  - 已存在且 `status=processing` → 返回 409；
  - 不存在 → 插入 `processing`，执行后更新为 `done`；
- 库存类接口**强制要求**幂等键。

### 10.7 核心业务在边缘的实现

#### 10.7.1 库存过账：Durable Object 串行化

**为什么需要 DO**：D1 单库只有一个写者，但多个 Worker 实例仍可能并发读到旧值后写回（丢失更新）。用一个「每租户一个」的 DO 将写操作串行化，是最小改造方案。

```typescript
export class TenantWriter implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async postStock(cmd: PostStockCommand): Promise<PostStockResult> {
    // 1. 幂等检查（DO 存储）
    const seen = await this.state.storage.get(`idem:${cmd.idempotencyKey}`)
    if (seen) return seen as PostStockResult

    // 2. 读取余额（D1 或 DO SQLite）
    // 3. 校验：不允许负库存、不允许跨租户
    // 4. 写台账 + 更新余额（同一事务）
    // 5. 写 outbox（供 D1 异步投影）
    // 6. 记录幂等结果
    const result = { ok: true, balance: 0 }
    await this.state.storage.put(`idem:${cmd.idempotencyKey}`, result)
    return result
  }
}
```

**分片策略**：

| 方案 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| 每租户 1 个 DO | 实现简单、强一致 | 大租户成热点 | 中小租户为主 |
| 每租户+仓库 1 个 DO | 分散热点 | 跨仓调拨需协调 | 多仓大客户 |
| 每租户+商品 1 个 DO | 最高并发 | 单据级事务复杂 | 超高并发 |

建议从「每租户 1 个」开始，监控 DO 请求速率与持续时间后再分片。

#### 10.7.2 状态机集中实现

把 ASN/DN 的状态迁移收敛为一张表 + 一个函数：

```typescript
const ASN_TRANSITIONS = {
  PRELOAD:  { from: ['DRAFT'],            to: 'PRELOADED' },
  PRESORT:  { from: ['PRELOADED'],        to: 'PRESORTED' },
  SORT:     { from: ['PRESORTED'],        to: 'SORTED' },
  PUTAWAY:  { from: ['SORTED'],           to: 'PUTAWAY' },
} as const

function assertTransition(current: string, action: keyof typeof ASN_TRANSITIONS) {
  const rule = ASN_TRANSITIONS[action]
  if (!rule.from.includes(current)) {
    throw new BusinessError(`非法状态迁移: ${current} -> ${action}`)
  }
}
```

- 单头与明细状态**只通过该函数推进**，避免双写不一致；
- 每次迁移写 `audit_log` 与 `stock_ledger`（如有库存影响）。

#### 10.7.3 单号生成

- 在 DO 内使用「租户 + 日期 + 序列」的原子计数：

```typescript
const seqKey = `seq:${prefix}:${yyyymmdd}`
const seq = (await this.state.storage.get<number>(seqKey) ?? 0) + 1
await this.state.storage.put(seqKey, seq)
return `${prefix}${yyyymmdd}${String(seq).padStart(4, '0')}`
```

- 同时在 D1 建立 `UNIQUE(tenant_id, code)` 作为第二道防线。

#### 10.7.4 扫码条码

- 保留「条码 = 签名载荷」的思路，但：
  - 使用非对称签名（Ed25519）或 HMAC + 密钥轮换；
  - 载荷加入 `exp`（如 24h）与 `jti`，支持吊销；
  - 条码内容改为短 ID + 服务端查表，避免二维码过大；
- 扫码解析端点限流 + 防重放（`jti` 只能使用一次）。

#### 10.7.5 导入导出

| 场景 | 方案 |
|---|---|
| 小文件（< 5MB，< 5000 行） | 前端 SheetJS 解析 → JSON → Worker 批量写入 |
| 大文件 | 上传 R2 → Queue → Consumer 分批写入（每批 500 行） |
| 复杂 Excel（公式/多 Sheet） | 可选 Workflows 或 Container 处理 |
| 导出 CSV | Worker 流式生成 → R2 → 预签名下载 |
| 导出 Excel | 前端生成（SheetJS）或异步任务生成后放 R2 |

关键：**禁止在 Worker 中使用 pandas/openpyxl**；导入进度通过 `import_job` 表 + 轮询/SSE 通知。

### 10.8 前端迁移

| 项 | 现状 | 目标 |
|---|---|---|
| 主前端 | Quasar 1 + Vue 2（Django 托管） | Quasar 构建产物 → Pages |
| 移动端 | Quasar 2 + Vue 3（裸 axios） | 统一 SDK + 同一 API 域名 |
| 请求层 | 5 个 axios 实例 / 裸 axios | 1 个 SDK（fetch/axios + 拦截器） |
| 令牌 | LocalStorage.openid | 内存 + HttpOnly Refresh Cookie（推荐） |
| 配置 | `baseurl.txt` 同步 XHR | 构建时环境变量 + 运行时 `/config.json` |
| 错误处理 | 分散 | SDK 统一 + 错误码表 |
| 上传 | 直传后端 | R2 预签名直传 + 回调 |

**分阶段建议**：

1. 先让两套前端都指向新的 Workers 域名（DNS/CNAME），验证兼容性；
2. 抽出 `sdk/` 包，先替换 `app/`（页面少、风险低）；
3. 再替换 `templates/`，同时升级到 Quasar 2 + Vue 3（可与迁移解耦，单独立项）；
4. 静态资源迁到 Pages 后，开启 Brotli、HTTP/3、缓存规则。

### 10.9 异步与定时

| 任务 | 触发 | 实现 |
|---|---|---|
| 草稿清理 | Cron 每日 | 替代 `asn/views.py` 的读时删除 |
| 盘点任务生成 | Cron 每日 | 生成 `cyclecountday` |
| 日报/仪表盘聚合 | Cron 每小时 | 写入 KV / D1 汇总表 |
| 导入任务 | Queue | 分批写入 + 失败重试 + 死信 |
| CSV 导出 | Queue | 生成文件放 R2 |
| 通知（邮件/Webhook） | Queue | outbox 模式 |
| 跨系统同步（ERP） | Queue/Workflows | 幂等 + 重试 |

### 10.10 文件与媒体（R2）

```
桶结构：
  wms-media/
    {tenant_id}/avatar/{user_id}.webp
    {tenant_id}/import/{yyyy}/{mm}/{uuid}.xlsx
    {tenant_id}/export/{yyyy}/{mm}/{uuid}.csv
```

- 上传：Worker 签发预签名 URL（限大小/类型/前缀）；
- 下载：短期签名 URL，禁止公开桶；
- 生命周期：导出文件 7 天自动删除；
- 病毒扫描：可选外部服务或 Container。

### 10.11 安全与合规

| 层 | 措施 |
|---|---|
| 边缘 | WAF 托管规则 + 自定义规则（拦截异常 UA/路径/扫描器） |
| 限流 | Rate Limiting：`/login`、`/register`、`/uploadfile`、`/scanner/query` 严格阈值 |
| 人机校验 | 注册/登录/找回密码接入 Turnstile |
| 管理后台 | Cloudflare Access（邮箱/SSO + MFA）保护 `/admin` 类路径 |
| 密钥 | `wrangler secret` / Secrets Store，禁止入库 |
| 传输 | 强制 HTTPS、HSTS、TLS 1.2+（建议 1.3） |
| 浏览器 | CSP、X-Content-Type-Options、Referrer-Policy、Permissions-Policy |
| 数据 | 租户隔离在 SQL 层强制 `tenant_id`，仓储层统一注入 |
| 审计 | `audit_log` + Logpush 长期归档 |
| 合规 | 数据驻留（如需要可用 Jurisdiction/区域限制）；PII 最小化 |

**关键原则**：

1. 任何 SQL 必须经过仓储层，仓储层自动附加 `tenant_id`；
2. 禁止在日志中输出令牌、密码、完整请求体；
3. 导出文件使用短期签名 URL，不提供公开链接；
4. 生产环境关闭 OpenAPI UI，或置于 Access 之后。

### 10.12 可观测性

| 能力 | 工具 | 内容 |
|---|---|---|
| 结构化日志 | Workers Logpush → R2 | `request_id`、`tenant_id`、`user_id`、`route`、`status`、`latency` |
| 实时排查 | Tail Workers | 采样错误请求，输出堆栈 |
| 业务指标 | Analytics Engine | 单据量、库存变更次数、导入行数、失败率 |
| 告警 | 外部 APM/Webhook | 5xx 率、P95、DO 错误、Queue 积压 |
| 追踪 | OpenTelemetry 导出 | 可选，按需接入 |

**SLO 建议**：

| 指标 | 目标 |
|---|---|
| 可用性 | 99.9% |
| 读接口 P95 | < 300ms |
| 写接口 P95 | < 800ms |
| 错误率 | < 0.1% |
| Queue 积压 | < 1000 条且 < 5 分钟 |

### 10.13 数据迁移步骤与对账

#### 10.13.1 总体流程

```
步骤 0：盘点与冻结
  - 确认表清单（33 张业务表）
  - 冻结 schema 变更

步骤 1：全量导出
  - 从 SQLite 导出 CSV（每表一个文件）
  - 记录行数、主键范围、校验和

步骤 2：转换
  - openid → tenant_id
  - id → ULID（保留 legacy_id）
  - Float 金额 → 分
  - 本地时间 → UTC
  - is_delete → deleted_at

步骤 3：加载
  - wrangler d1 execute --file=schema.sql
  - wrangler d1 import（或分批 execute）

步骤 4：期初台账
  - 以 stockbin 当前值为 OPENING 事件写入 stock_ledger
  - 重算 stock_balance / bin_balance 并与原值对比

步骤 5：对账
  - 行数对账、金额对账、库存对账、抽样单据对账

步骤 6：影子读
  - 读请求双发（旧 Django + 新 Workers），比对响应

步骤 7：切读 → 切写 → 下线
```

#### 10.13.2 对账口径

| 维度 | 方法 | 通过标准 |
|---|---|---|
| 表行数 | `COUNT(*)` 对比 | 完全一致（除清理的草稿） |
| 金额 | 按租户汇总 `SUM(total_cost)` | 差异 = 0（分为单位） |
| 库存 | `SUM(bin_balance.qty)` vs `SUM(stocklist.goods_qty)` | 差异 = 0 |
| 单据 | 随机 100 单比对明细行数与数量 | 100% 一致 |
| 时间 | 抽样比对 `create_time` 时区 | 偏差 = 0 |

#### 10.13.3 迁移脚本清单

| 脚本 | 作用 |
|---|---|
| `export_sqlite.py` | 按表导出 CSV + 元数据 |
| `transform.ts` | 字段映射/类型转换/ULID 生成 |
| `schema.sql` | D1 建表与索引 |
| `load.sh` | 分批导入 + 断点续传 |
| `reconcile.py` | 对账报告 |
| `opening_ledger.ts` | 生成期初台账 |

> 迁移脚本建议放在独立仓库 `greaterwms-migration/`，不污染主仓库。

### 10.14 工作分解（WBS）与工期

| 阶段 | 任务 | 人日 | 角色 |
|---|---|---|---|
| 0 | 账号/域名/环境/wrangler/CI-CD | 5 | 后端/运维 |
| 0 | Pages 部署 + DNS 预演 | 3 | 前端/运维 |
| 1 | 认证/租户/RBAC | 6 | 后端 |
| 1 | 主数据 CRUD（20+ 资源） | 12 | 后端 |
| 1 | OpenAPI + 错误码 | 4 | 后端 |
| 1 | 前端 SDK 接入（app） | 5 | 前端 |
| 2 | 库存模型/台账/DO 写协调 | 15 | 后端（核心） |
| 2 | ASN 全流程 | 12 | 后端 |
| 2 | DN 全流程（释放/拣货/发货/POD） | 15 | 后端 |
| 2 | 盘点 | 8 | 后端 |
| 2 | 扫码（签发/解析/防重放） | 6 | 后端 |
| 2 | 导入导出 | 10 | 后端/前端 |
| 2 | 仪表盘 | 4 | 后端 |
| 2 | 前端适配（templates） | 8 | 前端 |
| 3 | 自动化测试（API + 并发） | 15 | QA/后端 |
| 3 | 安全加固与渗透测试 | 5 | 安全 |
| 3 | 数据迁移与对账 | 8 | 后端/数据 |
| 3 | 灰度/切流/回滚演练 | 5 | 运维 |
| — | **合计** | **约 146 人日** | — |

**排期建议**：3 人并行，约 10-12 周；若仅 2 人，约 14-16 周。

**依赖关系**：

```
阶段0 → 阶段1（认证/主数据）
              ↓
         阶段2（库存 → ASN/DN → 盘点/扫码）
              ↓
         阶段3（测试 → 迁移 → 切流）
```

> 库存是前置依赖：ASN/DN 的写入都必须调用同一套 `StockService`。

### 10.15 迁移风险登记册

| ID | 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|---|
| M-01 | D1 单写瓶颈 | 中 | 高 | DO 串行化 + 分批提交 + 监控写延迟 |
| M-02 | DO 热点 | 中 | 中 | 按仓库/商品分片；限流 |
| M-03 | Worker CPU 超限（导入/报表） | 高 | 中 | 前端解析 + Queue 分批 + 限制行数 |
| M-04 | SQL 语义差异 | 中 | 高 | 建 SQL 兼容层 + 回归测试 |
| M-05 | 无事务导致迁移脏数据 | 中 | 高 | 幂等 + 对账 + 可重跑 |
| M-06 | 时间/时区/金额误差 | 高 | 中 | 统一 UTC + 整数分 + 对账 |
| M-07 | 前端兼容性 | 中 | 中 | 保持 API 契约 + 影子读 |
| M-08 | 扫码条码失效 | 中 | 中 | 保留旧解析器一个周期 |
| M-09 | 回滚不彻底 | 低 | 高 | 双写/只读窗口 + 回滚演练 |
| M-10 | 成本超预期 | 中 | 中 | 预算告警 + 采样日志 |

### 10.16 成本估算框架

> 以下为结构，不给出具体金额（价格随套餐/区域变化，需以官网为准）。

| 项目 | 计费维度 | 估算方法 |
|---|---|---|
| Workers | 请求数 + CPU 时间 | 月请求量 × 单价（含免费额度） |
| D1 | 存储 + 行读 + 行写 | 表体积 + 查询次数 × 扫描行数 |
| Durable Objects | 请求数 + 持续时间 + 存储 | 写操作次数 × 单价 |
| R2 | 存储 + Class A/B 操作 | 文件体积 + 上传/下载次数（无出流量费） |
| Queues | 操作数 | 消息条数 × 3（写/读/删） |
| Pages | 构建 + 带宽 | 通常免费额度内 |
| Access | 座位数 | 管理员数量 |
| Logpush | 日志量 | 采样后体积 |

**降本要点**：

1. 日志采样（错误全采、成功 1%）；
2. 仪表盘聚合结果缓存（KV/Cache）；
3. 导出文件生命周期 7 天；
4. 批量写合并（D1 batch）。

### 10.17 验收标准与回滚方案

#### 10.17.1 功能验收

| 模块 | 验收点 |
|---|---|
| 登录/注册 | 登录、登出、刷新、吊销、角色 |
| 主数据 | 20+ 资源 CRUD、导入、导出、分页、过滤 |
| ASN | 新建→预加载→预分拣→分拣→上架，含短缺/多货/破损 |
| DN | 新建→释放→拣货→发货→POD→欠货 |
| 库存 | 移库、库位转换、盘点调整、余额一致 |
| 扫码 | 签发、解析、过期、重放拦截 |
| 报表 | 收货/发货趋势与旧系统一致 |
| 权限 | 越权返回 403，跨租户不可见 |

#### 10.17.2 非功能验收

| 项 | 标准 |
|---|---|
| 性能 | 读 P95 < 300ms，写 P95 < 800ms |
| 并发 | 100 并发移库无超扣 |
| 数据 | 对账差异 = 0 |
| 安全 | 高危漏洞 = 0，渗透测试通过 |
| 可用性 | 灰度期 7 天无 P1 故障 |

#### 10.17.3 回滚方案

```
触发条件：
  - 5xx > 1% 持续 10 分钟
  - 库存对账差异 > 0
  - 关键流程不可用 > 15 分钟

回滚步骤：
  1. 边缘路由切回旧 Django（DNS/Worker 开关）
  2. 停止新系统写入（置只读）
  3. 导出新系统增量数据（按 update_time 水位）
  4. 回灌旧库（幂等脚本）
  5. 校验后恢复旧系统写入
  6. 保留新系统只读环境用于排查

前置条件：
  - 旧系统至少保留 30 天可写
  - 回滚脚本每阶段演练一次
```

### 10.18 分阶段路线图

| 阶段 | 时间 | 目标 | 交付物 |
|---|---|---|---|
| 0 | 第 1 周 | 基础设施就绪 | Pages 预览站、Workers 脚手架、CI/CD |
| 1 | 第 2-4 周 | 身份+主数据 | 登录/租户/RBAC、20+ CRUD、SDK |
| 2 | 第 5-10 周 | 核心作业 | 库存/ASN/DN/盘点/扫码/导入导出 |
| 3 | 第 11-14 周 | 上线 | 测试报告、对账报告、灰度/切流/回滚演练 |

**里程碑判据**：

- 阶段 1 结束：前端可完成登录 + 商品/供应商/库位维护；
- 阶段 2 结束：完整跑通一张 ASN 与一张 DN；
- 阶段 3 结束：对账为 0，灰度 7 天无 P1。

### 10.19 方案结论

1. **不建议直接全量重写**：应先止血（第 9 章阶段一），否则会把旧缺陷带进新系统。
2. **推荐「C → A」路径**：先用 Cloudflare 前置（WAF/CDN/TLS）获得即时收益，同时启动边缘重写的阶段 0/1。
3. **数据层以 D1 + DO 写协调为核心**：保留 SQL 能力，又解决并发一致性；不推荐把库存完全放进 DO 存储（运维与查询复杂度高）。
4. **API 契约保持不变**：路径、分页、错误结构均兼容，前端可渐进式替换。
5. **迁移成败取决于对账与回滚**：必须把「期初台账 + 对账脚本 + 回滚演练」作为硬性交付物。

---

## 附录

### 附录 A：数据表清单（33 张）

| # | 表名 | 所属应用 | 模型 | 说明 |
|---|---|---|---|---|
| 1 | `asnlist` | `asn` | `AsnListModel` | 入库单头 |
| 2 | `asndetail` | `asn` | `AsnDetailModel` | 入库明细 |
| 3 | `dnlist` | `dn` | `DnListModel` | 出库单头 |
| 4 | `dndetail` | `dn` | `DnDetailModel` | 出库明细 |
| 5 | `pickinglist` | `dn` | `PickingListModel` | 拣货任务 |
| 6 | `stocklist` | `stock` | `StockListModel` | 商品库存总账（15 个维度） |
| 7 | `stockbin` | `stock` | `StockBinModel` | 库位库存 |
| 8 | `qtyrecorder` | `cyclecount` | `QTYRecorder` | 库存变动流水 |
| 9 | `cyclecountday` | `cyclecount` | `CyclecountModeDayModel` | 日盘点任务 |
| 10 | `manualcyclecount` | `cyclecount` | `ManualCyclecountModeModel` | 手工盘点 |
| 11 | `goods` | `goods` | `ListModel` | 商品主数据 |
| 12 | `goodsunit` | `goodsunit` | `ListModel` | 单位字典 |
| 13 | `goodsclass` | `goodsclass` | `ListModel` | 类别字典 |
| 14 | `goodsbrand` | `goodsbrand` | `ListModel` | 品牌字典 |
| 15 | `goodscolor` | `goodscolor` | `ListModel` | 颜色字典 |
| 16 | `goodsshape` | `goodsshape` | `ListModel` | 形状字典 |
| 17 | `goodsspecs` | `goodsspecs` | `ListModel` | 规格字典 |
| 18 | `goodsorigin` | `goodsorigin` | `ListModel` | 产地字典 |
| 19 | `supplier` | `supplier` | `ListModel` | 供应商 |
| 20 | `customer` | `customer` | `ListModel` | 客户 |
| 21 | `company` | `company` | `ListModel` | 公司主体 |
| 22 | `warehouse` | `warehouse` | `ListModel` | 仓库 |
| 23 | `binset` | `binset` | `ListModel` | 库位 |
| 24 | `binsize` | `binsize` | `ListModel` | 库位尺寸 |
| 25 | `binproperty` | `binproperty` | `ListModel` | 库位属性 |
| 26 | `staff` | `staff` | `ListModel` | 员工 |
| 27 | `stafftype` | `staff` | `TypeListModel` | 员工类型 |
| 28 | `driver` | `driver` | `ListModel` | 司机 |
| 29 | `dispatchlist` | `driver` | `DispatchListModel` | 派车单 |
| 30 | `capital` | `capital` | `ListModel` | 固定资产 |
| 31 | `transportationfee` | `payment` | `TransportationFeeListModel` | 运输费用 |
| 32 | `scanner` | `scanner` | `ListModel` | 扫码指令 |
| 33 | `throttle` | `throttle` | `ListModel` | 限流计数 |

另：`user_profile`（`userprofile.Users`）为租户/用户主表；Django 内置表包括 `auth_user`、`auth_group`、`auth_permission`、`django_content_type`、`django_session`、`django_admin_log`、`django_migrations`。

> 若将 `user_profile` 计入业务表，则业务表总数为 34 张。

### 附录 B：API 端点清单

| 应用 | 端点数 | 端点（方法 + 路径） |
|---|---|---|
| `asn` | 13 | GET/POST `/asn/list/`；GET/PUT/PATCH/DELETE `/asn/list/<pk>/`；GET/POST/PUT `/asn/detail/`；GET `/asn/detail/<pk>/`；GET `/asn/viewprint/<pk>/`；POST `/asn/preload/<pk>/`；POST `/asn/presort/<pk>/`；PUT `/asn/sorted/`；POST `/asn/sorted/<pk>/`；PUT `/asn/movetobin/`；POST `/asn/movetobin/<pk>/`；GET `/asn/filelist/`；GET `/asn/filedetail/` |
| `dn` | 16 | GET/POST `/dn/list/`；GET/PUT/PATCH/DELETE `/dn/list/<pk>/`；GET/POST/PUT `/dn/detail/`；GET/DELETE `/dn/detail/<pk>/`；GET `/dn/viewprint/<pk>/`；POST `/dn/neworder/<pk>/`；POST `/dn/orderrelease/`；PUT `/dn/orderrelease/<pk>/`；GET `/dn/pickinglistfilter/`；GET `/dn/pickinglist/<pk>/`；PUT `/dn/picked/`；POST/PUT `/dn/picked/<pk>/`；POST `/dn/dispatch/<pk>/`；POST `/dn/pod/<pk>/`；GET `/dn/filelist/`；GET `/dn/filedetail/` |
| `stock` | 6 | GET `/stock/list/`；GET `/stock/list/<pk>/`；GET/PUT `/stock/bin/`；GET/POST `/stock/bin/<pk>/`；GET `/stock/filelist/`；GET `/stock/filebinlist/` |
| `goods` | 3 | GET/POST `/goods/`；GET/PUT/PATCH/DELETE `/goods/<pk>/`；GET `/goods/goodstag/<bar_code>/` |
| `goodsunit` 等 7 字典 | 14 | 每个应用：GET/POST `/<app>/`；GET/PUT/PATCH/DELETE `/<app>/<pk>/` |
| `warehouse` | 4 | GET/POST `/warehouse/`；GET/PUT/PATCH/DELETE `/warehouse/<pk>/`；GET `/warehouse/multiple/`；GET `/warehouse/multiple/<pk>/` |
| `binset` | 5 | GET/POST `/binset/`；GET/PUT/PATCH/DELETE `/binset/<pk>/`；GET `/binset/file/`；GET `/binset/scannerbintag/<bar_code>/` |
| `binsize` | 3 | GET/POST `/binsize/`；GET/PUT/PATCH/DELETE `/binsize/<pk>/`；GET `/binsize/file/` |
| `binproperty` | 1 | GET `/binproperty/` |
| `supplier` | 3 | GET/POST `/supplier/`；GET/PUT/PATCH/DELETE `/supplier/<pk>/`；GET `/supplier/file/` |
| `customer` | 3 | GET/POST `/customer/`；GET/PUT/PATCH/DELETE `/customer/<pk>/`；GET `/customer/file/` |
| `company` | 2 | GET/POST `/company/`；GET/PUT/PATCH/DELETE `/company/<pk>/` |
| `staff` | 4 | GET/POST `/staff/`；GET `/staff/type/`；GET `/staff/file/`；GET/PUT/PATCH/DELETE `/staff/<pk>/` |
| `driver` | 6 | GET/POST `/driver/`；GET/PUT/PATCH/DELETE `/driver/<pk>/`；GET `/driver/file/`；GET `/driver/dispatchlist/`；GET `/driver/dispatchlist/<pk>/` |
| `capital` | 3 | GET/POST `/capital/`；GET/PUT/PATCH/DELETE `/capital/<pk>/`；GET `/capital/file/` |
| `payment` | 3 | GET/POST `/payment/freight/`；GET/PUT/PATCH/DELETE `/payment/freight/<pk>/`；GET `/payment/freightfile/` |
| `cyclecount` | 9 | GET/POST/PUT `/cyclecount/`；GET `/cyclecount/cyclecountrecorder/`；GET `/cyclecount/qtyrecorviewset/`；GET `/cyclecount/getgoodscyclecount/`；GET/POST `/cyclecount/manualcyclecount/`；GET `/cyclecount/manualcyclecountrecorder/`；GET `/cyclecount/filecyclecountday/`；GET `/cyclecount/filecyclecountall/`；GET `/cyclecount/manualfilecyclecount/` |
| `scanner` | 4 | GET/POST `/scanner/`；POST `/scanner/query/`；GET `/scanner/list/<bar_code>/`；GET `/scanner/sanerpicking/` |
| `dashboard` | 2 | GET `/dashboard/receipts/`；GET `/dashboard/sales/` |
| `uploadfile` | 10 | POST `/uploadfile/goodslistfile/`、`supplierfile/`、`customerfile/`、`capitalfile/`、`freightfile/`；`goodslistfileadd/`、`supplierfileadd/`、`customerfileadd/`、`capitalfileadd/`、`freightfileadd/` |
| `userlogin` | 1 | POST `/login/` |
| `userregister` | 1 | POST `/register/` |
| 系统 | 6 | `/admin/`；`/myip/`；`/api/`；`/api/debug/`；`/api/docs/`；`/api-auth/` |

> 合计约 120 个路径-方法组合。路径均相对于站点根。

### 附录 C：关键文件职责索引

| 文件 | 职责 | 阅读价值 |
|---|---|---|
| `greaterwms/settings.py` | 全部配置 | 安全与行为的根源 |
| `greaterwms/urls.py` | 根路由 + SPA + 文档 | 理解访问入口 |
| `greaterwms/asgi.py` | HTTP/WS 分发 | 实时能力入口 |
| `greaterwms/views.py` | 静态文件手写流 | 性能与安全问题 |
| `utils/auth.py` | 认证 | 令牌机制核心 |
| `utils/permission.py` | 权限（恒真） | 授权缺失证据 |
| `utils/throttle.py` | 限流 | 可绕过与写库问题 |
| `utils/datasolve.py` | 校验/编号/运费 | 业务规则集中地 |
| `utils/jwt.py` | 条码签名 | 硬编码密钥 |
| `utils/page.py` | 分页 | 接口契约 |
| `asn/views.py` | 入库全流程 | 状态机与跨表写入 |
| `dn/views.py` | 出库全流程 | 最复杂的业务逻辑 |
| `stock/views.py` | 库存/移库 | 库存维度转换 |
| `cyclecount/views.py` | 盘点 | 差异调整 |
| `scanner/views.py` | 扫码 | 条码指令 |
| `uploadfile/views.py` | 导入 | 跨租户删除风险 |
| `userregister/views.py` | 注册 + 演示数据 | 初始化逻辑 |
| `templates/src/boot/axios_request.js` | 前端请求层 | 令牌与错误处理 |
| `templates/src/router/routes.js` | 路由 | 功能地图 |
| `app/src/router/routes.js` | 移动端路由 | 移动能力边界 |
| `Dockerfile` / `docker-compose.yml` | 构建与编排 | 部署缺陷 |
| `nginx.conf` | 反代与 TLS | 生产接入 |
| `.github/workflows/ci.yml` | CI | 质量门禁 |
| `.github/workflows/security.yml` | 安全扫描 | 供应链与漏洞 |

### 附录 D：统计口径与核对方法

| 指标 | 口径 | 核对命令/方式 |
|---|---|---|
| 应用数 | `INSTALLED_APPS` 中的业务应用 | 阅读 `settings.py` |
| Python 行数 | `*.py` 行数合计（排除 `000newPlatform`、`Docs`） | `git ls-files '*.py'` + 统计 |
| 数据表数 | `models.py` 中 `db_table` 声明数 | `Select-String -Pattern "db_table"` |
| 端点 | 各 `urls.py` 的 `path`/`re_path` 展开 | 阅读全部 `urls.py` |
| 页面数 | `src/pages/**/*.vue` | 文件计数 |
| 迁移文件 | `migrations/*.py` 除 `__init__.py` | 目录检查 |
| 测试 | `tests.py` 中的 `TestCase` 子类 | 全仓库检索 |
| 事务 | `transaction.atomic` | 全仓库检索（0 命中） |
| 版本 | `settings.py`、两个 `package.json`、`git tag` | 交叉比对 |

### 附录 E：未确认事项

| # | 事项 | 说明 |
|---|---|---|
| 1 | MySQL/PostgreSQL 实际支持 | README 声明支持，但 `requirements.txt` 无驱动、`settings.py` 无配置；可能存在于定制分支 |
| 2 | CI 实际执行结果 | 本机未安装 Django，未实测 `makemigrations --check` 退出码 |
| 3 | 生产实际部署拓扑 | 仓库仅有示例 Nginx/Compose，无生产环境描述 |
| 4 | 定时任务 | 未找到 Celery/cron 配置；`cyclecount` 的自动生成机制未确认 |
| 5 | 消息通知 | 未找到邮件/短信/Webhook 实现 |
| 6 | 多仓/多组织 | 有 `warehouse` 主数据，但业务表未存 `warehouse` 字段，多仓隔离未实现 |
| 7 | 批次/效期/序列号 | 未找到相关字段 |
| 8 | 权限矩阵 | 前端可能有菜单级控制，后端无校验 |
| 9 | 数据备份策略 | 未找到脚本或文档 |
| 10 | 监控告警 | 未找到接入代码 |
| 11 | 压测数据 | 未找到基准报告 |
| 12 | 移动端发布 | Cordova/Capacitor 配置存在，但无签名/发布流水线 |
| 13 | 第三方对接 | README 提到 ERP/IoT，代码中未找到对接实现 |
| 14 | 3.0/Bomiot 迁移路径 | README 提及，具体兼容性未评估 |

### 附录 F：版本与仓库状态快照

| 项 | 值 |
|---|---|
| 分支 | `S2B2B2C` |
| 最新提交 | `8344f387 V2.1.54`（2026-10-13） |
| 最近标签 | `V2.1.54`、`V2.1.52`、`V2.1.49`、`V2.1.48`、`V2.1.47`、`V2.1.42`、`V2.1.38`、`V2.1.37` |
| 未跟踪目录 | `000newPlatform/`、`Docs/`（已按要求排除分析） |
| 代码声明版本 | 2.1.48 |
| 许可 | Apache-2.0 |

---

> 本报告仅基于仓库中可读的代码与配置，不包含对运行时行为、生产环境或商业授权的推断。标注「未找到相关依据」的条目需在具备运行环境后补充验证。
