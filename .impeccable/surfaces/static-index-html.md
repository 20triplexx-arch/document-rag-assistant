---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: ["static/style.css","static/app.js"]
---

# 学习首页

Mode: Operate. Scope: `/`, static/index.html, static/style.css, static/app.js.

用户在明亮室内反复阅读中文教材。白色界面、中性灰侧栏和已有蓝色强调服务输入与原文核查。现有多人功能、self-only CSP、接口、语料与限额保持不变。

## Direction contract

THESIS: 一个表单从空讨论的直接提问切换为讨论底部输入区，阅读空间由回答与本轮依据占据；去掉大号欢迎标题、胶囊按钮和成排教材卡片。

OWN-WORLD: 白色工作区、中性灰辅助面、深灰文字与单一蓝色操作、链接、焦点；系统中文字体、6px 控件/10px 编辑器圆角、细边框、紧凑资料行，无渐变、插画或入场动画。

STORY: 选择资料范围并提问，阅读讲解，点击编号定位这一轮的原文证据，再继续提问；案例可匿名浏览，账户与私有历史仍在熟悉的位置。

FIRST VIEWPORT: 桌面 232px 侧栏、800px 最大阅读宽度、26px 小标题、16px 正文；空讨论直接显示表单，五个集合按行显示篇数与选中状态。有回答后同一表单固定底部，引用编号按轮定位 details。760px 以下顶部导航与可展开历史，资料纵排；仅 160ms 颜色反馈，减少动画偏好下关闭。

FORM: 用户批准白色聊天工作区的实现计划，code-led，无批准图片；延续用户选定 standing canon，覆盖历史 seed 37c90e4e 的 assigned #5。签名交互为单表单的讨论状态切换与逐轮引用定位。

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

所有页面图片资产均不需要；截图是 QA 证据，不作为页面资源。2026-10-11 已完成实现、四种宽度检查、独立 finish reviewer 和 documenter；最终 verdict 为 ship，两项修正均 resolved。实际验证与隔离预览见 docs/ui-redesign-2026-10-11.md，设计规范和配套 sidecar 已更新。
