# 案例12 多 Agent 旅行规划

旅行规划：协调器不能替代约束检查

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合观察一个前后端完整度更高的多 Agent 应用。它涉及航班、住宿、餐饮、预算、目的地和行程六类成员，建议作为进阶阅读，不作为首个运行项目。

## 架构

> 流程：Next.js表单 → FastAPI → 协调Team → 六类成员 → 行程与预算草稿 → 约束核对

## 关键代码与机制

backend/agents/team.py 创建 mode="coordinate" 的 Team，members 包含目的地、酒店、餐饮、预算、航班与行程成员。itinerary.py 定义行程 Agent；文件 travel_planning_team.py 只是航班库调用相关片段，不能把它视为全应用启动入口。

进一步核对 backend/main.py 后，确认它从 api.app 导入应用。backend/config/llm.py 的实际模型使用 OpenRouter，包含 Google与OpenAI路由名称；README概述为Gemini，配置细节应以代码为准。主脚本默认监听0.0.0.0，学习启动改用明确的127.0.0.1命令。

根案例目录没有 requirements.txt，后端依赖在 pyproject.toml 与 uv.lock；前端实际目录为 client，拥有 package.json、Prisma与环境示例。不要套用其他案例的 pip install -r requirements.txt 或把前端路径猜成 frontend。

旅行草稿中的营业时间、交通时间、价格与预算约束需另外验证。多个Agent都推荐了同一地点，不代表信息独立可靠，也不意味着完成了真实预订。

## 环境依赖

后端要求Python>=3.12，使用Agno、FastAPI、数据库与搜索/抓取组件；pyproject声明Agno>=2.3.24。client使用Next.js、React与Prisma。环境模板包括数据库、OpenRouter、搜索、抓取和存储相关变量，按启用路径配置。

<!-- pagebreak -->

# 实验卡12 多 Agent 旅行规划

## 复现步骤

先在 backend 按固定 uv.lock 建立环境并配置 .env，然后仅绑定本机启动API：
```bash
uv sync --frozen
uv run uvicorn api.app:app --host 127.0.0.1 --port 8000
```
再进入 client，按README安装包、配置 .env.local，并针对新建教学数据库初始化Prisma，最后启动网页开发服务。不得对已有业务库运行初始化命令。
```bash
pnpm install
pnpm prisma generate
pnpm prisma db push
pnpm dev
```
以上是依据源码整理的复现路线，未运行，服务间地址与凭据仍需逐项核对。

## 结果与故障核对

先验收API健康与表单数据流，再测试日期、每日时间、费用合计、交通可行性与来源时效。预订结果必须有对应交易证据；行程文本不能冒充已预订。

## 扩展练习

为两日旅行草稿增加确定性检查：日期是否连续、同一天是否冲突、总费用是否超预算。

## 参考答案

日期按明确时区排序；用时间区间检查重叠并保留交通缓冲；分项价格统一货币再求和与预算比较。缺失价格写明未知，不按零计算。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/README.md)

- [team.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/backend/agents/team.py) | Git blob：37326dc268b786585f48e227e94cd6f7638ddb07
- [itinerary.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/backend/agents/itinerary.py) | Git blob：5d2b5075fc675af907f98801be63d38d00d63af2
- [travel_planning_team.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/agent_teams/ai_travel_planner_agent_team/backend/travel_planning_team.py) | Git blob：d02a95ec0ef67ef1ce007f1845bb45db4bbe6753

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
