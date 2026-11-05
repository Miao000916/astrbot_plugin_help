from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Node, Plain
from astrbot.api.star import Context, Star

# 兜底数据源：AstrBot 内部指令注册表（非公开 API，导入失败时降级，不影响主功能）
try:
    from astrbot.core.star.command_management import list_commands
except Exception:  # noqa: BLE001
    list_commands = None

HELP_DIR = Path(__file__).parent / "help_data"
PLAIN_MAX_LINES = 20  # 超过此行数改用合并转发（参照 azurlane_assistant 的模式）
NODE_CHUNK_LINES = 50  # 合并转发每个节点的行数
PLUGIN_PREFIXES = ("astrbot_plugin_", "astrbot-plugin-")


def _normalize(name: str) -> str:
    """归一化插件名：小写、去掉 astrbot 插件前缀、- 与 _ 统一。

    使「astrbot-plugin-jmdownloader」「astrbot_plugin_jmdownloader」
    「jmdownloader」视为同一名字。
    """
    n = name.strip().lower()
    for prefix in PLUGIN_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix) :]
            break
    return n.replace("-", "_")


class HelpPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件加载后检查帮助文档目录，日志记录加载到的文档数量。"""
        if HELP_DIR.is_dir():
            docs = sorted(p.stem for p in HELP_DIR.glob("*.md"))
            logger.info(f"[help] 已加载 {len(docs)} 份插件帮助文档: {docs}")
        else:
            logger.warning(f"[help] 帮助文档目录不存在: {HELP_DIR}")

    @filter.command("help", alias={"帮助", "菜单"})
    async def help(self, event: AstrMessageEvent, plugin_name: str = ""):
        """查看插件帮助菜单"""
        plugin_name = plugin_name.strip()
        if plugin_name:
            async for result in self._plugin_detail(event, plugin_name):
                yield result
        else:
            async for result in self._overview(event):
                yield result

    async def _overview(self, event: AstrMessageEvent):
        """列出所有已装第三方插件及一句话简介。"""
        stars = [
            md
            for md in self.context.get_all_stars()
            if not md.reserved and md.activated
        ]
        stars.sort(key=lambda md: (md.name or "").lower())

        lines = []
        for md in stars:
            display = md.display_name or md.name or "未知插件"
            desc = md.desc or md.short_desc or "（暂无简介）"
            lines.append(f"▪ {display}：{desc}")
        lines.append("")
        lines.append("发送 /help <插件名> 查看该插件的详细指令")

        async for result in self._reply(event, f"📖 已安装插件（{len(stars)} 个）", lines):
            yield result

    async def _plugin_detail(self, event: AstrMessageEvent, plugin_name: str):
        """输出单个插件的详细指令说明。"""
        target = _normalize(plugin_name)
        match = None
        for md in self.context.get_all_stars():
            if md.reserved or not md.activated:
                continue
            candidates = {md.name or "", md.display_name or ""}
            if any(_normalize(c) == target for c in candidates if c):
                match = md
                break

        if not match:
            available = sorted(
                md.display_name or md.name or "未知插件"
                for md in self.context.get_all_stars()
                if not md.reserved and md.activated
            )
            text = f"未找到插件「{plugin_name}」。\n可用插件：\n" + "\n".join(available)
            yield event.plain_result(text).use_t2i(False)
            return

        name = match.name or "未知"
        display = match.display_name or name
        header = [
            f"📦 {display}（{name}）",
            f"版本: {match.version or '未知'}  作者: {match.author or '未知'}",
        ]
        if match.repo:
            header.append(f"仓库: {match.repo}")

        md_file = HELP_DIR / f"{_normalize(name)}.md"
        if md_file.is_file():
            body = md_file.read_text(encoding="utf-8").strip()
            lines = header + [""] + body.splitlines()
        else:
            lines = header + [
                "",
                "（该插件暂无维护的详细说明，以下为自动读取的指令列表）",
                "",
            ]
            lines += await self._dynamic_commands(name)

        async for result in self._reply(event, header[0], lines):
            yield result

    async def _dynamic_commands(self, plugin_name: str) -> list[str]:
        """兜底：从 AstrBot 指令注册表动态读取该插件的指令列表。"""
        if list_commands is None:
            return ["（无法读取指令注册表：AstrBot 内部 API 不可用）"]
        try:
            commands = await list_commands()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[help] 读取指令注册表失败: {e}")
            return ["（读取指令注册表失败，请查看日志）"]

        lines = []
        for item in commands:
            if item.get("plugin") != plugin_name or not item.get("enabled", True):
                continue
            cmd = item.get("effective_command") or item.get("original_command") or ""
            if not cmd:
                continue
            desc = item.get("description") or ""
            aliases = item.get("aliases") or []
            alias_text = f"（别名: {'、'.join(aliases)}）" if aliases else ""
            lines.append(f"/{cmd}{alias_text}" + (f" - {desc}" if desc else ""))
            for sub in item.get("sub_commands") or []:
                if not sub.get("enabled", True):
                    continue
                sub_cmd = sub.get("effective_command") or ""
                sub_desc = sub.get("description") or ""
                if sub_cmd:
                    lines.append(f"  /{sub_cmd}" + (f" - {sub_desc}" if sub_desc else ""))

        if not lines:
            lines.append("（该插件没有注册指令，可能通过关键词或消息监听触发）")
        return lines

    async def _reply(self, event: AstrMessageEvent, title: str, lines: list[str]):
        """统一发送：短文本直接发，长文本在 QQ 平台转合并转发，其他平台分段发。"""
        if len(lines) <= PLAIN_MAX_LINES:
            yield event.chain_result(
                [Plain(title + "\n" + "\n".join(lines))]
            ).use_t2i(False)
            return

        if event.get_platform_name() != "aiocqhttp":
            # 非 QQ 平台不支持合并转发，分段发纯文本
            for i in range(0, len(lines), NODE_CHUNK_LINES):
                chunk = "\n".join(lines[i : i + NODE_CHUNK_LINES])
                text = f"{title}\n{chunk}" if i == 0 else chunk
                yield event.chain_result([Plain(text)]).use_t2i(False)
            return

        self_id = event.get_self_id()
        nodes = [Node(uin=self_id, name="帮助菜单", content=[Plain(title)])]
        for i in range(0, len(lines), NODE_CHUNK_LINES):
            nodes.append(
                Node(
                    uin=self_id,
                    name="帮助详情",
                    content=[Plain("\n".join(lines[i : i + NODE_CHUNK_LINES]))],
                )
            )
        yield event.chain_result(nodes)

    async def terminate(self):
        """插件卸载/停用时调用，本插件无需清理资源。"""
