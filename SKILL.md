---
name: "stock_analyzer"
description: "A股/港股/美股智能分析系统技能。当用户想要分析单个或多个股票、进行市场复盘、启动 Web/API 服务、配置 LLM/通知/数据源或使用 Agent 策略问股时调用。"
---

# 股票智能分析系统

本技能覆盖本仓库的分析函数调用、本地启动、常用配置和 Web/API 使用方式。优先复用现有入口：命令行走 `main.py`，代码调用优先走 `analyzer_service.py`。

## 项目结构

```text
daily_stock_analysis/
├── main.py                 # 主入口程序
├── analyzer_service.py     # 股票分析服务（代码调用推荐入口）
├── api/                    # FastAPI 后端
├── apps/dsa-web/           # React 前端
├── src/
│   ├── config.py           # 配置管理
│   ├── analyzer.py         # AI 分析器
│   ├── notification.py     # 通知服务
│   ├── search_service.py   # 新闻搜索
│   ├── scheduler.py        # 定时任务
│   ├── agent/              # Agent 策略系统
│   └── services/           # 业务服务
├── bot/                    # 机器人平台
├── data_provider/          # 数据源
└── strategies/             # 交易策略 YAML 文件
```

## 本地启动

如果目标是运行整个项目，而不是只调用分析函数，优先按下面顺序检查：

1. Python 使用 3.10+；仓库在 3.9 下会因为 `|` 联合类型和 Pydantic 解析报错。
2. Web 前端使用较新的 Node；本仓库实测 `Node 22.14.0` 可以完成 `apps/dsa-web` 构建。
3. `.env` 中至少要有一个可用 LLM 配置；当前仓库可用 `LLM_CHANNELS + LLM_<NAME>_*` 方式接第三方 OpenAI 兼容接口。

推荐启动顺序：

```bash
test -x .venv/bin/python || python3.10 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install -r requirements.txt

cd apps/dsa-web
nvm use 22.14.0
npm ci
npm run build
cd ../..
# lqsmark
WEBUI_AUTO_BUILD=false .venv/bin/python main.py --webui-only --host 127.0.0.1 --port 8000
WEBUI_AUTO_BUILD=false python3 main.py --webui-only --host 127.0.0.1 --port 8000
PORT=8001 ./scripts/run_webui_with_logs.sh
```

说明：

- `npm run build` 会把前端静态资源输出到仓库的 `static/` 目录。
- 若 `.venv/bin/python` 提示 `no such file or directory`，通常不是目录不存在，而是虚拟环境绑定的底层 Python 可执行文件已经失效（常见于基于临时路径创建的 venv）；这时应先重建 `.venv`，再安装依赖。
- 已经手动构建前端时，建议启动前设置 `WEBUI_AUTO_BUILD=false`，避免服务启动时再次执行 `npm install && npm run build`。
- Web 和 API 共用同一个服务入口；`--webui-only` 启动后，页面和接口都挂在 `http://127.0.0.1:8000`。
- 只开 API 时可用 `.venv/bin/python main.py --serve-only --host 127.0.0.1 --port 8000`。
- 正常执行一次完整分析时可直接运行 `.venv/bin/python main.py`。
- 定时任务模式可用 `.venv/bin/python main.py --schedule`。
- 配置检查可先跑 `python test_env.py --config`；健康检查可访问 `http://127.0.0.1:8000/api/health`。

常见问题：

- 前端若报 `Cannot find module 'vite'` 或 `vite/client`，通常是 `apps/dsa-web` 依赖未安装，或 Node 版本过低。
- 后端若报 `No module named 'dotenv'`、`fastapi`、`litellm`，说明依赖没有安装到当前 `.venv`。
- 后端若直接报 `zsh: no such file or directory: .venv/bin/python`，优先检查 `ls -l .venv/bin/python*`；若指向的解释器路径已不存在，删除并重建 `.venv`。
- Web 服务日志若显示前端静态资源未就绪，先重新执行 `cd apps/dsa-web && npm ci && npm run build`。
- macOS 出现 `NotOpenSSLWarning` 多数不阻断运行，可先继续验证主流程。

## 运行模式

