# Third-Party Notices

[Up: FruitFlyAgent](README.md)

FruitFlyAgent adapts parts of [pi](https://github.com/earendil-works/pi), including the Agent loop, errors, Session storage, message normalization, tool validation, file/shell tools, token estimation, and offline test support. Attribution is consolidated here rather than repeated in module comments.

The upstream [MIT license](https://github.com/earendil-works/pi/blob/main/LICENSE) is reproduced below and distributed with this project. Runtime dependencies and their own licenses are supplied by their packages; see [pyproject.toml](pyproject.toml).

```text
MIT License

Copyright (c) 2025 Mario Zechner

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```


## Dream-RSI research attribution

The native [DreamRSI method](fruitfly_agent/lab/improvement/methods/dream_rsi/README.md) is based on Zheng et al., [Dream-RSI: Recursive Self-Improvement through Evolving Worlds](https://arxiv.org/abs/2609.14858). The implementation was written from the paper's described mechanisms; no upstream implementation code or paper figures are included. It uses a restricted declarative policy family and adds real-search holdout confirmation. Published benchmark results are not reproduced.

## Workflow and retained-state research attribution

The following native implementations were written from the papers' described mechanisms. No upstream implementation code, figures or datasets are included, and the published experiments are not reproduced.

| Native method | Research source | Implemented scope |
|---|---|---|
| [Workflow search](fruitfly_agent/lab/improvement/methods/workflow_search/README.md) | Hu, Lu and Clune, [Automated Design of Agentic Systems](https://arxiv.org/abs/2408.08435) | Archive-conditioned generation, reflection and repair over bounded sequential workflows |
| [Skill document optimization](fruitfly_agent/lab/improvement/methods/skill_edit/README.md) | Yang et al., [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904) | Trajectory minibatches, bounded edits, rejected-edit memory and selection gates |
| [Exploratory memory learning](fruitfly_agent/lab/improvement/methods/memory_exploration/README.md) | Zhu et al., [RSIAgent: Autonomous Exploration for Recursive Self-improvement in New Environments](https://arxiv.org/abs/2609.15364) | Authorized broad/focused practice, evidence-grounded consolidation and frozen memory reuse |
