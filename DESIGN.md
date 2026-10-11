---
name: "学有据"
description: "简洁聊天工作区"
colors:
  surface: "#fff"
  rail: "#f7f7f8"
  ink: "#202124"
  muted: "#61656b"
  line: "#e4e6e9"
  accent: "#2860c8"
  accent-dark: "#1c4da8"
  accent-soft: "#eef3fc"
  hover: "#ededf0"
  navigation-active: "#e9eaed"
  field-line: "#cdd1d7"
  quote-ink: "#4e535b"
  warning: "#805323"
  error: "#a62c35"
  error-bg: "#fdf0f1"
  delete-hover: "#fcebee"
  selection-bg: "#dbe7fc"
  selection-ink: "#1b3764"
  scrollbar: "#b5b8bf"
typography:
  headline:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.015em"
  title:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.6
  dialog-title:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.4
  section-title:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.5
  library-title:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.6
  body:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.9
  quote:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.9
  input:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.7
  button:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "14px"
    fontWeight: 500
  label:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "14px"
    fontWeight: 500
  action:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "13px"
    fontWeight: 400
  metadata:
    fontFamily: '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.8
rounded:
  control: "6px"
  editor: "10px"
  dialog: "12px"
spacing:
  "4": "4px"
  "6": "6px"
  "8": "8px"
  "10": "10px"
  "12": "12px"
  "14": "14px"
  "16": "16px"
  "18": "18px"
  "20": "20px"
  "24": "24px"
  "28": "28px"
  "32": "32px"
  "36": "36px"
  "40": "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-dark}"
  button-new:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  button-account:
    textColor: "{colors.muted}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  button-account-main:
    textColor: "{colors.ink}"
  button-text:
    textColor: "{colors.muted}"
    typography: "{typography.action}"
    padding: "8px 0"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "{spacing.12}"
  navigation:
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  navigation-active:
    backgroundColor: "{colors.navigation-active}"
    textColor: "{colors.ink}"
  prompt-link:
    textColor: "{colors.muted}"
    typography: "{typography.action}"
    padding: "8px 0"
  material-row:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 10px"
  material-row-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-dark}"
  question-editor:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.editor}"
    padding: "18px 18px 12px"
  evidence-reference:
    textColor: "{colors.accent}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: "0 5px"
  evidence-source:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.quote-ink}"
    typography: "{typography.quote}"
    rounded: "{rounded.control}"
    padding: "{spacing.16}"
  notice:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  notice-error:
    backgroundColor: "{colors.error-bg}"
    textColor: "{colors.error}"
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.dialog}"
    padding: "{spacing.28}"
---

# Design System: 学有据

## Overview

**Creative North Star: "简洁聊天工作区"**

“简洁聊天工作区”来自用户确认的白色、常规、熟悉通用的聊天工具偏好。白色内容面、中性灰辅助面与单一蓝色强调支持反复提问和阅读中文教材；说明保持简短，来源、状态与错误恢复仍清晰可见。

系统保留“学有据”品牌、本机中文无衬线字体、细边框与温和圆角。正文以阅读宽度和行距建立层级，资料以紧凑行呈现。本文按当前 HTML、CSS 与 JavaScript 记录可复用规则；提问优先、同一表单转为底部输入区的首页构图留在对应 surface contract，不作为未来所有路由的模板。

**Key Characteristics:**

- 白色内容面与中性灰辅助面。
- 蓝色标识操作、链接、选中与键盘焦点。
- 小标题、可读正文、紧凑资料行与简短说明。
- 原生控件、线描 SVG 与平面分层。

## Colors

白色与中性灰占据主要面积，操作蓝承接明确动作；frontmatter 是已提取颜色值的规范来源。

### Primary

- **操作蓝（accent）：** 提问按钮、链接、品牌书本图标、光标及键盘轮廓。
- **深蓝（accent-dark）：** 主按钮悬停、单集合范围与已选资料行文字。
- **浅蓝（accent-soft）：** 已选范围、已选资料行及引用编号悬停的底色。

### Neutral

- **白色（surface）：** 主工作区、编辑器、次级按钮和对话框。
- **辅助灰（rail）：** 侧栏、原生下拉框、原文摘录、一般提示和普通资料行悬停。
- **正文深灰（ink）与说明灰（muted）：** 标题和正文、元信息和次要动作。
- **分隔灰（line）与字段边线（field-line）：** 区域分隔、对话框边界、编辑器和字段边界。
- **交互灰（hover）与当前导航灰（navigation-active）：** 导航及历史悬停、当前导航项。
- **原文灰（quote-ink）：** 摘录与展开的证据正文。
- **滚动条灰（scrollbar）：** 窄滚动条；选中文字使用 selection-bg 与 selection-ink。

