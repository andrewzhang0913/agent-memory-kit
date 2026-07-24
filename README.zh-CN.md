# agent-memory-kit

[![CI](https://github.com/andrewzhang0913/agent-memory-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewzhang0913/agent-memory-kit/actions/workflows/ci.yml)

[English](README.md) | **简体中文**

一套面向 AI agent 的本地优先、分层记忆工具库。纯文件存储,零必需依赖,可离线运行。

> **无记忆，不智能——而过期或错误的记忆，比没有记忆更危险。** 这套 kit 的核心
> 不是"能存记忆"，而是**堵住那些半开的环**：记忆系统悄悄用了空的、过期的、
> 作用域错配的数据，却没有任何人察觉。

## 为什么会有这个项目

这套 kit 不是从一份"记忆功能清单"出发设计的。它是从长期跑 agent、日复一日
真实踩到的四个痛点里长出来的：

| 痛点 | kit 的解法 |
|------|-----------|
| **程序在任务中途挂掉**（OOM、ctrl-C、部署重启），进行中的工作丢失 | append-only journal——每个动作**当场落盘**，程序被杀也不丢已经发生的事 |
| **任务被中断**，下一次运行只能从头盲开 | `find_open_session_ids` 把没正常关闭的会话捞出来，让 agent **接续**线索而不是重新盲开 |
| **换一个 agent 接手**，记忆却带不过去 | canonical 身份 + `agent:<id>` 作用域，给每条痕迹稳定的归属，"谁做了什么"跨 agent、跨会话都可辨认 |
| **多个 agent 协同**，你得反复交代同样的背景 | 共享 `global` 作用域：背景**写一次，所有 agent 都读得到**——还有写时护栏，防止它们互相污染对方的私有记忆 |

这四条每一条都是我们真撞上的 bug，不是拍脑袋想出来的功能。跑起来看看：
[`examples/crash_recovery.py`](examples/crash_recovery.py) 和
[`examples/multi_agent.py`](examples/multi_agent.py)。

## 里面有什么

它把这些模式提炼成一个小而可复用的库：

- **韧性分层 LLM 客户端**——一条有序降级阶梯（upstream → OpenRouter → 本地），
  每层各有超时、重试，且**以"验证通过"作为成功条件**（"思考型"模型吐出的空内容
  会被拒绝、往下一层降级）。失败是**显式的**（`LLMError`），绝不悄悄返回空字符串。
- **多 agent 身份与作用域模型**——canonical ID + alias 归一化，`global` 与
  `agent:<id>` 两种记忆作用域，写时作用域护栏，以及诚实的署名痕迹（解析不出的
  身份会被**标记**，而非伪造）。
- **append-only 黑匣子 journal**——每个动作记为一行 JSON，盖上
  actor/scope/task-owner；单活跃会话策略。
- **新鲜度哨兵**——为每份记忆产物声明预期的刷新节奏；哨兵标记
  `FRESH` / `STALE` / `MISSING`，让悄悄停止刷新的任务被**自动抓出来**。
- **可插拔召回**——一个 `RecallBackend` 协议，自带零依赖的 lexical 默认实现，
  外加一个接外部向量库的 Hermes 参考适配器。

## 安装

```bash
pip install -e .          # 核心（仅标准库）
pip install -e ".[dev]"   # + pytest
```

需要 Python ≥ 3.10。核心**无任何运行时依赖**。
## 快速上手

```bash
python examples/quickstart.py
```

记录一个会话 → 召回它（lexical 后端）→ 检查新鲜度 → 通过 LLM 阶梯蒸馏经验
（无 LLM 可达时优雅降级）。全程只在临时目录里的纯文件上运行。

另有两个可直接运行的示例，正好对应上面的痛点：

```bash
python examples/crash_recovery.py   # 中断一个会话，重启后接续它
python examples/multi_agent.py      # 跨 agent 共享背景 + 作用域护栏
```

```python
from agent_memory import Journal, Recall, MemoryConfig

config = MemoryConfig(home="~/.agent-memory")
config.ensure_dirs()

journal = Journal(config=config)
ov = {"agent_id": "researcher", "memory_scope": "global"}
sid = journal.start_session("investigate deploy timeout", identity_overrides=ov)
journal.log_action("raised the bridge timeout from 8s to 150s", sid=sid, identity_overrides=ov)
journal.end_session(sid, identity_overrides=ov)

hits = Recall(config=config).search("why did the job stop", limit=5)
for h in hits:
    print(h.score, h.text)
```

## 架构一览

一个分层模型，数据自下而上从原始事件流向蒸馏后的知识：

| 层 | 内容 | 模块 |
|----|------|------|
| L1 | append-only 操作 journal（黑匣子） | `journal.py` |
| L2 | 情节式摘要（应用层） | *仅示例* |
| L3 | 语义事实 + 召回（向量/lexical）+ 实体索引 | `recall.py`、`entity_index.py`、`distiller.py` |
| L4 | 生命周期（合并/遗忘）——**手动队列，绝不自动改写** | *仅文档* |

横切关注点：韧性 LLM 客户端（`llm.py`）、身份/作用域模型（`identity.py`）、
新鲜度哨兵（`freshness.py`）。

详见 [`docs/architecture.md`](docs/architecture.md)、
[`docs/identity-model.md`](docs/identity-model.md)、
[`docs/design-principles.md`](docs/design-principles.md) 和
[`docs/recall-backends.md`](docs/recall-backends.md)。

## 这个库的边界

这套 kit 是从一个更大的个人系统里抽取出来的**可复用核心**。那个系统的应用层
（Obsidian 知识库策展、新闻/天气早报摘要、Hermes 网关集成）刻意**不**随包发布
——它们与具体部署强绑定。这里放的是通用机制，而 Hermes/LanceDB 召回路径仅作为
*参考适配器*，用来展示后端契约。一个正经的嵌入式向量后端（例如 sqlite-vec）是
非常欢迎的社区贡献——见 [`docs/recall-backends.md`](docs/recall-backends.md)。

## 许可证

MIT——见 [LICENSE](LICENSE)。

