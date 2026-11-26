# AGENTS.md — 研究项目操作规范

本文件是本仓库唯一的规则来源，对**人类研究者、Claude Code、CI 中的评审 agent 以及任何自动化代理**同时生效。`CLAUDE.md` 只负责把本文件引入上下文，不另行定义规则。

如果某条规则和一次具体请求冲突，以本文件为准；如果确实需要改变规则，先开 ADR，再改本文件，不要在 PR 里悄悄绕过。

---

## 0. 项目使命与诚实边界

**目标**：用机器学习方法研究针对 **round-reduced DES** 的已知明文攻击（KPA）与选择明文攻击（CPA），轮数覆盖 **4、6、8、10、12、14、16**，并回答：

1. 在哪一轮之前，神经方法还能从数据里学到可用的密钥相关信息？
2. 学到的是差分/线性结构，还是别的东西？
3. 与经典差分/线性攻击相比，数据复杂度和时间复杂度处在什么位置？

**诚实边界**：16 轮即完整 DES。以现有算力和 6 GB 显存，**不预期**在 16 轮上恢复 56-bit 主密钥，也不预期击败经典攻击。高轮数的**负结果本身就是交付物**，必须如实记录，不允许通过挑选种子、挑选测试集或修改成功判据来制造正结果。

**成功的定义**：每一个结论都能由仓库中的 manifest、metrics 和可重跑命令支撑；失败结论同样要有证据。

---

## 1. 不可协商的规则

1. **`main` 只接受 Pull Request。** 分支保护开启后，任何人（包括管理员）不得直接 push、不得 force-push、不得删除 `main`。**只允许 merge commit，禁止 squash 和 rebase**：manifest 里的 `code_sha` 必须在合并后仍是 `main` 的祖先，否则结果不可复现。GitHub 设置里 squash 仍然可点（平台要求至少保留一种重写方式），但使用它会被 `main-provenance` 审计并在 issue 中记录。唯一的例外是仓库初始化时的第一个 commit，已在 ADR-0001 中记录。
2. **每个 PR 必须关闭至少一个 issue。** PR 正文使用 `Closes #N`；纯文档/杂务 PR 可以用 `No-Issue: <至少 10 字的理由>` 豁免。所有被 `Refs #N` 引用的 issue 必须在合并前关闭。
3. **每个改变代码或配置的 PR 必须附带运行结果。** 结果以 `results/**/manifest.json` 的形式提交，manifest 的 `code_sha` 必须是本 PR 历史中的提交；同时更新 `results/LATEST.json`。纯文档 PR 使用 `Results-Exempt: <理由>`。
4. **每个改变 `src/**`、`configs/**`、`scripts/**` 的 PR 必须新增或修改一份 ADR**（`docs/adr/NNNN-*.md`），或由 PR 正文的 `ADR-Exempt: <理由>` 豁免。这是 delivery-gates 的 ADR Guard。
5. **CI 门禁全绿才能合并**：`ci`、`adr-guard`、`adr-numbers`、`link-check`、`release-blockers`、`results-gate`、`issue-gate`。评审 agent 不在必过列表中——它只能评论和开 issue，不能阻断合并。
6. **评审 agent 的结果必须进入 issue。** 高/中严重度发现由 `.github/workflows/code-review.yml` 自动开 issue，标签 `agent-review` 和研究领域标签。
7. **绝不提交密钥。** 包括 GitHub token、SSH 密码、`ANTHROPIC_API_KEY`、私钥、`.env`。远程主机地址可以写进文档，凭据不行。
8. **绝不在测试集上调参。** 训练用 train split，模型选择用 val split，最终数字只跑一次 test split，并记录在 manifest 中。
9. **绝不夸大结论。** 区分"区分器准确率"和"密钥恢复成功率"；区分"比随机策略好"和"比穷举快"。
10. **失败运行也要留 manifest。** `status: failed` 的结果同样提交，并在 issue 中说明原因；删除失败证据等同于造假。

---

## 2. 仓库结构

```
AGENTS.md               本文件
CLAUDE.md               指向本文件
README.md               项目说明
docs/
  adr/                  架构与研究决策记录（ADR）
  ROADMAP.md            研究路线图与阶段划分
  EXPERIMENTS.md        实验矩阵、编号与状态
  RESEARCH-LOG.md       按时间记录假设、结果、解释
  SHIP-CHECKLIST.md     发布门禁清单
src/des_ml/
  des.py                纯 Python 参考 DES（bit-exact）
  des_torch.py          向量化 DES（GPU 数据生成 / 验证）
  data.py               数据流、密钥划分、KPA/CPA
  models/               区分器与评分器
  train/                训练入口
  eval/                 密钥恢复与排序评估
  manifest.py           结果清单
configs/                实验配置（YAML，一个实验一个文件）
scripts/
  ci/                   CI 门禁脚本
  remote/               远程 GPU 主机同步与运行
  run_conformance.py    DES 一致性运行
tests/                  pytest
results/                已提交的结果（每个运行一个目录）
research/background/    上一阶段的研究笔记与图
```

