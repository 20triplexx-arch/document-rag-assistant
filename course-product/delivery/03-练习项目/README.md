# 3个独立Python练习

Python 3.12标准库，默认离线，零第三方Python依赖。

| 文件 | 功能 | 默认行为 |
| --- | --- | --- |
| tool_agent.py | 工具契约与有上限的模型循环 | 执行命令行给定的算术参数 |
| memory_chat.py | SQLite保存与恢复会话 | 回放上一条输入 |
| document_qa.py | 本地文档检索与来源 | 关键词检索后摘录原文 |
| common.py | DeepSeek请求与错误处理 | 仅在--online路径调用 |
| test_projects.py | 离线回归测试 | 临时数据，替身模型，不联网 |

快速运行：
```powershell
python tool_agent.py --operation multiply --a 18 --b 7
python memory_chat.py --session alice --message "我在学RAG"
python memory_chat.py --session alice --message "上一句是什么？"
python document_qa.py "报销材料有哪些？"
python -m unittest -v test_projects.py
```

完整环境、联网和排错步骤见../00-开始学习/配置与排错.md。

源码是独立教学实现；不调用eval、不自动重试、不读取课程外的账号数据库。运行后生成的runtime属于你的本机数据，交付他人时不要打包它。

关键词评分是词项重叠，不是语义向量或概率。来源检查只验证编号存在，联网结论仍需回查。默认示例规则是虚构资料。
