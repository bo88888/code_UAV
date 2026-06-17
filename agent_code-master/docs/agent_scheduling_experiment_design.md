# 智能体调度实验设计

## 1. 实验目标

该实验只评价多智能体算法服务的编排与调度能力，不将四种航线算法的
确定性示例输出包装成新的路径规划精度结论。核心问题包括：

1. DAG 并行调度能否降低任务流完工时间并提高吞吐量。
2. 医疗任务优先级能否提高紧急任务的截止期满足率。
3. retry、fallback 和 optional-skip 能否提高工具故障下的任务成功率。
4. 随任务流数量、服务并发度和工具故障率增加，调度器是否保持稳定。

## 2. 论文实验形式对应

- ScheduleNet 使用 makespan、归一化调度性能、推理时间、问题规模和消融
  实验评价多智能体调度。本项目据此报告归一化 makespan、任务规模曲线、
  服务并发度曲线和 95% 置信区间。
- Gradientsys 使用任务成功率、完成时延、并行执行消融和动态恢复分析评价
  多智能体编排。本项目据此报告端到端成功率、故障恢复率以及
  `w/o parallelism`、`w/o replanning` 消融。
- CoordField 和 UAV-MARL 强调动态任务、资源协调、响应效率、截止期与
  扩展性。本项目据此加入优先级加权截止期满足率和负载—故障热力图。

参考文献：

1. Park, J., Bakhtiyar, S., and Park, J. ScheduleNet: Learn to Solve
   Multi-Agent Scheduling Problems with Reinforcement Learning, 2021.
   https://arxiv.org/abs/2106.03051
2. Song, X. et al. Gradientsys: A Multi-Agent LLM Scheduler with ReAct
   Orchestration, 2025. https://arxiv.org/abs/2507.06520
3. Zhang, T. et al. CoordField: Coordination Field for Agentic UAV Task
   Allocation in Low-altitude Urban Scenarios, 2025.
   https://arxiv.org/abs/2505.00091
4. Guven, I. and Parlak, M. UAV-MARL: Multi-Agent Reinforcement Learning
   for Time-Critical and Dynamic Medical Supply Delivery, 2026.
   https://arxiv.org/abs/2603.10528

以上论文仅用于确定评价维度和图表形式。本项目没有复制其数值，也没有声称
复现其模型。

## 3. 对比方法

| 方法 | 并行 | DAG | 重试 | 能力回退 | 紧急度优先 |
|---|---:|---:|---:|---:|---:|
| Serial-FIFO | 否 | 否 | 否 | 否 | 否 |
| Parallel-FIFO | 是 | 是 | 统一一次 | 否 | 否 |
| HEFT-DAG | 是 | 是 | 统一一次 | 否 | 否 |
| Capability-DAG+Replan | 是 | 是 | 能力相关 | 是 | 是 |

所有方法使用同一组任务到达时间、服务时延和失败事件。HEFT-DAG 按工作流
到达顺序和上行秩选择就绪节点；本文方法按截止期、任务紧急度和关键路径
联合排序。

## 4. 仿真假设

- 每个任务流包含 10 个节点：4 个环境检查、4 个算法服务、风险评估和报告。
- 服务时延使用变异系数为 0.13 的高斯模型，并设置正的最小时延。
- 工具调用失败服从独立 Bernoulli 事件，并按能力设置风险权重。
- 任务分为三个紧急等级，对应 7.5、10.0 和 13.0 秒截止期裕量。
- 每个数据点运行 50 次，固定主种子为 `20260615`。
- 图中阴影和误差线为 `mean ± 1.96 × sample_std / sqrt(n)`。

失败任务采用三倍截止期裕量构造惩罚时延，避免“提前失败”被错误解释为
低时延。

## 5. 指标

- `normalized_makespan`：相对 Serial-FIFO 的总完工时间，越低越好。
- `priority_weighted_on_time_rate`：按医疗任务紧急度加权的截止期满足率。
- `throughput_per_min`：每分钟完成的任务流数量。
- `utilization`：服务工作线程忙碌时间占比。
- `success_rate`：成功生成可执行保障报告的任务流比例。
- `recovery_success_rate`：观察到至少一次工具失败后仍完成的任务流比例。
- `failure_penalized_latency_s`：对失败任务加入截止期惩罚的平均时延。

## 6. 复现

```powershell
python -m experiments.agent_scheduling_benchmark --trials 50
python -m experiments.generate_scheduler_paper_figures
python -m unittest discover -s tests -v
```

JSON 文件保存完整实验设置、随机种子、均值、标准差、置信区间和样本数。
