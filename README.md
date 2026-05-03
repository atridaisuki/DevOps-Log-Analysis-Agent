# DevOps Log Analysis Agent

基于 LangGraph 的故障自动诊断系统。接收自然语言描述的故障现象，Agent 自主调用工具调查日志、指标和配置，定位根因并生成分析报告。

## 架构

ReAct 循环：planner → tool_executor → critic → reporter

- **planner**：LLM 根据当前证据决定下一步调查方向
- **tool_executor**：并行执行工具调用（ThreadPoolExecutor）
- **critic**：评估证据充分性，决定继续调查或终止
- **reporter**：生成结构化根因分析报告

## 技术栈

- Python 3.11+, FastAPI, LangGraph, Claude API
- SQLite / PostgreSQL（会话持久化）
- MCP Server（工具标准化暴露）
- Docker Compose 多服务编排

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 填入 ANTHROPIC_API_KEY

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Docker 方式：

```bash
docker-compose up
```

## API

```bash
# 同步分析
POST /agent/analyze
{
  "goal": "用户反馈登录接口响应很慢，请排查原因",
  "scenario": "scenario_01_db_pool"
}

# 流式分析（SSE）
POST /agent/analyze/stream

# 恢复暂停的分析
POST /agent/resume
```

## 评测

```bash
python -m eval.run_eval
```

10 条用例覆盖 5 个场景、3 种提问风格。根因命中率 75%，服务召回率 100%。

## 项目结构

```
app/
├── agent/          # LangGraph 图定义、节点、状态、提示词
├── tools/          # 5 个工具（search_logs, read_file, check_metrics, list_services, save_report）
├── routers/        # FastAPI 路由
├── mcp_server.py   # MCP Server
└── config.py       # 配置
data/scenarios/     # 5 个故障场景（日志、配置、指标、拓扑）
eval/               # 评测数据集与脚本
tests/              # 单元测试（22 条）
```
