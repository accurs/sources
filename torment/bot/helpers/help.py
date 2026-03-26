from __future__ import annotations

import inspect
import os
from typing import Any

import discord
from discord.ext import commands

from bot.helpers.context import TormentContext

ACCENT_COLOR = 3618621
PLACEHOLDER_DESCRIPTIONS = {"no description", "no description given"}

EXAMPLES: dict[str, str] = {
    "ping": "ping",
    "setup": "setup",
    "setup view": "setup view",
    "setup modlog": "setup modlog #mod-actions",
    "setup muted": "setup muted @Muted",
    "setup imuted": "setup imuted @Image Muted",
    "setup rmuted": "setup rmuted @Reaction Muted",
    "warn": "warn @offermillions being annoying in chat",
    "warnings": "warnings @offermillions",
    "cases": "cases @offermillions",
    "case": "case 42",
    "reason": "reason 42 actually they were raiding",
    "kick": "kick @offermillions won't stop posting links",
    "ban": "ban @offermillions alt account detected",
    "hardban": "hardban 123456789012345678 known ban evader",
    "unban": "unban 123456789012345678 served their time",
    "nickname": "nickname @offermillions something appropriate",
    "forcenickname": "forcenickname @offermillions definitely appropriate",
    "forcenickname remove": "forcenickname remove @offermillions",
    "forcenickname list": "forcenickname list",
    "forcenickname sync": "forcenickname sync @offermillions",
    "lock": "lock #general dealing with raid",
    "lock category": "lock category 123456789012345678 server under attack",
    "unlock": "unlock #general raid over",
    "unlock category": "unlock category 123456789012345678 all clear",
    "hide": "hide #staff-chat @everyone",
    "hide category": "hide category 123456789012345678 @Members",
    "reveal": "reveal #announcements @everyone",
    "reveal category": "reveal category 123456789012345678 @Members",
    "mute": "mute @offermillions won't stop arguing",
    "unmute": "unmute @offermillions learned their lesson",
    "imute": "imute @offermillions posting nsfw content",
    "iunmute": "iunmute @offermillions behaving now",
    "rmute": "rmute @offermillions abusing reactions",
    "runmute": "runmute @offermillions stopped spamming",
    "purge": "purge 50",
    "purge user": "purge user @spammer 100",
    "purge bots": "purge bots 50",
    "purge files": "purge files 30",
    "purge embeds": "purge embeds 20",
    "purge links": "purge links 40",
    "purge invites": "purge invites 100",
    "purge mentions": "purge mentions 25",
    "purge contains": "purge contains spam 50",
    "purge startswith": "purge startswith ! 30",
    "purge endswith": "purge endswith ? 20",
    "purge reactions": "purge reactions 15",
    "purge humans": "purge humans 50",
    "customize": "customize",
    "customize avatar": "customize avatar https://i.imgur.com/example.png",
    "customize avatar remove": "customize avatar remove",
    "customize banner": "customize banner https://i.imgur.com/banner.png",
    "customize banner remove": "customize banner remove",
    "customize bio": "customize bio Your friendly neighborhood bot",
    "customize bio remove": "customize bio remove",
    "customize name": "customize name server manager",
    "customize name remove": "customize name remove",
    "customize view": "customize view",
    "customize reset": "customize reset",
    "prefix": "prefix",
    "prefix set": "prefix set !",
    "prefix add": "prefix add ?",
    "prefix remove": "prefix remove !",
    "prefix reset": "prefix reset",
    "welcome": "welcome",
    "welcome add": "welcome add #welcome Welcome @offermillions to the server!",
    "welcome remove": "welcome remove #welcome",
    "welcome list": "welcome list",
    "welcome test": "welcome test #welcome",
    "welcome clear": "welcome clear",
    "goodbye": "goodbye",
    "goodbye add": "goodbye add #goodbye Goodbye @offermillions, thanks for being here!",
    "goodbye remove": "goodbye remove #goodbye",
    "goodbye list": "goodbye list",
    "goodbye test": "goodbye test #goodbye",
    "goodbye clear": "goodbye clear",
    "boost": "boost",
    "boost add": "boost add #boosts Thanks for boosting @offermillions!",
    "boost remove": "boost remove #boosts",
    "boost list": "boost list",
    "boost test": "boost test #boosts",
    "boost clear": "boost clear",
    "avatar": "avatar @offermillions",
    "banner": "banner @offermillions",
    "userinfo": "userinfo @offermillions",
    "serverinfo": "serverinfo",
    "inviteinfo": "inviteinfo discord.gg/example",
    "hex": "hex @offermillions",
    "invite": "invite",
    "botinfo": "botinfo",
    "afk": "afk going to sleep",
    "urban": "urban yeet",
    "screenshot": "screenshot https://torment.lat",
    "shazam": "shazam",
    "createembed": "createembed {title: My Embed} {description: This is a test}",
    "pin": "pin",
    "unpin": "unpin",
    "snipe": "snipe",
    "snipe 2": "snipe 2",
    "editsnipe": "editsnipe",
    "editsnipe 3": "editsnipe 3",
    "reactionsnipe": "reactionsnipe",
    "reactionsnipe 2": "reactionsnipe 2",
    "clearsnipes": "clearsnipes",
    "giveaway": "giveaway",
    "giveaway start": "giveaway start #giveaways 1d Nitro Classic",
    "giveaway end": "giveaway end 123456789012345678",
    "giveaway reroll": "giveaway reroll 123456789012345678",
    "giveaway edit": "giveaway edit",
    "giveaway edit title": "giveaway edit title 123456789012345678 Discord Nitro",
    "giveaway edit prize": "giveaway edit prize 123456789012345678 Discord Nitro",
    "giveaway edit description": "giveaway edit description 123456789012345678 React with 🎉 to enter!",
    "giveaway add": "giveaway add",
    "giveaway add description": "giveaway add description 123456789012345678 React to enter!",
    "giveaway list": "giveaway list",
    "birthday": "birthday @offermillions",
    "birthday set": "birthday set January 15",
    "birthday list": "birthday list",
    "birthday role": "birthday role @Birthday",
    "birthday role remove": "birthday role remove",
    "birthday channel": "birthday channel #birthdays",
    "birthday channel remove": "birthday channel remove",
    "birthday message": "birthday message Happy birthday @offermillions!",
    "birthday message remove": "birthday message remove",
    "emoji": "emoji",
    "emoji steal": "emoji steal :custom_emoji:",
    "emoji addmany": "emoji addmany :emoji1: :emoji2: :emoji3:",
    "emoji removeduplicates": "emoji removeduplicates",
    "emoji remove": "emoji remove :custom_emoji:",
    "emoji rename": "emoji rename :old_name: new_name",
    "emoji add": "emoji add https://i.imgur.com/example.png cool_emoji",
    "emoji removemany": "emoji removemany :emoji1: :emoji2:",
    "emoji recolor": "emoji recolor #FF5733 :custom_emoji:",
    "reminder": "reminder 1h check the oven",
    "reminder cancel": "reminder cancel 5",
    "reminder list": "reminder list",
    "antiraid": "antiraid",
    "antiraid massjoin": "antiraid massjoin enable --do kick --threshold 10",
    "antiraid massjoin disable": "antiraid massjoin disable",
    "antiraid newaccounts": "antiraid newaccounts enable --do ban --threshold 7",
    "antiraid newaccounts disable": "antiraid newaccounts disable",
    "antiraid defaultavatar": "antiraid defaultavatar enable --do kick",
    "antiraid defaultavatar disable": "antiraid defaultavatar disable",
    "antiraid whitelist": "antiraid whitelist add @offermillions massjoin",
    "antiraid whitelist remove": "antiraid whitelist remove @offermillions massjoin",
    "antiraid whitelist list": "antiraid whitelist list massjoin",
    "fakepermissions": "fakepermissions",
    "fakepermissions add": "fakepermissions add @Moderator kick_members, ban_members",
    "fakepermissions remove": "fakepermissions remove @Moderator kick_members",
    "fakepermissions list": "fakepermissions list @Moderator",
    "fakepermissions reset": "fakepermissions reset",
    "autoresponder": "autoresponder",
    "autoresponder add": "autoresponder add hello, Hey there! --reply",
    "autoresponder remove": "autoresponder remove hello",
    "autoresponder list": "autoresponder list",
    "autoresponder exclusive": "autoresponder exclusive hello #general",
    "sticky": "sticky",
    "sticky add": "sticky add #announcements Remember to follow the rules!",
    "sticky existing": "sticky existing #announcements 123456789012345678",
    "sticky remove": "sticky remove #announcements",
    "sticky view": "sticky view #announcements",
    "sticky list": "sticky list",
    "command": "command",
    "command disable": "command disable #general warn",
    "command enable": "command enable #general warn",
    "command disabled": "command disabled",
    "command restrict": "command restrict @Moderator ban",
    "command unrestrict": "command unrestrict @Moderator ban",
    "command restricted": "command restricted",
    "lastfm": "lastfm",
    "lastfm set": "lastfm set username",
    "lastfm remove": "lastfm remove",
    "lastfm nowplaying": "lastfm nowplaying @offermillions",
    "lastfm recent": "lastfm recent @offermillions",
    "lastfm topartists": "lastfm topartists @offermillions",
    "lastfm toptracks": "lastfm toptracks @offermillions",
    "lastfm topalbums": "lastfm topalbums @offermillions",
    "lastfm reaction": "lastfm reaction 👍 👎",
    "lastfm cr": "lastfm cr 👍 👎",
    "voicemaster": "voicemaster",
    "voicemaster setup": "voicemaster setup #voice-channels",
    "voicemaster remove": "voicemaster remove",
    "softban": "softban @offermillions spamming",
    "notes": "notes",
    "notes add": "notes add @offermillions suspicious activity",
    "notes view": "notes view @offermillions",
    "notes remove": "notes remove 5",
    "notes clear": "notes clear @offermillions",
}


