# astrbot_plugin_help

增强版 `/help` 插件，接管 AstrBot 内置的帮助指令。

## 功能

- `/help`（别名：`/帮助`、`/菜单`）：列出所有已安装的第三方插件及一句话功能简介
- `/help <插件名>`：查看该插件的详细指令说明

插件名支持模糊匹配：`/help setu`、`/help astrbot_plugin_setu`、`/help astrbot-plugin-setu` 等价（自动忽略大小写、`astrbot_plugin_`/`astrbot-plugin-` 前缀、`-` 与 `_` 差异）。

## 数据源

详情内容按两级来源获取：

1. **主**：插件目录 `help_data/<插件名>.md` —— 手工维护的高质量说明，随插件分发
2. **兜底**：无对应 md 文件时，从 AstrBot 指令注册表动态读取（依赖内部 API `astrbot.core.star.command_management`，失败时降级为仅显示插件元数据）

## 展示形式

- 内容 ≤ 20 行：纯文本直接发送
- 内容更长：QQ（aiocqhttp）平台自动转合并转发消息，防刷屏；其他平台分段发送纯文本

## 覆盖内置 /help 的说明

本插件注册同名 `help` 指令。AstrBot 的指令分发机制是"所有匹配的 handler 依次执行，后执行者的结果覆盖先执行者"，内置插件先于第三方插件加载，因此本插件的输出会覆盖内置 `/help`（内置版只显示 AstrBot 版本号和内置指令，对第三方插件无用）。

## 维护 help_data

新增插件后，在 `help_data/` 下添加 `<归一化插件名>.md` 即可在 `/help <插件名>` 中展示。归一化规则：小写、去 `astrbot_plugin_`/`astrbot-plugin-` 前缀、`-` 替换为 `_`。

## 相关链接

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
