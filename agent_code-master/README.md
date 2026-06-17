# 低空任务智能体调度中心

面向应急医疗和应急物资配送的多智能体、多算法服务编排系统。系统将
任务需求解析为空域、气象、无人机、机巢、航线、时间窗、风险和报告
节点，并通过依赖感知调度器并行执行。

## 编排 DAG

```text
A1 空域检查 ─────┐
A2 气象检查 ─────┼─> B1 DRL-LLM 合规航线 ─────┐
A3 无人机状态 ───┼─> B2 NN 空地协同 ──────────┤
A4 机巢状态 ─────┼─> B3 TWA-MILP 时间窗调度 ──┼─> C1 风险评估 ─> R1 报告
                  └─> B4 CoordField 任务分配 ──┘
```

异常恢复策略：

- 临时禁飞区导致合规航线失败时，切换到空地协同配送。
- 医疗调度遇到无可用无人机时，等待后重试。
- 可选对比算法失败时可跳过，不阻塞已具备保障条件的方案。
- 所有 retry、fallback、skip 和 blocked 事件写入执行轨迹。

## 运行

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动算法服务：

```powershell
python -m uvicorn services.low_altitude_service.app:app --port 8888
```

启动调度中心：

```powershell
python -m uvicorn api_main:app --port 9000
```

也可以使用：

```powershell
docker compose up --build
```

## 提交任务

`POST http://127.0.0.1:9000/api/v1/task/submit`

```json
{
  "task_id": "MEDICAL_001",
  "requirement_xml_path": "data/requirement.xml",
  "simulation_scenario": "normal"
}
```

可用实验场景：

- `normal`
- `bad_weather`
- `airspace_restricted`
- `no_available_uav_once`
- `no_available_uav`
- `dock_congested`

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 算法对比

```powershell
python -m experiments.algorithm_comparison
```

结果写入 `outputs/algorithm_comparison.json`，包含：

- 四种算法的时间窗满足率、平均耗时、能耗和合规评分。
- 正常、恶劣天气、临时禁飞和无人机短时不可用场景的恢复结果。
- 串行执行与能力感知 DAG 的确定性服务时延对比。

## 智能体调度论文实验

运行 50 次固定种子、配对实例的离散事件仿真：

```powershell
python -m experiments.agent_scheduling_benchmark --trials 50 --seed 20260615
python -m experiments.generate_conference_paper_assets
```

实验比较：

- `Serial-FIFO`：单智能体顺序工具调用。
- `Parallel-FIFO`：依赖满足后的并行先到先服务。
- `HEFT-DAG`：基于关键路径上行秩的 DAG 调度。
- `RL-DAG`：通过交叉熵策略搜索得到的学习型 DAG 优先级基线。
- `Parallel-FIFO+Recovery`：FIFO 排序加同等 capability recovery。
- `HEFT-DAG+Recovery`：HEFT 排序加同等 capability recovery。
- `RL-DAG+Recovery`：学习型排序加同等 capability recovery。
- `Capability-DAG+Replan`：active recovery、deadline、urgency 和 critical path 联合排序。

恢复动作带 deadline guard：优先选择仍可满足医疗时间窗的 retry/fallback；
若不能准时完成，则仅在有限晚到有效窗口内尝试最快注册 fallback。

输出文件：

- `outputs/agent_scheduling_benchmark.json`：原始聚合指标、标准差和 95% 置信区间。
- `paper/ICCC_conference_paper/figures/scheduler_scalability.png`：任务规模下的 makespan 和优先级加权准时率。
- `paper/ICCC_conference_paper/figures/scheduler_resource_efficiency.png`：服务 worker 扩展下的吞吐量和利用率。
- `paper/ICCC_conference_paper/figures/scheduler_robustness.png`：独立残余故障下的成功率和恢复率。
- `paper/ICCC_conference_paper/figures/scheduler_ablation.png`：并行、重规划、fallback 和优先级消融。
- `paper/ICCC_conference_paper/figures/scheduler_correlated_geography.png`：相关性故障压力测试和纽约、芝加哥、旧金山地理场景验证。
- `paper/ICCC_conference_paper/conference_paper.pdf`：按 IEEE conference 模板生成的完整论文。

实验设计与论文指标对应关系见
`docs/agent_scheduling_experiment_design.md`。这些结果是调度器级仿真；
地理场景使用真实医院坐标和固定 2024 年气象站摘要参数，但不能表述为
真实无人机飞行测试或认证航路数据。

## 主要目录

```text
agents/                         智能体编排与报告
core/                           请求、任务和能力模型
mcp/                            算法服务调用协议
scheduler/                      依赖调度与异常重规划
services/low_altitude_service/  低空算法服务
experiments/                    可重复算法对比实验
tests/                          单元和端到端测试
data/requirement.xml            应急医疗配送需求
```