def env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def color_from_env(name: str) -> discord.Color:
    raw = env(name).lower()
    raw = raw[1:] if raw.startswith("#") else raw
    try:
        return discord.Color(int(raw, 16))
    except ValueError:
        raise RuntimeError(f"Invalid color value for {name}: {raw}")


def normalize_description(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = " ".join(cleaned.split())
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    if cleaned and cleaned[0].isalpha():
        cleaned = cleaned[0].lower() + cleaned[1:]
    return cleaned


def command_description(command: commands.Command[Any, ..., Any]) -> str:
    description = normalize_description(command.help or command.brief or "")
    if description and description.lower() not in PLACEHOLDER_DESCRIPTIONS:
        return description
    qualified = (command.qualified_name or command.name or "command").replace("_", " ").strip()
    if isinstance(command, commands.Group):
        return f"use subcommands under {qualified}"
    return f"run the {qualified} command"


def format_parameters(signature: str) -> str:
    if not signature:
        return "n/a"
    cleaned: list[str] = []
    for token in signature.split():
        token = token.strip("[]<>")
        token = token.replace("_", " ")
        if token:
            cleaned.append(token)
    return ", ".join(cleaned) if cleaned else "n/a"


def usage_from_clean_params(command: commands.Command[Any, ..., Any]) -> str:
    tokens: list[str] = []
    for name, param in command.clean_params.items():
        if name in {"self", "ctx"}:
            continue
        label = name.replace("_", " ")
        tokens.append(f"({label})" if param.default is param.empty else f"[{label}]")
    return f"{command.qualified_name} {' '.join(tokens)}".strip()


def usage_from_parameters(name: str, parameters: str) -> str:
    cleaned = parameters.replace(", ", " ").strip()
    return f"{name} {cleaned}".strip()


def command_permissions(command: commands.Command[Any, ..., Any]) -> str:
    found: list[str] = []
    current: commands.Command[Any, ..., Any] | None = command
    while current is not None:
        for check in getattr(current, "checks", []):
            predicate = getattr(check, "predicate", check)
            try:
                closure = inspect.getclosurevars(predicate)
            except TypeError:
                continue
            perms = closure.nonlocals.get("perms")
            if isinstance(perms, dict):
                found.extend(permission for permission, enabled in perms.items() if enabled)
        if current.extras.get("permissions"):
            found.extend(current.extras["permissions"])
        current = current.parent
    if not found:
        return "n/a"
    return ", ".join(sorted(set(found)))


def module_name(command: commands.Command[Any, ..., Any]) -> str:
    module_path = command.callback.__module__ if command.callback else ""
    parts = module_path.split(".")
    if "modules" in parts:
        index = parts.index("modules")
        if len(parts) > index + 1:
            return parts[index + 1].lower()
    return (command.cog_name or "misc").lower()


def build_command_pages(
    command: commands.Command[Any, ..., Any],
    prefix: str,
    author: discord.abc.User,
) -> list[discord.Embed]:
    pages: list[discord.Embed] = []

    def embed_for(item: commands.Command[Any, ..., Any], title: str) -> discord.Embed:
        key = item.qualified_name.lower()
        usage = str(item.extras.get("usage") or "").strip()
        if not usage:
            usage = usage_from_clean_params(item) or f"{item.qualified_name} {item.signature}".strip()
        parameters = item.extras.get("parameters") or format_parameters(item.signature)
        if "args" in item.signature and parameters != "n/a":
            usage = usage_from_parameters(item.qualified_name, parameters)

        aliases = ", ".join(item.aliases) if item.aliases else "n/a"
        permissions = command_permissions(item)
        example = EXAMPLES.get(key) or str(item.extras.get("example") or "").strip() or usage
        description = command_description(item)

        embed = discord.Embed(
            title=title,
            description=description,
            color=color_from_env("EMBED_INFO_COLOR"),
        )
        embed.set_author(
            name=author.display_name,
            icon_url=getattr(author.display_avatar, "url", None),
        )
        embed.add_field(name="**Aliases**", value=aliases, inline=True)
        embed.add_field(name="**Parameters**", value=parameters, inline=True)
        embed.add_field(name="**Permissions**", value=permissions, inline=True)
        embed.add_field(
            name="**Usage**",
            value=f"```kt\nSyntax: {prefix}{usage}\nExample: {prefix}{example}\n```",
            inline=False,
        )
        embed.set_footer(text=module_name(item))
        return embed

    def add_pages(item: commands.Command[Any, ..., Any]) -> None:
        title = f"Group command: {item.qualified_name}" if isinstance(item, commands.Group) else f"Command: {item.qualified_name}"
        pages.append(embed_for(item, title))
        if isinstance(item, commands.Group):
            for child in item.commands:
                add_pages(child)

    add_pages(command)
    return pages


def build_cog_map(bot: commands.Bot) -> dict[str, commands.Cog]:
    cog_map = {}
    for name, cog in bot.cogs.items():
        if name.lower() in ("help", "jishaku"):
            continue
        if "jishaku" in (getattr(cog, "__module__", "") or "").lower():
            continue
        cmds = [c for c in cog.get_commands() if not c.hidden]
        if cmds:
            key = cog.__cog_name__ if hasattr(cog, "__cog_name__") else name.lower()
            cog_map[key] = cog
    return cog_map


def build_commands_str(cog: commands.Cog) -> str:
    parts = []
    for cmd in cog.get_commands():
        if cmd.hidden:
            continue
        if isinstance(cmd, commands.Group):
            parts.append(f"{cmd.name} [{len(cmd.commands)}]")
        else:
            parts.append(cmd.name)
    return ", ".join(parts)


def build_select_options(cog_map: dict[str, commands.Cog]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(label=name.capitalize(), value=name)
        for name in cog_map
    ]


def build_home_view(cog_map: dict[str, commands.Cog], select_id: str) -> discord.ui.LayoutView:
    header_text = (
        "# [torment](https://torment.lat) \n"
        "> **Parameters** with `(…)` = required\n"
        "> **Parameters** with `[…]` = optional\n"
        "Commands marked with `*` have **subcommands.**"
    )

    class HomeView(discord.ui.LayoutView):
        container1 = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=header_text),
                accessory=discord.ui.Thumbnail(media="https://api.torment.lat/avatar"),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(
                discord.ui.Select(
                    placeholder="Select a category...",
                    min_values=1,
                    max_values=1,
                    options=build_select_options(cog_map),
                    custom_id=select_id,
                ),
            ),
            accent_color=ACCENT_COLOR,
        )

    return HomeView()


