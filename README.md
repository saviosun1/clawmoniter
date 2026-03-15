# Claw 负载监控系统

实时展示 AI Agent 运行状态的可视化仪表盘。

## 功能特性

- 📻 **收音机式仪表盘** - 直观的认知评分显示
- 📊 **实时状态监控** - CPU、内存、会话数等指标
- 📈 **负载走势图** - 支持多时间范围切换
- 📝 **任务队列** - 智能标签、Token 显示
- 💾 **历史数据** - SQLite 本地存储，Redis 云端同步

## 快速开始

### 1. 安装依赖

```bash
pip install redis psutil
```

### 2. 配置 Redis (可选)

如果使用 Upstash Redis，设置环境变量：

```bash
export REDIS_URL="https://your-upstash-url.upstash.io"
export REDIS_TOKEN="your-token-here"
```

或者使用本地 Redis：
```bash
docker run -d -p 6379:6379 redis:alpine
```

### 3. 启动监控服务

```bash
python3 cognitive_monitor.py
```

### 4. 打开仪表盘

直接在浏览器中打开 `cognitive-status.html`，或部署到静态服务器：

```bash
# 本地测试
python3 -m http.server 8000

# 然后访问
open http://localhost:8000/cognitive-status.html
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `cognitive-status.html` | 前端仪表盘页面 |
| `cognitive_monitor.py` | 后端数据采集服务 |
| `README.md` | 本文档 |

## 配置说明

### 前端配置

首次打开页面时，点击页面设置 Redis 连接信息，或直接在浏览器控制台执行：

```javascript
localStorage.setItem('redis_url', 'https://your-url.upstash.io');
localStorage.setItem('redis_token', 'your-token');
location.reload();
```

### 后端配置

编辑 `cognitive_monitor.py` 中的 `CONFIG` 字典：

```python
CONFIG = {
    "SESSIONS_DIR": "/root/.openclaw/agents/main/sessions",  # 会话目录
    "ACTIVE_THRESHOLD": 600,  # 活跃判定时间(秒)
    "REDIS_URL": "redis://localhost:6379",
    "UPDATE_INTERVAL": 15,  # 更新间隔(秒)
    "HISTORY_DB": "/var/lib/cognitive_monitor/history.db",
}
```

## 评分算法

```
最终评分 = 基础评分(50) + max(等待评分, Token评分) + 处理加成

等待评分: 基于最长等待消息时间
  - 0-10s: 20-30%
  - 10-30s: 30-55%
  - 30-60s: 55-80%
  - 60s+: 80-95%

Token评分: 基于处理中任务的Token量
  - 10k: ~10%
  - 50k: ~30%
  - 100k: ~50%
  - 200k+: 75-80%

处理加成: 每个处理中任务 +3% (最多+15%)
```

## 部署到 GitHub Pages

```bash
# 1. Fork 或克隆本仓库
git clone https://github.com/saviosun1/clawmoniter.git
cd clawmoniter

# 2. 提交代码
git add .
git commit -m "feat: 初始版本"
git push origin main

# 3. 开启 GitHub Pages
# 进入仓库 Settings -> Pages -> Source 选择 main 分支

# 4. 访问
# https://your-username.github.io/clawmoniter/cognitive-status.html
```

## 架构图

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   浏览器页面     │────▶│  Upstash Redis  │◀────│  Python 采集器   │
│ cognitive-status │     │   (云端数据)     │     │cognitive_monitor│
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                              ┌─────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  OpenClaw 会话   │
                    │  /sessions/*.jsonl│
                    └─────────────────┘
```

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| 页面显示 "加载中" | 检查 Redis 连接配置 |
| 数据不更新 | 确认 cognitive_monitor.py 正在运行 |
| 会话数为 0 | 检查 SESSIONS_DIR 路径是否正确 |
| CPU/内存显示为 0 | 安装 psutil: `pip install psutil` |

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-03-15 | 初始版本，基础监控功能 |

## 许可证

MIT
