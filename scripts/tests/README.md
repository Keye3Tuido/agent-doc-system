# doc-system 回归测试套件

## 目录

```
tests/
├── README.md                    本文件
├── run.sh                       一键回归入口
├── unit/                        单元测试（纯函数 + serializer）
│   ├── test_postprocess.py      后处理层测试（不依赖 tree-sitter）
│   ├── test_serializer.py       doc-structure-import 序列化测试
│   └── test_format_check.py     doc-format-check 校验规则测试
└── snapshots/                   端到端快照（待补）
    ├── README.md                补建说明
    └── (cpp_proj/ ts_proj/ py_proj 三标杆项目快照)
```

## 运行

```bash
# 单元层（默认快速通过）
bash scripts/tests/run.sh

# 完整回归（含 snapshots，需先 setup 标杆项目）
bash scripts/tests/run.sh --full
```

## 客观指标对应（TODO §5.1）

单元测试覆盖：
- [x] `doc-structure-import.py` 5 字段全序列化
- [x] `doc-format-check.py` 全字段校验通过 / 拒绝
- [x] 后处理：模块归并 + role 分类 + pattern 识别 + dead import 过滤

snapshot 层覆盖（待补）：
- [ ] `deps` 数量从百级降到十级
- [ ] `deps.use` 非空率 > 80%
- [ ] `deps.role` 已分类率 > 70%
- [ ] `exports` 不含实现文件中内部函数
- [ ] `inner` 覆盖核心公开类清单 ≥ 90%

## 主观指标（TODO §5.2）

agent 端到端问答基线，需人工准备黄金答案，此处不自动化。

## 标杆项目（待补）

`snapshots/` 期望布局：

```
snapshots/cpp_proj/
├── pinned-commit.txt        固定 commit sha
├── source-link.txt          标杆项目 git URL（不入库源码）
├── golden-deps.json         人工标注的黄金 deps
├── golden-exports.json      黄金 exports（白名单）
└── expected-output.json     当前脚本期望输出
```

补建步骤：
1. 选 3 个公开标杆项目（C++ git-submodule / TS monorepo / Python 单仓）
2. 各 clone 到本地 + checkout 到 pinned commit
3. 跑 `python3 scripts/doc-structure-extract.py` 生成快照
4. 人工标注黄金 deps / exports，纳入仓库
5. 在 run.sh 加端到端比对
