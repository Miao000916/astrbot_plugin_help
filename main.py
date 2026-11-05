import math
import unicodedata
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Node, Plain
from astrbot.api.star import Context, Star

# 兜底数据源：AstrBot 内部指令注册表（非公开 API，导入失败时降级，不影响主功能）
try:
    from astrbot.core.star.command_management import list_commands
except Exception:  # noqa: BLE001
    list_commands = None

HELP_DIR = Path(__file__).parent / "help_data"
WRAP_WIDTH = 34  # QQ 客户端约 17 汉字/行，折合 34 半角单位
FORWARD_LINES = 20  # auto 模式下估算显示行数超过此值改用合并转发
NODE_CHUNK_LINES = 50  # 长消息分段/合并转发每个节点的行数
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


def _display_width(text: str) -> int:
    """估算字符串在 QQ 客户端的显示宽度：全角字符计 2，其余计 1。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _estimate_lines(lines: list[str]) -> int:
    """按显示宽度估算消息在客户端的实际行数（客户端按屏宽自动换行）。"""
    return sum(max(1, math.ceil(_display_width(line) / WRAP_WIDTH)) for line in lines)


def _parse_kv_list(raw: list | None) -> dict[str, str]:
    """把 ["插件名=值", ...] 形式的配置解析为 归一化插件名 -> 值 的字典。"""
    result = {}
    for item in raw or []:
        if "=" in str(item):
            key, value = str(item).split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value:
                result[_normalize(key)] = value
    return result


class HelpPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self):
        """插件加载后检查帮助文档目录，日志记录加载到的文档数量。"""
        if HELP_DIR.is_dir():
            docs = sorted(p.stem for p in HELP_DIR.glob("*.txt"))
            logger.info(f"[help] 已加载 {len(docs)} 份插件帮助文档: {docs}")
        else:
            logger.warning(f"[help] 帮助文档目录不存在: {HELP_DIR}")

    def _hidden(self) -> set[str]:
        """配置中被隐藏的插件名集合（归一化后）。"""
        return {_normalize(x) for x in self.config.get("hidden_plugins", [])}

    def _aliases(self) -> dict[str, str]:
        """配置的插件别名：归一化插件名 -> 别名。"""
        return _parse_kv_list(self.config.get("plugin_aliases", []))

    def _desc_overrides(self) -> dict[str, str]:
        """配置的自定义简介：归一化插件名 -> 简介。"""
        return _parse_kv_list(self.config.get("plugin_desc_overrides", []))

    def _name_of(self, md) -> str:
        """插件的展示名：优先别名，其次 display_name，最后插件名。"""
        alias = self._aliases().get(_normalize(md.name or ""))
        return alias or md.display_name or md.name or "未知插件"

    def _desc_of(self, md) -> str:
        """插件的简介：优先自定义覆盖，其次 metadata 的 desc/short_desc。"""
        override = self._desc_overrides().get(_normalize(md.name or ""))
        return override or md.desc or md.short_desc or "（暂无简介）"

    def _visible_stars(self) -> list:
        """所有应在帮助中展示的插件：非内置、已激活、未被隐藏。"""
        hidden = self._hidden()
        return [
            md
            for md in self.context.get_all_stars()
            if not md.reserved
            and md.activated
            and _normalize(md.name or "") not in hidden
        ]

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
        stars = sorted(self._visible_stars(), key=lambda md: (md.name or "").lower())

        lines = []
        for md in stars:
            lines.append(f"▪ {self._name_of(md)}")
            lines.append(f"  {self._desc_of(md)}")
        lines.append("")
        lines.append("发送 /help <插件名> 查看该插件的详细指令")

        async for result in self._reply(
            event, f"📖 已安装插件（{len(stars)} 个）", lines
        ):
            yield result

    async def _plugin_detail(self, event: AstrMessageEvent, plugin_name: str):
        """输出单个插件的详细指令说明，直奔内容，不带头部信息。"""
        target = _normalize(plugin_name)

        if target in self._hidden():
            yield event.plain_result(
                f"插件「{plugin_name}」已被设置为隐藏。"
            ).use_t2i(False)
            return

        aliases = self._aliases()
        match = None
        for md in self._visible_stars():
            key = _normalize(md.name or "")
            candidates = {md.name or "", md.display_name or ""}
            if key in aliases:
                candidates.add(aliases[key])
            if any(_normalize(c) == target for c in candidates if c):
                match = md
                break

        if not match:
            available = sorted(self._name_of(md) for md in self._visible_stars())
            text = f"未找到插件「{plugin_name}」。\n可用插件：\n" + "\n".join(available)
            yield event.plain_result(text).use_t2i(False)
            return

        source = self.config.get("detail_source", "md_first")
        name = match.name or ""

        if source == "desc_only":
            lines = [self._desc_of(match)]
        elif source == "dynamic_only":
            lines = await self._dynamic_commands(name)
        else:  # md_first：内置文档优先，缺失时动态读取
            doc_file = HELP_DIR / f"{_normalize(name)}.txt"
            if doc_file.is_file():
                lines = doc_file.read_text(encoding="utf-8").strip().splitlines()
            else:
                lines = ["（该插件暂无维护的详细说明，以下为自动读取的指令列表）", ""]
                lines += await self._dynamic_commands(name)

        async for result in self._reply(event, f"📦 {self._name_of(match)}", lines):
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
        """统一发送。display_mode: auto=按估算行数自动选择；plain=直接回复；forward=合并转发（仅 QQ）。

        合并转发不带独立标题节点（标题节点会被平台单独发成一条合并转发，冗余）。
        """
        mode = self.config.get("display_mode", "auto")
        use_forward = mode == "forward" or (
            mode == "auto" and _estimate_lines([title] + lines) > FORWARD_LINES
        )
        if event.get_platform_name() != "aiocqhttp":
            # 非 QQ 平台不支持合并转发，降级为分段纯文本
            use_forward = False

        if not use_forward:
            for i in range(0, len(lines), NODE_CHUNK_LINES):
                chunk = "\n".join(lines[i : i + NODE_CHUNK_LINES])
                text = f"{title}\n{chunk}" if i == 0 else chunk
                yield event.chain_result([Plain(text)]).use_t2i(False)
            return

        self_id = event.get_self_id()
        nodes = []
        for i in range(0, len(lines), NODE_CHUNK_LINES):
            nodes.append(
                Node(
                    uin=self_id,
                    name="帮助菜单",
                    content=[Plain("\n".join(lines[i : i + NODE_CHUNK_LINES]))],
                )
            )
        yield event.chain_result(nodes)

    async def terminate(self):
        """插件卸载/停用时调用，本插件无需清理资源。"""