def build_category_view(cog: commands.Cog, cog_map: dict[str, commands.Cog], select_id: str) -> discord.ui.LayoutView:
    commands_str = build_commands_str(cog)
    description = cog.description or (cog.__cog_name__.capitalize() if hasattr(cog, "__cog_name__") else cog.qualified_name)

    content_text = (
        f"# [torment](https://torment.lat)  \n"
        f"> **{description}**\n"
        f"```yaml\n{commands_str}```"
    )

    class CategoryView(discord.ui.LayoutView):
        container1 = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=content_text),
                accessory=discord.ui.Thumbnail(media="https://api.torment.lat/avatar"),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(
                discord.ui.Select(
                    placeholder="Select a category...",
                    min_values=1,
                    max_values=1,
                    options=build_select_options(cog_map),
                    custom_id=select_id,
                ),
            ),
            accent_color=ACCENT_COLOR,
        )

    return CategoryView()


class Help(commands.Cog):
    __cog_name__ = "help"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sessions: dict[str, dict] = {}
        bot.help_command = None

    def _register_session(self, select_id: str, user_id: int, cog_map: dict[str, commands.Cog]) -> None:
        self._sessions[select_id] = {"user_id": user_id, "cog_map": cog_map}

    @commands.command(
        name="help",
        aliases=["h"],
        help="View all commands and categories",
        extras={"parameters": "n/a", "usage": "help"},
    )
    async def help(self, ctx: TormentContext, *, command: str | None = None) -> None:
        if command:
            target = ctx.bot.get_command(command.lower())
            if not target:
                if hasattr(ctx, "warn"):
                    await ctx.warn(f"Command **{command}** does **not** exist")
                else:
                    await ctx.send(f"Command `{command}` does not exist.")
                return

            pages = build_command_pages(target, ctx.clean_prefix, ctx.author)
            entries = len(pages)
            for index, page in enumerate(pages, start=1):
                module_text = page.footer.text or "misc"
                page.set_footer(
                    text=f"Page {index}/{entries} ({entries} entries) | Module: {module_text}"
                )
            if hasattr(ctx, "paginate"):
                await ctx.paginate(pages)
            else:
                await ctx.send(embed=pages[0])
            return

        cog_map = build_cog_map(self.bot)
        select_id = os.urandom(16).hex()
        self._register_session(select_id, ctx.author.id, cog_map)
        view = build_home_view(cog_map, select_id)
        await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
            return

        data = interaction.data or {}
        if data.get("component_type") != 3:
            return

        custom_id = data.get("custom_id", "")
        session = self._sessions.get(custom_id)
        if session is None:
            return

        if interaction.user.id != session["user_id"]:
            return await interaction.response.send_message("You can't use this menu.", ephemeral=True)

        cog_map = session["cog_map"]
        selected = (data.get("values") or [None])[0]

        new_select_id = os.urandom(16).hex()
        self._register_session(new_select_id, session["user_id"], cog_map)
        del self._sessions[custom_id]

        cog = cog_map.get(selected)
        if not cog:
            return await interaction.response.defer()

        view = build_category_view(cog, cog_map, new_select_id)
        message_id = interaction.message.id
        channel_id = interaction.channel_id
        await interaction.response.edit_message(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))

EXAMPLES["timeout"] = "timeout @offermillions 10m spamming"
EXAMPLES["untimeout"] = "untimeout @offermillions"
EXAMPLES["slowmode"] = "slowmode 5s"