```bash
python main.py                      # 正常运行
python main.py --debug              # 调试模式
python main.py --dry-run            # 仅获取数据，不进行 AI 分析
python main.py --stocks 600519      # 指定股票
python main.py --force-run          # 跳过交易日检查强制执行
python main.py --market-review      # 仅运行大盘复盘
python main.py --no-market-review   # 跳过大盘复盘
python main.py --schedule           # 定时任务模式
python main.py --no-run-immediately # 定时模式启动时不立即执行
python main.py --webui              # 启动 Web 界面 + 执行分析
python main.py --webui-only         # 仅启动 Web 界面
python main.py --serve              # 启动 FastAPI 服务 + 执行分析
python main.py --serve-only         # 仅启动 API 服务
python main.py --backtest           # 运行回测
```

## 必需配置

### 自选股列表

```env
STOCK_LIST=600519,300750,002594,hk00700,AAPL
```

代码格式：

- A 股：6 位数字，例如 `600519`
- 港股：`hk` + 5 位数字，例如 `hk00700`
- 美股：字母代码，例如 `AAPL`

### LLM 配置

至少配置一组可用模型。

简单模式：

```env
GEMINI_API_KEY=your_gemini_key
# 或 DEEPSEEK_API_KEY=your_deepseek_key
# 或 AIHUBMIX_KEY=your_aihubmix_key
# 或 ANTHROPIC_API_KEY=your_anthropic_key
```

多渠道模式：

```env
LLM_CHANNELS=deepseek,gemini
LLM_DEEPSEEK_API_KEY=sk-xxx
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_DEEPSEEK_MODELS=deepseek-chat
LLM_GEMINI_API_KEYS=key1,key2
LLM_GEMINI_MODELS=gemini-2.5-flash
```

第三方 OpenAI 兼容代理：

```env
LLM_CHANNELS=my_proxy
LLM_MY_PROXY_BASE_URL=https://your-proxy.example.com/v1
LLM_MY_PROXY_API_KEY=sk-xxx
LLM_MY_PROXY_MODELS=gpt-4o-mini,claude-3-5-sonnet
LLM_MY_PROXY_PROTOCOL=openai
```

高级模式：

```env
LITELLM_CONFIG=./litellm_config.yaml
```

### 搜索与通知

新闻搜索至少配置一个更好：

```env
TAVILY_API_KEYS=your_tavily_key
# 或 BOCHA_API_KEYS=your_bocha_key
# 或 SERPAPI_API_KEYS=your_serpapi_key
```

通知渠道按需配置：

- 企业微信：`WECHAT_WEBHOOK_URL`
- 飞书：`FEISHU_WEBHOOK_URL`
- Telegram：`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
- Discord：`DISCORD_WEBHOOK_URL`
- 邮件：`EMAIL_SENDER` + `EMAIL_PASSWORD`
- 通用 Webhook：`CUSTOM_WEBHOOK_URLS`

### 数据源配置

```env
EFINANCE_PRIORITY=0
AKSHARE_PRIORITY=1
TUSHARE_PRIORITY=2
YFINANCE_PRIORITY=4
REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance
```

补充经验：

- 美股优先时可把 `YFINANCE_PRIORITY=0`
- 东财限流或连接关闭时可尝试 `ENABLE_EASTMONEY_PATCH=true`
- 有 Tushare 高积分账号时，可把 `tushare` 提到 `REALTIME_SOURCE_PRIORITY` 前面

### Web 认证

```env
ADMIN_AUTH_ENABLED=true
```

首次访问时设置密码，可保护 Web 设置页中的敏感配置。

## 输出结构 (`AnalysisResult`)

分析函数返回一个 `AnalysisResult` 对象（或其列表），该对象具有丰富的结构。以下是其关键组件的简要概述，并附有真实的输出示例：

`dashboard` 属性包含核心分析，分为四个主要部分：
1.  **`core_conclusion`**: 一句话总结、信号类型和仓位建议。
2.  **`data_perspective`**: 技术数据，包括趋势状态、价格位置、量能分析和筹码结构。
3.  **`intelligence`**: 定性信息，如新闻、风险警报和积极催化剂。
4.  **`battle_plan`**: 可操作的策略，包括狙击点（买/卖目标）、仓位策略和风险控制清单。

## 配置 (`Config`)

所有分析函数都可以接受一个可选的 `config` 对象。该对象包含应用程序的所有配置，例如 API 密钥、通知设置和分析参数。

如果未提供 `config` 对象，函数将自动使用从 `.env` 文件加载的全局单例实例。

**参考:** [`Config`](src/config.py)

## 函数

### 1. 分析单只股票

**描述:** 分析单只股票并返回分析结果。

**何时使用:** 当用户要求分析特定股票时。

**输入:**
- `stock_code` (str): 要分析的股票代码。
- `config` (Config, 可选): 配置对象。默认为 `None`。
- `full_report` (bool, 可选): 是否生成完整报告。默认为 `False`。
- `notifier` (NotificationService, 可选): 通知服务对象。默认为 `None`。

**输出:** `Optional[AnalysisResult]`
一个包含分析结果的 `AnalysisResult` 对象，如果分析失败则为 `None`。

**示例:**

```python
from analyzer_service import analyze_stock