**命名**：实验 id 形如 `des{R}-{kpa|cpa}-{model}-s{seed}`；分支 `feat/…`、`fix/…`、`exp/…`、`docs/…`、`chore/…`。

---

## 3. 研究协议

### 3.1 威胁模型

- **KPA**：明文均匀随机，攻击者不能选择；同一目标密钥下可拿到多对。
- **CPA**：明文对共享固定差分 `delta`；`delta` 的来源（经典特征、随机、搜索）必须写进配置和 ADR。
- 两种场景都必须报告**数据复杂度**（目标密钥下已知/选择的明密文对数）和**时间复杂度**（训练加密当量 + 推理/搜索加密当量）。

### 3.2 划分与泄漏控制

- 以**56-bit 有效密钥**为划分单位，按 `des_ml.data.split_of` 的确定性哈希分为 80/10/10。
- 训练、验证、测试的密钥集合不相交；测试集只在最终评估时使用。
- 目标密钥 `K*` 不得作为网络输入；候选密钥 `K_t` 只能是攻击算法自己产生的状态。
- 每次评估必须报告 `initial_hit`（初始候选是否已正确）和随机重启基线。
- 任何"命中"必须用**真实 DES 重新加密**验证，不能只看网络分数。

### 3.3 基线

每个实验至少包含：

1. **随机猜测 / 预算匹配的随机搜索**（同样的候选密钥评估次数）；
2. **穷举**（同一密钥规模下的加密次数，作为时间复杂度的分母）；
3. **经典差分或线性区分器**（同轮数、同数据量）；
4. **打乱标签对照**（shuffled labels）与**随机置换负类**。

缺少任一基线，结果不得写进 README 或论文草稿。

### 3.4 统计

- 至少 3 个种子；报告均值、标准差、95% 置信区间。
- 二项比例用 Wilson 区间；AUC 用 bootstrap 区间。
- 多重比较（14 个轮数×场景组合）需要说明校正方式，或明确标注为探索性结果。
- 不以单次运行的 1–2 个百分点差异下结论。

### 3.5 计算计量

- 训练成本换算成"DES 加密当量"：`batch_size × steps × m`（m 为每个目标密钥的明文对数）。
- 与 `2^56` 穷举对比时，明确这是**数量级比较**，不是硬件实测。
- 记录 GPU 型号、显存、wall-clock、峰值显存。

### 3.6 负结果

负结果必须包含：轮数、场景、数据量、训练曲线、与随机/经典的对比、以及**至少一个能区分"表征学不到"与"解码用不上"的诊断**（例如真实密钥在全部候选中的排名分布）。只写"训练不收敛"不合格。

---

## 4. 结果清单规范

每个运行目录必须包含：

```
results/<stage>/<run_id>/
  config.yaml       实际使用的配置（由 RunWriter 写入）
  metrics.jsonl     逐步指标（JSONL）
  metrics.json      final + best
  train.log         人类可读日志
  manifest.json     必填，见下
  best.pt           可选，大文件不入库（.gitignore）
```

`manifest.json` 必填字段：

| 字段 | 含义 |
|---|---|
| `schema_version` | 当前为 1 |
| `run_id` | 时间戳 + code sha + config hash + seed |
| `created_at` | UTC ISO-8601 |
| `status` | `completed` / `failed` / `aborted` |
| `code_sha` | 产生结果的提交，必须在 PR 历史中 |
| `git_dirty` | 必须为 `false` |
| `config_path` | 配置相对路径 |
| `config_sha256` | 规范化 JSON 的 SHA-256 |
| `seed` | 随机种子 |
| `environment` | Python、torch、CUDA、GPU |
| `metrics` | `{final: {...}, best: {...}}`，全部为有限数值 |
| `artifacts` | 目录内文件列表 |

`results/LATEST.json` 指向最近一次被采纳的运行，必须与 PR 中新增的 manifest 一致。

**生成方式**：训练脚本内置 `RunWriter`；不要在 CI 里手写 manifest。远程运行由 `DES_CODE_SHA` 环境变量传入真实提交号。

---

## 5. 远程执行

