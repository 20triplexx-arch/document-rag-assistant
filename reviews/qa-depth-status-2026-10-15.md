# 冻结四十题逐题状态

以下为已保存结果的离线汇总。出处位置通过不代表内容正确；历史裁判为模型辅助复核，部分裁判结论已在样本复核中纠正。空缺均未补判，不作为通过。

| 题号 | 结构与出处 | 历史模型辅助复核 | 记录 |
| --- | --- | --- | --- |
| DEPTH-A01 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A01-0.json) |
| DEPTH-A02 | 通过 | 有异议：P1核心要点中'config/runtime是保留参数名，自定义使用会导致运行错误'在答案中未被明确表述，仅在单元0隐含提及不该混用，缺少直接因果说明。其余关于ToolRuntime的使用方式覆盖充分。整体无严重事实错误，但关键点覆盖不完整。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A02-0.json) |
| DEPTH-A03 | 通过 | 有异议：unit 0和1由E7支持，unit 2引用的E6/E7不含字符串与对象用途，但必要要点P1所需的完整信息在source_context中存在却未被引用，导致漏答。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A03-0.json) |
| DEPTH-A04 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A04-0.json) |
| DEPTH-A05 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A05-0.json) |
| DEPTH-A06 | 通过 | 有异议：unit0完整回答问题并受原文支持；unit1引入无关实现细节且关系表述无据，偏离简短区分要求。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A06-0.json) |
| DEPTH-A07 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A07-0.json) |
| DEPTH-A08 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A08-0.json) |
| DEPTH-A09 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A09-0.json) |
| DEPTH-A10 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A10-0.json) |
| DEPTH-A11 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A11-0.json) |
| DEPTH-A12 | 通过 | 复核格式失败，未形成有效判定 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A12-0.json) |
| DEPTH-A13 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A13-0.json) |
| DEPTH-A14 | 通过 | 有异议：三个单元均由各自references支持，但均未覆盖P1所需的具体后端类型清单。source_context缺少gold引用的关键段落（含in-memory state、local disk等枚举），导致必要要点未被完整覆盖。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A14-0.json) |
| DEPTH-A15 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A15-0.json) |
| DEPTH-A16 | 通过 | 有异议：两个单元均错误声称原文无法区分差异，实际source_context包含skills渐进式披露与memory总是加载的明确对比。P1、P2均未覆盖。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A16-0.json) |
| DEPTH-A17 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A17-0.json) |
| DEPTH-A18 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A18-0.json) |
| DEPTH-A19 | 失败：InvalidJSON | 回答结构失败 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A19-0.json) |
| DEPTH-A20 | 通过 | 通过（待独立核对） | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A20-0.json) |
| DEPTH-A21 | 通过 | 有异议：source_context缺失定义notification不得含id且接收方不得回复的关键段落(E1)，候选答案全部依赖订阅流_meta字段间接推断，未能由自身references直接支撑核心结论。 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A21-0.json) |
| DEPTH-A22 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A22-0.json) |
| DEPTH-A23 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A23-0.json) |
| DEPTH-A24 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A24-0.json) |
| DEPTH-A25 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A25-0.json) |
| DEPTH-A26 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A26-0.json) |
| DEPTH-A27 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A27-0.json) |
| DEPTH-A28 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A28-0.json) |
| DEPTH-A29 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A29-0.json) |
| DEPTH-A30 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A30-0.json) |
| DEPTH-A31 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A31-0.json) |
| DEPTH-A32 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A32-0.json) |
| DEPTH-A33 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A33-0.json) |
| DEPTH-A34 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A34-0.json) |
| DEPTH-A35 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A35-0.json) |
| DEPTH-A36 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A36-0.json) |
| DEPTH-A37 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A37-0.json) |
| DEPTH-A38 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A38-0.json) |
| DEPTH-A39 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A39-0.json) |
| DEPTH-A40 | 通过 | 未完成 | [保存结果](../output/qa-depth-20261015-v1/compare-accept1/deepseek-flash/DEPTH-A40-0.json) |
