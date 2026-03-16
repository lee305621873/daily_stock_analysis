---
name: daily-stock-analysis
description: A股/港股/美股智能分析系统，帮助分析股票、执行大盘复盘、配置 Agent 策略问股。当用户想要分析股票、进行市场复盘、启动 Web 界面、配置通知推送时使用。
---

# 股票智能分析系统

基于 AI 大模型的 A股/港股/美股自选股智能分析系统，每日自动分析并推送「决策仪表盘」。

## 项目结构

```
daily_stock_analysis/
├── main.py                 # 主入口程序
├── analyzer_service.py     # 股票分析服务（推荐使用）
├── server.py               # FastAPI 服务器入口
├── webui.py                # Web UI 入口
├── src/
│   ├── config.py           # 配置管理
│   ├── analyzer.py         # AI 分析器
│   ├── notification.py     # 通知服务
│   ├── search_service.py   # 新闻搜索
│   ├── scheduler.py        # 定时任务
│   ├── core/               # 核心模块 (pipeline, market_review)
│   ├── agent/              # Agent 策略系统
│   └── services/          # 业务服务
├── api/                    # FastAPI 后端
│   └── v1/endpoints/      # API 端点
├── apps/dsa-web/           # React 前端
├── bot/                    # 机器人平台 (Telegram/飞书/钉钉)
├── data_provider/          # 数据源 (AkShare/Tushare/YFinance)
└── strategies/            # 交易策略 YAML 文件
```

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
vim .env
```

### 3. 运行模式

```bash
# 方式一：直接运行分析（需要配置 STOCK_LIST 和 AI Key）
python main.py

# 方式二：启动 Web 界面（含 API 服务）
python main.py --webui
# 访问 http://127.0.0.1:8000

# 方式三：仅启动 API 服务（不自动执行分析）
python main.py --serve-only
# 访问 http://127.0.0.1:8000/docs 查看 API 文档

# 方式四：定时任务模式
python main.py --schedule
```

### 4. 快速测试命令

不配置 AI Key 也可测试基本功能：

```bash
# 测试 API 服务启动
python main.py --serve-only
# 然后访问 http://127.0.0.1:8000/docs

# 测试 dry-run 模式（仅获取数据，不 AI 分析）
STOCK_LIST="600519" RUN_IMMEDIATELY=false python main.py --dry-run

# 指定股票运行分析
python main.py --stocks 600519

# 跳过交易日检查强制运行
python main.py --force-run
```

### 5. 环境变量说明

项目支持多种配置方式（优先级从高到低）：

1. **命令行环境变量**：`STOCK_LIST="600519" python main.py`
2. **.env 文件**：项目根目录的 `.env` 文件
3. **.env.example**：配置模板，复制为 `.env` 后修改

常用环境变量：
```bash
STOCK_LIST         # 自选股列表，逗号分隔
RUN_IMMEDIATELY   # 启动时是否立即运行分析 (true/false)
GEMINI_API_KEY    # Gemini API Key
DEEPSEEK_API_KEY  # DeepSeek API Key
```

## 必需配置

### 1. 自选股列表

```env
STOCK_LIST=600519,300750,002594,hk00700,AAPL
```

| 市场 | 代码格式 | 示例 |
|------|---------|------|
| A股沪市 | 6位数字 | 600519 |
| A股深市 | 6位数字 | 000001, 300750 |
| 港股 | hk + 5位数字 | hk00700 |
| 美股 | 字母 | AAPL, TSLA |

### 2. AI 模型配置 (至少配置一个)

#### 方式一：简单配置（填一个 Key 即可）

```env
# 推荐：Gemini (免费额度)
GEMINI_API_KEY=your_gemini_key

# 或：DeepSeek (性价比高)
DEEPSEEK_API_KEY=your_deepseek_key

# 或：AIHubMix (聚合平台，一个 Key 用 GPT/Claude/Gemini/GLM/Qwen)
AIHUBMIX_KEY=your_aihubmix_key

# 或：Anthropic Claude
ANTHROPIC_API_KEY=your_anthropic_key
```

获取地址：
- Gemini: https://aistudio.google.com/app/apikey
- DeepSeek: https://platform.deepseek.com/
- AIHubMix: https://aihubmix.com/?aff=CfMq
- Claude: https://console.anthropic.com/

#### 方式二：多渠道配置（支持 fallback）

```env
# 启用多渠道
LLM_CHANNELS=deepseek,gemini

# 渠道1: DeepSeek
LLM_DEEPSEEK_API_KEY=sk-xxx
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_DEEPSEEK_MODELS=deepseek-chat