# 分析单只股票
result = analyze_stock("600989")
if result:
    print(f"股票: {result.name} ({result.code})")
    print(f"情绪得分: {result.sentiment_score}")
    print(f"操作建议: {result.operation_advice}")
```

**参考:** [`analyze_stock`](./analyzer_service.py)

### 2. 分析多只股票

**描述:** 分析一个股票列表并返回分析结果列表。

**何时使用:** 当用户想要一次分析多只股票时。

**输入:**
- `stock_codes` (List[str]): 要分析的股票代码列表。
- `config` (Config, 可选): 配置对象。默认为 `None`。
- `full_report` (bool, 可选): 是否为每只股票生成完整报告。默认为 `False`。
- `notifier` (NotificationService, 可选): 通知服务对象。默认为 `None`。

**输出:** `List[AnalysisResult]`
一个 `AnalysisResult` 对象列表。

**示例:**

```python
from analyzer_service import analyze_stocks

# 分析多只股票
results = analyze_stocks(["600989", "000001"])
for result in results:
    print(f"股票: {result.name}, 操作建议: {result.operation_advice}")
```

**参考:** [`analyze_stocks`](./analyzer_service.py)


### 3. 执行大盘复盘

**描述:** 对整体市场进行复盘并返回一份报告。

**何时使用:** 当用户要求市场概览、摘要或复盘时。

**输入:**
- `config` (Config, 可选): 配置对象。默认为 `None`。
- `notifier` (NotificationService, 可选): 通知服务对象。默认为 `None`。

**输出:** `Optional[str]`
一个包含市场复盘报告的字符串，如果失败则为 `None`。

**示例:**

```python
from analyzer_service import perform_market_review

# 执行大盘复盘
report = perform_market_review()
if report:
    print(report)
```

**参考:** [`perform_market_review`](./analyzer_service.py)

## API 与 Web

启动服务后：

- Web 首页：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

常用 API：

- `POST /api/v1/analysis/analyze`：触发分析
- `GET /api/v1/history`：查询历史分析
- `POST /api/v1/stocks/extract-from-image`：从图片识别股票
- `POST /api/v1/stocks/parse-import`：解析导入文件/文本
- `GET /api/v1/usage/summary`：LLM 用量统计
- `POST /api/v1/backtest/run`：运行回测

示例：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/analysis/analyze" \
  -H "Content-Type: application/json" \
  -d '{"stock_codes": ["600519"], "async_mode": false}'
```

## Agent 策略问股

启用方式：

```env
AGENT_MODE=true
AGENT_SKILLS=bull_trend,ma_golden_cross,volume_breakout,shrink_pullback
AGENT_MAX_STEPS=10
```

访问 `/chat` 页面即可使用策略问股。

常见内置策略：

- `bull_trend`
- `ma_golden_cross`
- `volume_breakout`
- `shrink_pullback`
- `bottom_volume`
- `dragon_head`
- `one_yang_three_yin`
- `box_oscillation`
- `chan_theory`
- `wave_theory`
- `emotion_cycle`

## 验证

```bash
python test_env.py --config
python -m py_compile main.py
./scripts/ci_gate.sh
```

文档入口：

- `docs/full-guide.md`
- `docs/LLM_CONFIG_GUIDE.md`
- `docs/FAQ.md`


##验证查询市场服务信息

.venv/bin/python scripts/test_tavily.py --query "比亚迪 股票 最新消息"
