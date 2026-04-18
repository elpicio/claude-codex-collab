# Review Spec

review 和 verify 不是一回事。

review 负责：

- 检查实现是否符合任务范围
- 先报问题，再给概述
- 检查测试、文档、风险说明是否齐全

verify 负责：

- 跑 `verify.json` 里的命令
- 把结果写回 shared runtime
- 只对当前 workspace 指纹成立

如果 workspace 内容变了，旧 verify 结果不能继续当作有效结论。
