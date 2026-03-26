import re
import os
import discord
from discord.ext import commands
from stare.core.tools.paginator import PaginatorView

CATEGORY_DESCRIPTIONS = {
    "Information": "View detailed bot statistics, server information, user profiles, and invite details",
    "Moderation": "Comprehensive moderation tools including kick, ban, mute, warn, and server management features",
    "Configuration": "Configure bot settings, autoroles, welcome messages, tickets, starboard, webhooks, and more",
    "Utility": "Useful utility commands for server management, reminders, polls, and general purpose tools",
    "Fun": "Fun and entertainment commands including roleplay actions, games, and interactive features",
    "Audio": "Manage your Last.fm integration, track music listening history, and display now playing information",
    "Social": "Lookup and display profiles from Instagram, TikTok, Roblox, Valorant, Minecraft, and more platforms",
    "Music": "Full-featured music playback system with queue management, filters, and playlist support",
    "Leveling": "Server leveling system with XP tracking, level roles, leaderboards, and rank cards",
    "Economy": "Virtual economy system with currency, shop, inventory, trading, and gambling features",
    "Security": "Advanced security features including antiraid, antinuke, verification, and server protection",
    "Premium": "Exclusive premium features and perks for supporters.",
}


def build_categories_dict(bot):
    categories_dict = {}
    for cog_name, cog in bot.cogs.items():
        if cog_name.lower() in ("jishaku", "help", "premium"):
            continue
        module_path = cog.__module__
        if "stare.plugins." in module_path:
            parts = module_path.split(".")
            folder_name = parts[2].capitalize() if len(parts) >= 3 else "Other"
            if folder_name.lower() == "developer":
                continue
        else:
            folder_name = "Other"
        visible_cmds = [cmd for cmd in cog.get_commands() if not cmd.hidden]
        if not visible_cmds:
            continue
        categories_dict.setdefault(folder_name, []).append(cog)
    return categories_dict


def _make_select_options(categories_dict):
    options = [{"label": "Home", "description": "Go back to the main page", "value": "home"}]
    for cat_name, cat_cogs in categories_dict.items():
        total = sum(len([c for c in cog.get_commands() if not c.hidden]) for cog in cat_cogs)
        desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{total} commands available")
        options.append({
            "label": cat_name,
            "description": desc[:100],
            "value": f"cat_{cat_name}",
        })
    return options


def build_home_payload(bot, categories_dict, select_id):
    return {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "accent_color": 921102,
                "components": [
                    {
                        "type": 9,
                        "components": [
                            {
                                "type": 10,
                                "content": (
                                    f"# {bot.user.name}\n"
                                    "Click on the **dropdown menu** to view each category.\n"
                                    "**Syntax**: `[..]` = optional, `<..>` = required\n"
                                    "Commands marked with `*` have **subcommands.**"
                                ),
                            }
                        ],
                        "accessory": {"type": 11, "media": {"url": str(bot.user.display_avatar.url)}},
                    },
                    {"type": 14},
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 3,
                                "custom_id": select_id,
                                "placeholder": "Select a category..",
                                "min_values": 1,
                                "max_values": 1,
                                "options": _make_select_options(categories_dict),
                            }
                        ],
                    },
                ],
            }
        ],
    }


def build_category_payload(bot, cogs, categories_dict, select_id):
    all_commands = [cmd for cog in cogs for cmd in cog.get_commands() if not cmd.hidden]
    command_names = [
        f"{cmd.name}*" if isinstance(cmd, commands.Group) else cmd.name
        for cmd in all_commands
    ]
    commands_str = ", ".join(command_names) if command_names else "No commands available"
    description = next((cog.description for cog in cogs if cog.description), None)
    desc_line = f"> **{description}**\n" if description else ""

    return {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "accent_color": 921102,
                "components": [
                    {
                        "type": 9,
                        "components": [
                            {
                                "type": 10,
                                "content": f"# {bot.user.name}\n{desc_line}```yaml\n{commands_str}```",
                            }
                        ],
                        "accessory": {"type": 11, "media": {"url": str(bot.user.display_avatar.url)}},
                    },
                    {"type": 14},
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 3,
                                "custom_id": select_id,
                                "placeholder": "Select a category..",
                                "min_values": 1,
                                "max_values": 1,
                                "options": _make_select_options(categories_dict),
                            }
                        ],
                    },
                ],
            }
        ],
    }


async def send_cv2(ctx, payload: dict):
    route = discord.http.Route(
        "POST", "/channels/{channel_id}/messages", channel_id=ctx.channel.id
    )
    return await ctx.bot.http.request(route, json=payload)


async def edit_cv2(interaction: discord.Interaction, payload: dict):
    await interaction.response.defer()
    route = discord.http.Route(
        "PATCH",
        f"/webhooks/{interaction.application_id}/{interaction.token}/messages/@original",
    )
    await interaction.client.http.request(route, json=payload)


def get_clean_signature(command):
    if command.signature:
        sig = re.sub(r"=\S+", "", command.signature)
        return sig.strip()
    return ""