# 渠道2: Gemini
LLM_GEMINI_API_KEYS=key1,key2
LLM_GEMINI_MODELS=gemini-2.5-flash
```

#### 方式三：自定义第三方 API 代理

```env
LLM_CHANNELS=my_proxy
LLM_MY_PROXY_BASE_URL=https://your-proxy.example.com/v1
LLM_MY_PROXY_API_KEY=sk-xxx
LLM_MY_PROXY_MODELS=gpt-4o-mini,claude-3-5-sonnet
LLM_MY_PROXY_PROTOCOL=openai
```

#### 方式四：YAML 配置文件（高级）

```env
LITELLM_CONFIG=./litellm_config.yaml
```

参考 `litellm_config.example.yaml`

### 3. 新闻搜索 API (可选)

```env
# 至少配置一个，用于获取股票新闻
TAVILY_API_KEYS=your_tavily_key
# 或
BOCHA_API_KEYS=your_bocha_key
# 或
SERPAPI_API_KEYS=your_serpapi_key
```

获取地址：
- Tavily: https://tavily.com/
- Bocha: https://open.bocha.cn/
- SerpAPI: https://serpapi.com/

### 4. 通知渠道 (可选，至少一个)

| 渠道 | 环境变量 | 说明 |
|------|---------|------|
| 企业微信 | `WECHAT_WEBHOOK_URL` | 机器人 Webhook |
| 飞书 | `FEISHU_WEBHOOK_URL` | 机器人 Webhook |
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Bot + Chat ID |
| Discord | `DISCORD_WEBHOOK_URL` | Webhook |
| 邮件 | `EMAIL_SENDER` + `EMAIL_PASSWORD` | SMTP 授权码 |
| 钉钉 | `CUSTOM_WEBHOOK_URLS` | 自定义 Webhook |

## 命令行参数

```bash
python main.py                      # 正常运行
python main.py --debug              # 调试模式，输出详细日志
python main.py --dry-run            # 仅获取数据，不进行 AI 分析
python main.py --stocks 600519      # 指定分析特定股票
python main.py --no-notify          # 不发送推送通知
python main.py --single-notify      # 单股推送模式
python main.py --workers 5          # 并发线程数

# Web 相关
python main.py --webui              # 启动 Web 界面 + 执行分析
python main.py --webui-only         # 仅启动 Web 界面
python main.py --serve              # 启动 FastAPI 服务
python main.py --serve-only         # 仅启动 API 服务，不自动分析
python main.py --port 8080          # 指定端口 (默认 8000)
python main.py --host 0.0.0.0       # 指定监听地址

# 定时任务
python main.py --schedule            # 启用定时任务模式
python main.py --no-run-immediately  # 定时任务启动时不立即执行

# 其他
python main.py --market-review      # 仅运行大盘复盘
python main.py --no-market-review   # 跳过大盘复盘
python main.py --backtest           # 运行回测
python main.py --force-run          # 跳过交易日检查强制执行
```

## 常用操作 (代码调用)

### 分析单只股票

```python
from analyzer_service import analyze_stock

result = analyze_stock("600519")
if result:
    print(f"股票: {result.name} ({result.code})")
    print(f"情绪得分: {result.sentiment_score}")
    print(f"操作建议: {result.operation_advice}")
    print(f"趋势预测: {result.trend_prediction}")
```

### 分析多只股票

```python
from analyzer_service import analyze_stocks

results = analyze_stocks(["600519", "000001", "AAPL"])
for r in results:
    emoji = r.get_emoji()
    print(f"{emoji} {r.name}: {r.operation_advice}")
```

### 大盘复盘

```python
from analyzer_service import perform_market_review

report = perform_market_review()
print(report)
```

### 使用自定义配置

```python
from analyzer_service import analyze_stock
from src.config import Config

# 创建自定义配置
config = Config()
config.stock_list = ["600519", "300750"]
config.gemini_api_key = "your_key"

# 传入配置
result = analyze_stock("600519", config=config)
```

## API 接口

启动服务后访问 `http://127.0.0.1:8000/docs` 查看完整 API 文档。

### 常用端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/analysis/analyze` | 分析股票 |
| GET | `/api/v1/history` | 获取历史分析记录 |
| GET | `/api/v1/history/{id}` | 获取单条历史详情 |
| POST | `/api/v1/stocks/extract-from-image` | 从图片识别股票代码 |
| POST | `/api/v1/stocks/parse-import` | 解析导入的股票 |
| GET | `/api/v1/usage/summary` | LLM 使用量统计 |
| POST | `/api/v1/backtest/run` | 运行回测 |
| GET | `/api/v1/system_config` | 获取系统配置 |
| PUT | `/api/v1/system_config` | 更新系统配置 |

