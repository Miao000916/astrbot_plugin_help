# astrbot_plugin_help

增强版 `/help` 插件，接管 AstrBot 内置的帮助指令。

**核心定位：展示 bot 可用的指令，即用户可手动触发的功能。** 后台运行、无用户指令的功能增强型插件默认不出现在帮助中（可在配置中调整）。

## 功能

- `/help`（别名：`/帮助`、`/菜单`）：列出所有已安装的第三方插件及一句话功能简介
- `/help <插件名>`：查看该插件的详细指令说明

插件名支持模糊匹配：`/help setu`、`/help astrbot_plugin_setu`、`/help astrbot-plugin-setu` 等价（自动忽略大小写、`astrbot_plugin_`/`astrbot-plugin-` 前缀、`-` 与 `_` 差异）。

## 配置项（WebUI 插件页可改）

| 配置 | 说明 | 默认值 |
| ---- | ---- | ------ |
| `hidden_plugins` | 在 `/help` 中隐藏的插件名列表（归一化匹配） | `livingmemory`、`self_learning`、`meme_manager` |
| `detail_source` | 详情页数据源：`md_first`（内置文档优先，注册表兜底）/ `dynamic_only`（只读指令注册表）/ `desc_only`（只显示插件简介） | `md_first` |
| `display_mode` | 发送方式：`auto`（按估算长度自动选择）/ `plain`（总是纯文本，过长分段）/ `forward`（总是合并转发，仅 QQ） | `auto` |
| `plugin_aliases` | 插件别名，格式 `插件名=别名`。/help 列表显示别名，/help <别名> 可查。解决插件名过长、含符号不好输入的问题 | 预填 6 个插件的短别名 |
| `plugin_desc_overrides` | 自定义插件简介，格式 `插件名=简介`，覆盖自动读取的过长描述 | 预填 jmdownloader 的精简简介 |

注：合并转发模式下不带独立的标题消息（标题节点会被平台单独发成一条合并转发，造成两条转发的冗余）。

## 数据源

详情内容按两级来源获取（`md_first` 模式下）：

1. **主**：插件目录 `help_data/<归一化插件名>.txt` —— 手工维护的纯文本指令说明（本地目录，不入库）
2. **兜底**：无对应 txt 文件时，从 AstrBot 指令注册表动态读取（依赖内部 API `astrbot.core.star.command_management`，与 WebUI「指令管理」页同源，失败时降级提示不崩溃）

## 展示形式

- 纯文本输出（QQ 不渲染 markdown，help_data 均为纯文本格式）
- 按显示宽度估算实际行数（全角字符计 2，约 34 半角/行）：估算 ≤ 20 行直接发送，超过则 QQ 平台自动转合并转发消息，其他平台分段发送

## 覆盖内置 /help 的说明

本插件注册同名 `help` 指令。AstrBot 的指令分发机制是「所有匹配的 handler 依次执行，后执行者的结果覆盖先执行者」，内置插件先于第三方插件加载，因此本插件的输出会覆盖内置 `/help`（内置版只显示 AstrBot 版本号和内置指令，对第三方插件无用）。

## 维护 help_data

`help_data/` 是**本地维护的数据目录，已加入 .gitignore，不随仓库发布**（其中内容按各自部署环境定制）。插件加载时若目录不存在只记一条 warning，不影响运行，详情页自动走动态兜底。

部署/使用时在插件目录下自建 `help_data/`，添加 `<归一化插件名>.txt` 即可在 `/help <插件名>` 中展示。归一化规则：小写、去 `astrbot_plugin_`/`astrbot-plugin-` 前缀、`-` 替换为 `_`。

格式建议一行一条指令：`/指令 <参数> —— 说明（例: 用法示例）`，不要用 markdown 表格（QQ 客户端按屏宽换行，全半角混排对不齐）。

## 相关链接

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