- **GPU 主机**：`192.168.137.1`，Windows 11，RTX 2060 6 GB，16 GB RAM，用户 `user`。
- **远程根目录**：`D:\research\ml-des`。
- **认证**：SSH 公钥 `~/.ssh/des_remote`（控制器侧）。密码只用于首次装钥，**不得写入仓库、脚本或 CI**。
- **控制器**：当前 Linux 机器只有 2 GB 内存，只做 git/编排/静态检查，不跑训练。
- **CI**：GitHub Actions 只跑 CPU smoke（3 步）与静态门禁；真实训练永不在 CI 中跑。

约定：

1. 同步代码用 `git bundle` 或 `scp`，运行目录必须记录 `DES_CODE_SHA`。
2. 训练以**分离进程**启动，日志写到 `logs/<run_id>.log`；控制器轮询日志与 manifest。
3. 结果用 `scp` 取回 `results/<stage>/<run_id>/`，再在控制器上提交。
4. 远程主机不得保存 GitHub token；需要拉取仓库时使用只读 deploy key 或由控制器推送 bundle。
5. 不在远程主机上安装来路不明的包；Python 环境用 `uv`，依赖版本写进 `pyproject.toml`。

具体命令见 `scripts/remote/README.md`。

---

## 6. CI 门禁

| 检查 | 工作流 | 失败条件 |
|---|---|---|
| `ci` | `.github/workflows/ci.yml` | 测试、ruff、smoke 训练或 manifest 校验失败 |
| `adr-guard` | `adr-guard.yml` | 改了 watched path 却没有 ADR，且没有 `ADR-Exempt:` |
| `adr-numbers` | `adr-numbers.yml` | ADR 编号重复 |
| `link-check` | `link-check.yml` | Markdown 相对链接指向不存在的文件 |
| `release-blockers` | `release-blockers.yml` | `SHIP-CHECKLIST.md` 中有未勾选的 `BLOCKER` |
| `results-gate` | `results-gate.yml` | 无 manifest、manifest 不合法、code_sha 不在 PR 中、LATEST 未更新 |
| `issue-gate` | `issue-gate.yml` | 未关闭 issue、引用了未关闭 issue、存在 open 的 `blocker` |
| `code-review` | `code-review.yml` | **永不阻断**；只评论与开 issue |

**评审 agent 的定位**：它是"有发言权、没有否决权"的审稿人。它的意见必须被看见，但研究判断由人做。任何试图让评审 agent 成为 required check 的改动都需要新 ADR。

**后端选择**：由 secret 决定，二者共享同一套 rubric、JSON 输出和 issue 策略。
- `OPENCODE_ZEN_API_KEY` 存在 → **OpenCode Zen Go**（OpenAI 兼容，默认
  `https://opencode.ai/inference/go/openai/v1`、`deepseek-v4.1-flash`，
  每次 PR 用稳定的 `x-opencode-session`）。该后端没有仓库工具，diff（截断
  90k 字符）和 manifest 摘要直接放进 prompt。
- 否则 `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` 存在 → **Claude Agent SDK**，
  只读工具 `Read/Grep/Glob`。
- 两者都没有 → 在 PR 里贴 skip 通知并成功退出，绝不失败 CI。
- **除非同时设置 `ALLOW_TOOL_TRANSPORT=1` 与 `GITHUB_EVENT_NAME=workflow_dispatch`，CI 禁用带工具的 Claude 后端**：diff 是
  不可信的 PR 内容，Read/Grep/Glob 可能被提示注入用来读取仓库外文件并写进公开评论。
  PR 评审只用无工具的 OpenCode 后端；opt-in 仅用于人工确认可信的 dispatch。manifest
  指标是"主张"而不是事实，由 `results-gate` 独立校验 schema、`code_sha`、config hash
  和干净工作树。

---

## 7. 评审 Agent 的审查清单

评审 agent **同时审查代码与研究内容**。研究部分必须回答：

- **R1 问题与假设**：问题是否可否证？是否把"区分"当成"密钥恢复"？是否把 toy key space 当成 56-bit DES？
- **R2 设计**：密钥划分、预算匹配基线（随机搜索、穷举、经典差分/线性）、种子、置信区间、对照、算力计量是否齐全？
- **R3 结果**：每个结论是否由 metrics 支撑？负结果解释是否正确？缺少哪些分析（排名诊断、消融、校准、power、多重比较、与经典上界对比）？
- **R4 下一步**：给出具体、按优先级排序的后续实验；说明什么结果会改变结论。

输出中的 `research_analysis` 和 `recommendations` 会渲染在 PR 评论里。对于触及
`src/`、`configs/` 或 `results/` 的 PR，agent 会开一个 `[research] PR #N analysis` issue
保存完整分析报告（标签 `research-review`、`analysis`）；high/medium 建议各自开
`[research] ...` issue（标签 `recommendation`）。同类标题精确匹配去重，标签缺失
不会丢失报告。以下代码清单同样适用：

