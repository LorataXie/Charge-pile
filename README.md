# 智能充电站调度计费系统

基于 BUPT 充电站详细需求文档，采用 C/S 分层架构实现的充电桩调度计费系统。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.10+ / FastAPI |
| 数据库 | SQLite（开发）/ MySQL（生产） |
| ORM | SQLAlchemy 2.0 (async) |
| 前端 | Vue.js 3 CDN（无需构建） |
| CLI | Click |
| 认证 | JWT |

## 快速开始

### 1. 环境准备

```bash
# Python 3.10+ 必须已安装
python --version

# 克隆项目
git clone https://github.com/LorataXie/-.git
cd -

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境配置（使用默认配置即可运行）
cp .env.example .env
```

默认使用 SQLite，无需安装数据库。如需 MySQL，修改 `.env` 中的 `DATABASE_URL`。

### 3. 初始化测试数据（推荐）

```bash
python cli/seed.py
```

一键创建所有测试数据：
- 管理员：admin / admin123
- 25个客户：user1~user25 / user123
- 25辆车（京A1001~京A1025）
- 21条充电请求（13快充 + 8慢充，用于展示充电中、桩内排队、等候区排队）

如果只需要管理员账号：

```bash
python cli/main.py create-admin -u admin -p admin123
```

### 4. 启动后端

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

看到 `Uvicorn running on http://0.0.0.0:8000` 即启动成功。

### 5. 打开前端

浏览器直接打开 `frontend/index.html`，或者：

```bash
start frontend/index.html   # Windows
open frontend/index.html    # macOS
```

---

## 功能验证指南

以下按照需求文档逐项验证。

### 一、用户客户端功能（客户角色）

#### 1.1 注册与登录
- 打开前端 → 点击「注册」
- 输入用户名/密码 → 角色默认为"客户" → 注册
- 注册成功自动登录

#### 1.2 提交充电请求
- 「提交请求」Tab → 选择快充(F)或慢充(T) → 输入充电度数 → 提交
- 提交成功后显示排队号（如 F1、T2）
- 若等候区有空位，自动调度进入充电桩队列

#### 1.3 查看排队状态
- 「我的订单」Tab → 点订单行的「查看」按钮
- 显示：排队号码、前面等待车辆数、当前状态

#### 1.4 修改充电请求
- 「我的订单」Tab → 等候中的订单点「修改」
- **等候区改模式**：重新生成排队号，排到新模式队尾
- **等候区改电量**：排队号不变
- **充电区（排队中/充电中）**：不允许修改，提示"请先取消后重新提交"

#### 1.5 取消充电
- 「我的订单」Tab → 点「取消」
- 等候区、充电区均允许取消

#### 1.6 结束充电
- 「我的订单」Tab → 充电中的订单点「结束充电」

#### 1.7 查看充电详单
- 完成或中断的订单点「查看详单」，或切换到「查看详单」Tab 输入订单ID
- 显示字段：详单编号、生成时间、充电桩编号、充电电量、充电时长、启动时间、停止时间、充电费用（峰/平/谷）、服务费用、总费用

---

### 二、管理员客户端功能（管理员角色）

用 `admin / admin123` 登录。

#### 2.1 仿真控制（推进时间）
- 「仿真控制」Tab → 点「执行 1 Tick」推进虚拟时间
- 每次 Tick 默认 15 分钟，充电进度随之推进
- 支持快速 1h / 2h / 4h / 24h
- 充电完成的订单自动停止、生成详单、触发下一辆排队车充电

#### 2.2 监控总览
- 「监控总览」Tab → 看到 5 个充电桩实时状态（F1/F2/F3 快充, T1/T2 慢充）
- 点击任意充电桩 → 展开等候车辆详情：
  - 用户ID、电池容量、请求充电量、排队时长

#### 2.3 充电桩管理
- 「充电桩管理」Tab → 查看全部桩的累计数据
- 操作：启动/停止充电桩
- 状态：IDLE（空闲）、CHARGING（充电中）、BROKEN（故障）、STOPPED（已停止）

#### 2.4 等候区
- 「等候区」Tab → 查看所有在等候区排队的车辆

#### 2.5 故障管理
- 「故障管理」Tab → 输入充电桩ID → 选择调度策略 → 上报故障
  - **优先级调度**：故障桩车辆优先转入同类桩
  - **时间顺序调度**：合并故障桩+同类桩未充电车，按排队号重排序
- 故障恢复：输入桩ID → 点「故障恢复」→ 重新分配未充电订单

#### 2.6 报表
- 「报表」Tab → 选日报/周报/月报 → 生成报表 → 点「详情」查看
- 包含：充电桩编号、累计充电次数、累计充电时长、累计充电量、累计充电费用、累计服务费用、累计总费用

---

### 三、CLI 命令行工具

```bash
# 创建管理员
python cli/main.py create-admin -u admin -p admin123

# 登录
python cli/main.py login -u admin -p admin123

# 查看充电桩
python cli/main.py piles list

# 启动/停止充电桩
python cli/main.py piles start 2
python cli/main.py piles stop 2

# 仿真控制
python cli/main.py sim time       # 查看虚拟时间
python cli/main.py sim tick       # 推进一次
python cli/main.py sim fast 4     # 快进4小时

# 故障管理
python cli/main.py faults report 1 -s PRIORITY
python cli/main.py faults recover 1
python cli/main.py faults list

# 报表
python cli/main.py reports generate DAILY
python cli/main.py reports list

# 系统状态总览
python cli/main.py status
```

---

### 四、API 文档（Swagger）

启动后端后访问：`http://localhost:8000/docs`

所有接口可在线交互式测试。

---

## 推荐验证流程

```
1. 注册 admin（CLI）     → python cli/main.py create-admin -u admin -p admin123
2. 前端注册 client       → user1 / user123
3. Client 提交快充30度   → 自动调度到 F1，状态 CHARGING
4. Client 提交慢充15度   → 自动调度到 T1，状态 CHARGING
5. Admin 仿真 Tick x4    → 1小时，快充30度完成（30/30=1h）
6. Admin 仿真 Tick x2    → 再0.5h，慢充15度完成（15/10=1.5h）
7. Client 查看详单       → 订单ID=1，查看峰平谷分段费用
8. Admin 上报故障        → 桩ID=2，优先级调度
9. Admin 故障恢复        → 桩ID=2，重新分配
10. Admin 生成日报       → 查看各桩统计
```

## 项目架构

```
边界类 (frontend/) → 控制类 (controllers/) → 服务类 (services/)
                                            → 策略类 (strategy/)
                                            → 实体类 (models/)
                                            → DAO类 (dao/)
```

严格对应静态结构文档的分层设计，覆盖全部 9 个用例（UC_C01~C05, UC_A01~A04）和 7 种调度策略。