warning 表示缺失信息与未匹配资料；error、error-bg 表示失败提示，delete-hover 只用于删除历史的悬停反馈。这些是功能状态，不构成第二套品牌强调色。新讨论的默认边线（#d4d7dc）与悬停边线（#afb4bd）、例题下划线（#c5c8cf）为局部组件值，不扩展为通用调色板。

**The 单一强调色 Rule.** 蓝色服务操作、链接、选中和焦点；警告与错误色只服务对应状态。

## Typography

所有角色共用 frontmatter 中的本机无衬线字体栈，无远程字体、独立展示字体或等宽正文。字号来自实际中文阅读与控件密度，不推导等比字体尺度。

### Hierarchy

- **Headline：** 提问区任务标题；整个窄屏范围保留同一字号和字重。
- **Title：** 每轮问题标题，移动端局部缩为 19px；最大行长（70ch）。
- **Dialog title：** 账户、资料目录与管理概览标题。
- **Section title / Library title：** 教材区标题与目录分组；移动端分别为 14px 与 15px。
- **Body：** 讲解正文；最大行长（70ch），长中文和资料路径自然换行。
- **Quote：** 引文、展开的原文及失败状态；原文保留换行，代码证据沿用系统字体。
- **Input：** 主问题输入使用 input 行高，其他对话框字段保持 16px，未另设行高。
- **Button / Label / Action / Metadata：** 主次操作、字段标签、文字动作及来源、字数、配额。计数使用等宽数字。

品牌在桌面为 21px、字重 600，移动端为 20px。导航为 14px，移动端为 13px；结果分组为 14px、字重 600；管理汇总数值为 18px、字重 500。正文不会因窄屏而缩小。

**The 阅读优先 Rule.** 讲解正文与输入保持 16px；用间距、行高和字重建立层级，不用大号展示字压过学习任务。

## Layout

当前首页在桌面使用固定侧栏（232px）与居中内容区（最大 800px），主区左右留白（32px），顶栏最小高度（72px）。空讨论内容上下内边距为 52px / 44px；资料区和问题表单分别组织成单列，五个集合按紧凑行显示。该构图属于当前 surface，不是所有未来页面的固定模板。

1100px 及以下，侧栏收为 208px、主区和底部输入区左右留白为 28px；工具栏换行，两个原生 select 共同占满一行，字数与提问按钮在下一行。760px 及以下，侧栏变成顶部品牌、导航和可展开历史，主区左右留白为 20px；顶栏最小高度为 60px，内容顶部留白为 28px。历史列表最大高度为 220px。350px 及以下，主区与顶部导航左右留白为 16px。页面最小宽度为 280px。

有结果后，同一个表单固定于讨论底部，桌面保持侧栏偏移；表单与短说明仍以 800px 对齐。ResizeObserver 将输入区实际高度写入 --composer-height，阅读区底部留白为测量高度加 32px；证据定位及页面滚动也避开输入区。源代码的 220px 只是初始回退值，不是固定的输入区高度。移动端底部内边距包含 safe-area-inset-bottom。

间距使用 frontmatter 中的实际步长；讨论间使用 36px 间隔与细分隔线。主要按钮、导航、编号引用与 summary 的最小高度为 44px；对话框字段最小高度为 46px。桌面历史删除按钮为 36×44px，移动端为 44×44px，不把桌面尺寸推广为主要触控目标。

## Elevation & Depth

界面使用平面分层，源码未定义 box-shadow。白色内容面、中性灰辅助面、细边线和浅蓝选中底色承担分组；固定输入区用顶部细线与白底划定边界。对话框使用正文深灰的半透明遮罩（#20212466），没有装饰投影。

**The 平面分层 Rule.** 用背景色与细边框区分区域，不为普通容器添加投影。

## Shapes

control 圆角用于按钮、导航、资料行、字段、提示及原文容器；editor 用于主问题容器；dialog 用于对话框。例题是透明、带下划线的文字动作，不使用胶囊外形；资料行不形成边框卡片网格。边界以 1px 实线为主。图标使用作者编写的线描 SVG，常规尺寸为 19px、笔画为 1.7，品牌及局部功能按实际组件尺寸调整。

## Components

### Buttons