按严重度输出，必须带文件/行号或明确说明是推测：

1. **密码学正确性**：表、轮数、末轮交换、密钥编排、round-reduced 语义。
2. **泄漏**：密钥划分、目标密钥是否入输入、测试集是否被用于选模。
3. **基线**：随机搜索、穷举、经典差分/线性、shuffled labels。
4. **统计**：种子数、置信区间、多重比较。
5. **训练方法**：损失是否优化了声称的目标（排序 vs 分类）、类别平衡、早停。
6. **计算计量**：数据/时间复杂度的单位是否与穷举可比。
7. **可复现性**：manifest、code_sha、config hash。
8. **声称**：PR/README 中每一句结论是否被 metrics 支撑；高轮数是否诚实报告负结果。
9. **代码与安全**：密钥、越界写、缺少测试。

---

## 8. 开发流程

1. **开 issue**：用 `Experiment` 或 `Task` 模板，写清假设、成功/失败判据、预算。
2. **建分支**：从 `main` 拉出 `exp/…#issue` 或 `feat/…#issue`。
3. **先写 ADR**（若改 watched path）：记录选择、备选、代价。
4. **实现 + 单元测试**，本地/CI 跑通。
5. **在 GPU 主机运行**，把 `results/<stage>/<run_id>/` 拉回仓库，更新 `results/LATEST.json`。
6. **提交**：代码与结果分开 commit，但同一个 PR；commit message 写清运行 id。
7. **开 PR**：填模板（Summary / Linked issues / Results / Risk），关联 issue。
8. **等门禁**：修到全绿；评审 agent 的 issue 逐条回应（关闭或开 follow-up）。
9. **Merge commit**（不是 squash/rebase），删除分支。合并后确认 `code_sha` 指向的提交仍是 `main` 的祖先（`git merge-base --is-ancestor <sha> main`）。
10. **更新 `docs/RESEARCH-LOG.md`**：一句话记录这次学到了什么。

Commit message 约定：`<type>(<scope>): <summary>`，type ∈ `feat|fix|exp|docs|chore|ci|test`。不要把多个不相关实验塞进一个 PR。

---

## 9. Definition of Done

一个实验只有在以下全部满足时才算完成：

- [ ] issue 中的假设与判据已写明；
- [ ] 配置、代码、种子、命令可复现；
- [ ] 至少 3 个种子，或明确说明为何单种子；
- [ ] 基线齐全（随机、穷举、经典、对照）；
- [ ] 结果目录含合法 manifest，`code_sha` 属于本 PR；
- [ ] `results/LATEST.json` 已更新；
- [ ] ADR 已记录方法选择；
- [ ] 评审 agent 的 high/medium issue 已处理；
- [ ] `docs/RESEARCH-LOG.md` 已更新；
- [ ] 结论没有超出数据。

---

## 10. 当前阶段

- **Stage 0（进行中）**：仓库治理、可验证 DES、结果清单、CI 门禁、远程 GPU 执行。
- **Stage 1**：经典 DDT/LAT 上界 + SPADE 分块打分器（4→8 轮）。
- **Stage 2**：末轮子密钥排序、精确密钥编排解码、真实重加密验证。
- **Stage 3**：KPA 线性/奇偶先验与差分先验的对比、泄漏审计。
- **Stage 4**：R=8 主终点 F1、10–16 轮边界与 signal-death `r*`。
- **Stage 5**：复现、最终统计、成文。

**研究策略已冻结**：主方案是 SPADE（结构先验 + DDT 初始化残差 + 精确解码），
不是 56-bit 端到端回归，也不是候选密钥精化网络。理由与被拒方案见
[ADR-0008](docs/adr/0008-research-strategy-spade.md)。预注册否证 F1–F6 见
[ADR-0006](docs/adr/0006-pre-registered-endpoints.md)，在跑确证实验前不得修改。

详细计划见 `docs/ROADMAP.md`；实验编号与状态见 `docs/EXPERIMENTS.md`。

---

## 11. 给自动化代理的额外约束

- 不得修改 `.github/workflows/` 来绕过门禁；此类改动必须单独 PR 并由人审。
- 不得在 `results/` 之外写运行产物；不得删除失败运行。
- 不得把远程密码、token、私钥写入任何被 git 跟踪的文件。
- 不得在未运行的情况下填写 metrics；`status: completed` 意味着脚本真的跑完了。
- 遇到规则冲突或不确定，先开 issue 提问，不要自行解释规则。