### 分析 API 示例

```bash
# 单股分析
curl -X POST "http://localhost:8000/api/v1/analysis/analyze" \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["600519"], "async_mode": false}'

# 批量分析 (异步)
curl -X POST "http://localhost:8000/api/v1/analysis/analyze" \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["600519", "300750"], "async_mode": true}'
```

## Web 界面功能

访问 `http://127.0.0.1:8000`

- **首页**：查看历史分析记录、手动触发分析
- **设置**：配置自选股、AI Key、通知渠道
- **智能导入**：从图片/文件/剪贴板导入股票
- **Agent 问股**：`/chat` 页面进行策略对话

### 认证设置 (可选)

```env
ADMIN_AUTH_ENABLED=true
```

首次访问时设置密码，保护敏感配置。

## Agent 策略问股

启用 Agent 模式：

```env
AGENT_MODE=true
AGENT_SKILLS=bull_trend,ma_golden_cross,volume_breakout,shrink_pullback
AGENT_MAX_STEPS=10
```

访问 `/chat` 页面进行对话。

### 11 种内置策略

| 策略 | 说明 |
|------|------|
| `bull_trend` | 多头趋势 (MA5>MA10>MA20) |
| `ma_golden_cross` | 均线金叉 |
| `volume_breakout` | 放量突破 |
| `shrink_pullback` | 缩量回踩 |
| `bottom_volume` | 底部放量 |
| `dragon_head` | 龙头策略 |
| `one_yang_three_yin` | 一阳夹三阴 |
| `box_oscillation` | 箱体震荡 |
| `chan_theory` | 缠论 |
| `wave_theory` | 波浪理论 |
| `emotion_cycle` | 情绪周期 |

## 数据源配置

```env
# 数据源优先级 (数字越小越高)
EFINANCE_PRIORITY=0    # 东财 (默认)
AKSHARE_PRIORITY=1    # AkShare
TUSHARE_PRIORITY=2    # Tushare Pro
YFINANCE_PRIORITY=4   # Yahoo Finance (美股)

# 实时行情优先级
REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance
```

## GitHub Actions 部署 (推荐)

1. Fork 仓库
2. Settings → Secrets and variables → Actions 添加配置
3. Actions → 每日股票分析 → Run workflow

```env
# 必需
STOCK_LIST=600519,300750

# 至少一个 AI Key
GEMINI_API_KEY=xxx

# 至少一个通知渠道
WECHAT_WEBHOOK_URL=xxx
```

## 验证

```bash
# Python 语法检查
python -m py_compile main.py

# 完整门禁
./scripts/ci_gate.sh
```

## 常见问题

详见 `docs/FAQ.md`

- Q: 分析失败怎么办？ → 检查 `.env` 配置和 API Key
- Q: 如何在非交易日运行？ → 使用 `--force-run` 参数
- Q: 推送不到怎么办？ → 检查 Webhook URL 是否正确
- Q: 美股分析异常？ → 确保配置了 YFINANCE_PRIORITY=0

## 已知问题/踩坑记录

### 1. Python 版本要求

项目要求 **Python 3.10+**，当前环境如果是 Python 3.9 可能会有兼容性问题。

### 2. json-repair 版本问题

`requirements.txt` 中 `json-repair>=0.55.1` 版本在 PyPI 不存在，最高可用版本为 `0.44.1`。

**解决方法**：修改 `requirements.txt`:
```
json-repair>=0.44.1
```

### 3. 依赖安装建议

建议使用 `--no-cache-dir` 参数分批安装，避免超时：
```bash
pip install efinance --no-cache-dir
pip install akshare --no-cache-dir
pip install litellm --no-cache-dir
pip install newspaper3k --no-cache-dir
```

### 4. SSL 警告

macOS 自带 LibreSSL 可能会有警告，不影响运行：
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+
```

### 5. pip 版本建议

当前环境 pip 版本较旧（21.2.4），建议升级：
```bash
pip install --upgrade pip
```

### 6. Node.js 版本要求 (Web 界面)

Web 前端构建需要 Node.js 16+，当前环境 v14.21.3 可能会导致构建失败。

**解决方法**：升级 Node.js：
```bash
# 使用 nvm 升级
nvm install 20
nvm use 20
```

或者手动构建前端：
```bash
cd apps/dsa-web
npm install
npm run build
```

## 更多文档

- 完整配置指南：`docs/full-guide.md`
- LLM 配置指南：`docs/LLM_CONFIG_GUIDE.md`
- 更新日志：`docs/CHANGELOG.md`