主操作为操作蓝底白字，control 圆角，悬停转深蓝；新讨论为白底局部灰边线，只在悬停时加强边界。账户和目录动作使用透明底，账户主入口为深灰文字，次要操作为说明灰。例题使用有下划线的透明文字按钮，悬停使文字与下划线转蓝。

禁用按钮透明度为 0.6，默认使用 not-allowed；提问按钮等待时使用 wait，并切换为“生成中”或“检索中”。字段、范围和模式在处理期间保持不可修改，状态提示位于输入区。

按钮、链接、字段、下拉框和 summary 的 focus-visible 使用操作蓝外轮廓（2px）、偏移（3px）。主 textarea 的轮廓同为 2px，偏移为 2px；容器同时将边线转蓝。链接下划线偏移为 3px，例题为 4px。

### Cards / Containers

系统保留容器边界，但资料和管理员汇总使用行。资料行透明、无边线、control 圆角；桌面最小高度为 54px，名称与篇数同行，窄屏最小高度为 66px，名称与篇数上下排列。已选行使用浅蓝底、深蓝文字与“已选”，并同步 aria-pressed 与范围 select。课程重复点击恢复全部范围；案例行打开案例目录并选中案例范围。

一般提示为辅助灰底、control 圆角；失败提示使用错误色与 error-bg。对话框为白底、line 边界、dialog 圆角，宽度分别限制在 420px（账户）、820px（目录）、580px（管理），同时避开视口边缘 16px，最大高度为视口高度减 32px。目录关闭按钮保持可见，列表通过细线分行；管理汇总也是标签与数值对齐的行。

### Inputs / Fields

问题编辑器使用 field-line 边线、editor 圆角与白底；textarea 自身无边线，文本光标为操作蓝。空讨论 textarea 最小高度为 96px、最大高度为 240px，移动端最小为 88px；允许垂直调整。讨论底部状态为 68px 高，最大为 min(160px, 24dvh)，移动端高为 58px。这些是同一个字段的状态尺寸。

普通对话框字段为 field-line 边线、control 圆角与 12px 内边距。原生 select 为辅助灰底、透明边线，悬停使用交互灰；单集合范围变为浅蓝底与深蓝文字。范围、资料行和模式仍保留原生语义。

新讨论、导航、账户、资料行、主按钮和文字按钮只对背景、文字及边线做 160ms ease-out 反馈；没有入场、位移或自动滚动动画。prefers-reduced-motion 下关闭全部 transition 与 animation。未定义的字段悬停、平滑滚动或阴影不得补作既有规则。

### Navigation

桌面导航置于中性灰侧栏，默认说明灰，当前项为当前导航灰底、深灰文字与字重 600；悬停为交互灰底、深灰文字。历史标题可截断，删除按钮独立，悬停为 delete-hover 底与错误色图标。移动端导航取消底色，当前项仍用字重和文字颜色表达；历史通过带 aria-expanded 的入口展开。

### Evidence

每轮问题和回答独立成组，答案正文旁的蓝色编号对应本轮原生 details。编号点击展开对应原文，将 summary 按顶部对齐滚入视口并转移焦点，编号通过 aria-controls 关联本轮目标。引用不跨轮跳转，阅读位置避开固定输入区。

摘录使用辅助灰底、原文灰与 quote 行高；展开的原文可滚动，最大高度为 390px，保留章节、语言和原文位置链接。结果状态是说明灰文字，不使用彩色胶囊。检索未命中、模型失败和引文检查失败保留必要说明；“引用已核对”只说明引文位置核对，不表示答案正确。

## Do's and Don'ts

### Do:

- Do 延续白色聊天工作区、中性灰辅助面、本机中文字体与实际圆角层级。
- Do 让资料行、范围 select 与“已选”文字同步表达同一个状态。
- Do 保留清晰的键盘轮廓、逐轮原文入口和必要的失败说明。
- Do 用实际测量的底部输入区高度保护阅读及证据定位空间。
- Do 把首页提问优先的构图留在 surface contract，未来路由按其任务组织布局。

### Don't:

- Don't 恢复用户已拒绝的暖纸色阅读室材质或衬线展示方向。
- Don't 给学习工作区添加营销口号、重复标签、胶囊动作或资料卡片网格。
- Don't 用渐变、装饰投影、插画或入场动画取代内容层级。
- Don't 引入远程字体或图标字体；延续本机字体和线描 SVG。
- Don't 把引用核对状态表达成答案正确，或把未检查的依据包装成已验证结论。
