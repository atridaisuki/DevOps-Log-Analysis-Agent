# DevOps Log Analysis Agent — 开发计划

## 项目定位

一个面向故障排查场景的单 Agent 系统。用户描述一个故障现象（比如"API 响应变慢"或"服务频繁重启"），Agent 自主搜索日志、读取配置、查看指标、形成假设、验证假设、定位根因、输出修复建议。

核心价值不在日志分析本身，而在于通过这个场景完整实现 Agent 编排层的所有关键能力：
- ReAct 循环 + LangGraph state machine
- Planning / replanning
- Critic / self-correction
- 工具失败恢复
- 短期 + 长期记忆
- 上下文膨胀控制
- Streaming
- Checkpointing
- Human-in-the-loop
- 动态工具选择
- 评估体系

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 编排框架 | LangGraph | 状态机表达清晰，面试好讲 |
| LLM | Claude (Anthropic API) | 和前两个项目一致 |
| API 框架 | FastAPI | 和前两个项目一致 |
| 前端 | Streamlit | 轻量，展示推理过程和工具链路 |
| 持久化 | SQLite | checkpointer + 长期记忆 |
| 测试 | pytest | 标准选择 |

## 项目结构

```
devops-log-agent/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # Settings
│   ├── schemas.py               # 请求/响应模型
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py             # AgentState TypedDict
│   │   ├── graph.py             # LangGraph 图定义
│   │   ├── nodes.py             # planner / tool_executor / critic / reporter
│   │   ├── prompts.py           # system prompt + planner prompt
│   │   └── memory.py            # 短期/长期记忆管理
│   │
│   ├── tools/
│   │   ├── __init__.py          # 工具注册
│   │   ├── base.py              # 工具基类 + 统一返回格式
│   │   ├── search_logs.py       # 日志搜索
│   │   ├── read_file.py         # 读取文件
│   │   ├── list_services.py     # 服务拓扑查询
│   │   ├── check_metrics.py     # 指标查询
│   │   └── save_report.py       # 保存报告
│   │
│   └── routers/
│       ├── agent.py             # POST /agent/analyze, /agent/analyze/stream
│       └── health.py            # GET /health
│
├── data/
│   └── scenarios/               # 故障场景数据（日志+配置+指标）
│       ├── scenario_01_db_pool/ # 数据库连接池耗尽
│       ├── scenario_02_oom/     # 内存泄漏 OOM
│       ├── scenario_03_config/  # 配置错误
│       ├── scenario_04_cascade/ # 级联故障
│       └── scenario_05_disk/    # 磁盘写满
│
├── eval/
│   ├── dataset.json             # 评估数据集
│   ├── run_eval.py              # 评估脚本
│   └── results/                 # 评估结果
│
├── ui/
│   └── streamlit_app.py         # Streamlit 前端
│
├── tests/
│   ├── test_tools.py            # 工具单元测试
│   ├── test_graph.py            # 图流转测试
│   └── test_api.py              # API 集成测试
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 架构设计

### AgentState

```python
class AgentState(TypedDict):
    user_goal: str                                          # 用户描述的故障
    scenario_path: str                                      # 故障场景数据目录
    messages: Annotated[list[BaseMessage], add_messages]     # LLM 对话历史
    current_plan: str                                       # 当前排查计划
    hypotheses: list[str]                                   # 当前假设列表
    findings: list[str]                                     # 已确认的发现
    tool_call_history: list[dict]                           # 工具调用记录
    files_read: list[str]                                   # 已读文件（去重用）
    iteration_count: int                                    # 当前迭代次数
    max_iterations: int                                     # 最大迭代次数
    status: Literal["running", "completed", "failed"]       # Agent 状态
```

### LangGraph 图

```
START
  │
  ▼
planner ──── (无需工具) ────→ reporter ──→ END
  │
  │ (需要工具)
  ▼
tool_executor
  │
  ▼
observer ──→ critic
               │
               ├── (信息不足) ──→ planner（循环）
               │
               ├── (信息充分) ──→ reporter ──→ END
               │
               └── (达到上限) ──→ reporter ──→ END