def get_required_permissions(command):
    perms = []
    for check in command.checks:
        name = getattr(check, "__qualname__", "")
        if "has_permissions" not in name or "bot_has" in name:
            continue
        if hasattr(check, "__closure__") and check.__closure__:
            for cell in check.__closure__:
                try:
                    val = cell.cell_contents
                    if isinstance(val, dict):
                        perms.extend([p.replace("_", " ").title() for p, v in val.items() if v])
                except (ValueError, AttributeError):
                    pass
    return ", ".join(perms) if perms else "None"


def build_command_embed(command, ctx):
    prefix = ctx.prefix
    is_sub = command.parent is not None
    module_name = command.cog.qualified_name if command.cog else "Other"
    is_premium = (
        getattr(command, "extras", {}).get("premium", False)
        or module_name.lower() == "premium"
    )
    premium_emoji = "<:premium:1478944142846459988> " if is_premium else ""

    title = (
        f"{premium_emoji}Subcommand: **{command.qualified_name}**"
        if is_sub
        else f"{premium_emoji}Command: **{command.qualified_name}**"
    )
    aliases = ", ".join(command.aliases) if command.aliases else "None"
    sig = get_clean_signature(command)
    arguments = sig if sig else "None"
    permissions = get_required_permissions(command)

    syntax_line = f"\x1b[2;30mSyntax\x1b[0m: {prefix}{command.qualified_name} {sig}".rstrip()

    if hasattr(command, "extras") and "example" in command.extras:
        example_line = f"\x1b[2;30mExample\x1b[0m: {prefix}{command.extras['example']}"
    else:
        example_line = f"\x1b[2;30mExample\x1b[0m: {prefix}{command.qualified_name}"

    footer_text = f"Module: {module_name}"

    avatar_url = ctx.bot.user.display_avatar.url
    embed = discord.Embed(
        title=title,
        description=f"> **{command.help or 'No description available'}**\n",
        color=855309,
    )
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="Aliases:", value=f"**{aliases}**", inline=True)
    embed.add_field(name="Arguments:", value=f"**{arguments}**", inline=True)
    embed.add_field(name="Permissions:", value=f"**{permissions}**", inline=True)
    embed.add_field(
        name="Usage:",
        value=f"```ansi\n{syntax_line}\n{example_line}\n```",
        inline=False,
    )
    embed.set_footer(text=footer_text, icon_url=avatar_url)
    return embed


class HelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs={
                "help": "Shows help about the bot, a command, or a category",
                "aliases": ["h"],
            }
        )

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot
        categories_dict = build_categories_dict(bot)
        select_id = os.urandom(16).hex()
        bot.get_cog("Help")._register_session(select_id, ctx.author.id, categories_dict)
        payload = build_home_payload(bot, categories_dict, select_id)
        await send_cv2(ctx, payload)

    async def send_cog_help(self, cog):
        ctx = self.context
        bot = ctx.bot
        categories_dict = build_categories_dict(bot)

        module_path = cog.__module__
        if "stare.plugins." in module_path:
            parts = module_path.split(".")
            folder_name = parts[2].capitalize() if len(parts) >= 3 else "Other"
        else:
            folder_name = cog.qualified_name

        cogs = categories_dict.get(folder_name, [cog])
        select_id = os.urandom(16).hex()
        bot.get_cog("Help")._register_session(select_id, ctx.author.id, categories_dict)
        payload = build_category_payload(bot, cogs, categories_dict, select_id)
        await send_cv2(ctx, payload)

    async def send_group_help(self, group):
        ctx = self.context
        subcommands = await self.filter_commands(group.commands, sort=True)
        all_cmds = [group] + list(subcommands)

        embeds = [
            build_command_embed(cmd, ctx)
            for cmd in all_cmds
        ]

        if len(embeds) > 1:
            view = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=view)
        else:
            await ctx.send(embed=embeds[0])

    async def send_command_help(self, command):
        ctx = self.context
        embed = build_command_embed(command, ctx)
        await ctx.send(embed=embed)

    async def send_error_message(self, error):
        ctx = self.context
        await ctx.warn(str(error))


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._sessions = {}
        self._original_help_command = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self

    def _register_session(self, select_id, user_id, categories_dict):
        self._sessions[select_id] = {
            "user_id": user_id,
            "categories_dict": categories_dict,
        }

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
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
            return await interaction.response.send_message("lil bro u can't use this", ephemeral=True)

        categories_dict = session["categories_dict"]
        value = (data.get("values") or ["home"])[0]

        new_select_id = os.urandom(16).hex()
        self._register_session(new_select_id, session["user_id"], categories_dict)
        del self._sessions[custom_id]

        if value == "home":
            payload = build_home_payload(self.bot, categories_dict, new_select_id)
        else:
            cat_name = value[len("cat_"):]
            cogs = categories_dict.get(cat_name)
            if not cogs:
                return await interaction.response.send_message("Category not found!", ephemeral=True)
            payload = build_category_payload(self.bot, cogs, categories_dict, new_select_id)

        await edit_cv2(interaction, payload)

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


async def setup(bot):
    await bot.add_cog(Help(bot))