```

**节点职责：**

| 节点 | 职责 |
|------|------|
| `planner` | 调用 Claude（带 tools），分析当前状态，决定下一步：调用哪个工具、用什么参数，或者直接给结论 |
| `tool_executor` | 执行 planner 选择的工具，收集原始结果 |
| `observer` | 处理工具结果，提取关键信息，更新 findings / hypotheses |
| `critic` | 评估当前 findings 是否足以回答 user_goal，决定继续还是结束 |
| `reporter` | 汇总所有 findings，生成结构化排查报告 |

**条件边：**

| 边 | 条件 |
|----|------|
| planner → tool_executor | planner 输出包含 tool_calls |
| planner → reporter | planner 输出不包含 tool_calls（直接给结论） |
| critic → planner | findings 不足 且 iteration_count < max_iterations |
| critic → reporter | findings 充分 或 iteration_count >= max_iterations |

---

## 五个工具

### 1. search_logs
- **输入**: keyword, severity(可选), time_range(可选), service_name(可选)
- **功能**: 在场景的日志文件中搜索匹配条目
- **实现**: 读取 `{scenario_path}/logs/*.log`，按条件过滤，返回匹配行 + 上下文

### 2. read_file
- **输入**: file_path, start_line(可选), end_line(可选)
- **功能**: 读取配置文件、代码文件
- **实现**: 路径校验（必须在 scenario_path 内），读取并返回内容
- **限制**: 单次最多返回 200 行

### 3. list_services
- **输入**: 无（或 service_name 查单个服务详情）
- **功能**: 返回系统服务拓扑、依赖关系、端口、健康状态
- **实现**: 读取 `{scenario_path}/topology.json`

### 4. check_metrics
- **输入**: service_name, metric_type(cpu/memory/latency/error_rate), time_range(可选)
- **功能**: 查询服务指标数据
- **实现**: 读取 `{scenario_path}/metrics/{service_name}.json`

### 5. save_report
- **输入**: title, root_cause, evidence, suggestions
- **功能**: 保存结构化排查报告
- **实现**: 写入 `data/reports/{session_id}_{timestamp}.json`

**统一返回格式：**
```python
class ToolResult(TypedDict):
    success: bool
    data: str | dict | list
    error: str | None
```

---

## 故障场景数据设计

每个场景包含：
```
scenario_XX/
├── description.json    # 故障描述 + 预期根因（评估用）
├── topology.json       # 服务拓扑和依赖关系
├── logs/
│   ├── api-gateway.log
│   ├── user-service.log
│   ├── db-service.log
│   └── ...
├── configs/
│   ├── api-gateway.yaml
│   ├── db-service.yaml
│   └── ...
└── metrics/
    ├── api-gateway.json
    ├── user-service.json
    └── ...
```

### 五个场景

| # | 场景 | 根因 | 复杂度 | 覆盖能力 |
|---|------|------|--------|----------|
| 1 | API 响应超时 | 数据库连接池耗尽 | 简单 | 基础 ReAct 循环 |
| 2 | 服务频繁重启 | 内存泄漏 OOM | 简单 | 多工具协作 |
| 3 | 部分请求 500 | 配置文件环境变量错误 | 中等 | 假设验证 + replanning |
| 4 | 全站不可用 | 上游认证服务挂了，级联失败 | 中等 | 多服务排查 + 依赖链追踪 |
| 5 | 写入操作全部失败 | 磁盘空间写满 | 简单 | 指标分析 |

---

## 编排层能力覆盖

| 能力 | 实现方式 |
|------|----------|
| **ReAct 循环** | planner → tool → observer → critic → planner 循环 |
| **Planning** | planner 节点根据 user_goal 生成排查计划 |
| **Replanning** | critic 判断当前假设不成立时，planner 重新规划方向 |
| **Critic / Self-correction** | critic 节点评估 findings 质量，判断是否需要补充 |
| **工具失败恢复** | tool_executor 捕获异常，observer 将错误写入 state，planner 换策略 |
| **短期记忆** | AgentState.messages + findings + hypotheses |
| **长期记忆** | SQLite checkpointer，跨会话持久化 |
| **上下文膨胀控制** | 超过阈值时对历史 messages 做 summarization |
| **Streaming** | SSE 逐步推送每个节点的执行结果 |
| **Checkpointing** | LangGraph MemorySaver / SqliteSaver |
| **Human-in-the-loop** | 高风险操作前暂停等待用户确认（interrupt_before） |
| **动态工具选择** | 根据场景类型决定暴露哪些工具 |
| **循环终止** | max_iterations + critic 判断 + 连续失败检测 |
| **去重** | files_read 集合避免重复读取 |
| **Trace 记录** | tool_call_history 记录每步的工具、输入、输出、耗时 |

---

## 实施阶段

### Phase 1：最小可运行 Agent
- 项目骨架 + 依赖安装
- AgentState 定义
- 5 个工具实现 + 单元测试
- LangGraph 图（planner + tool_executor + observer，先不加 critic）
- 1 个故障场景数据
- FastAPI 路由（同步）
- 手动验证：一个简单问题能跑通

### Phase 2：状态与记忆
- 添加 critic 节点 + 条件边
- Session memory（SqliteSaver checkpointer）
- 多轮对话支持（同一 session_id 继续排查）
- files_read 去重
- 上下文膨胀控制（message summarization）

### Phase 3：自纠错与高级编排
- 工具失败 → 自动重试 / 换策略
- Replanning（假设被推翻后重新规划）
- Human-in-the-loop（interrupt_before）
- 动态工具选择
- Streaming SSE
- 补充 2-3 个故障场景

### Phase 4：评估与展示
- 完善全部 5 个故障场景
- 评估数据集 + 评估脚本
- 评估指标：success_rate / avg_steps / avg_latency / tool_failure_rate
- Streamlit UI（展示推理过程 + 工具调用链）
- Dockerfile + docker-compose
- README

---

## 评估设计

### 数据集格式
```json
{
  "task_id": "task_01",
  "scenario": "scenario_01_db_pool",
  "user_input": "API 响应时间从 200ms 飙升到 5s 以上，用户反馈大量超时",
  "expected_root_cause": "数据库连接池耗尽",
  "expected_tools_used": ["search_logs", "check_metrics", "read_file"],
  "max_acceptable_steps": 6
}
```

### 评估指标
| 指标 | 说明 |
|------|------|
| success_rate | agent 找到正确根因的比例 |
| avg_steps | 平均迭代步数 |
| avg_latency_ms | 平均总耗时 |
| avg_tool_calls | 平均工具调用次数 |
| tool_failure_rate | 工具调用失败率 |
| self_correction_count | 自纠错发生次数 |

---

## 验证标准

1. 场景 1（简单）：agent 在 2-4 步内定位到"数据库连接池耗尽"
2. 场景 4（中等）：agent 能追踪依赖链，从 API 网关 → 用户服务 → 认证服务
3. 工具返回错误时，agent 不崩溃，能换策略继续
4. 同一 session 的第二轮对话能复用第一轮的 findings
5. 评估脚本输出完整指标报告
