import math
import discord
from discord.ext import commands
from heist.framework.discord import Context
from .events import LevelEvents
from PIL import Image, ImageDraw
import io
import asyncio

async def create_progress_bar(xp, level):
    def _create_bar():
        xp_end = math.floor(5 * math.sqrt(level) + 50 * level + 30)
        percentage = (xp / xp_end) if xp_end > 0 else 0
        
        width, height = 400, 30
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        draw.rounded_rectangle([0, 0, width-1, height-1], radius=15, fill=(60, 60, 60, 255))
        
        if percentage > 0:
            progress_width = int((width - 4) * percentage)
            if progress_width > 0:
                draw.rounded_rectangle([2, 2, progress_width + 2, height-3], radius=13, fill=(128, 164, 168, 255))
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    
    return await asyncio.to_thread(_create_bar)

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def rank(self, ctx: Context, member: discord.Member = None):
        if member is None:
            member = ctx.author
        
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config or not config['status']:
            return await ctx.warn("Levels **aren't** enabled in this server.")
        
        member_data = await self.bot.pool.fetchrow(
            "SELECT * FROM level.member WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if not member_data:
            level, xp = 0, 0
        else:
            level = member_data['level']
            xp = member_data['xp']
        
        xp_end = math.floor(5 * math.sqrt(level) + 50 * level + 30)
        percentage = int(xp / xp_end * 100) if xp_end > 0 else 0
        
        progress_bar = await create_progress_bar(xp, level)
        file = discord.File(progress_bar, filename="progress.png")
        
        embed = discord.Embed(
            color=ctx.config.colors.information,
            title=f"{member.name}'s rank"
        ).set_author(
            name=member, icon_url=member.display_avatar.url
        ).add_field(
            name="XP", value=f"**{xp:,}** / **{xp_end:,}**"
        ).add_field(
            name="Level", value=f"**{level}**"
        ).add_field(
            name="Progress", value=f"**{percentage}%**"
        ).set_image(url="attachment://progress.png")
        
        await ctx.send(embed=embed, file=file)

    @commands.group(invoke_without_command=True)
    async def level(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @level.group(invoke_without_command=True)
    async def rewards(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @rewards.command()
    @commands.has_permissions(manage_guild=True)
    async def add(self, ctx: Context, level: int, *, role: discord.Role):
        if role.permissions.administrator or role.permissions.manage_guild:
            return await ctx.warn("You **cannot** make a level role a role with dangerous permissions.")
        
        existing = await self.bot.pool.fetchrow(
            "SELECT * FROM level.role WHERE guild_id = $1 AND level = $2",
            ctx.guild.id, level
        )
        if existing:
            return await ctx.warn(f"A role has been **already** assigned for level **{level}**.")
        
        await self.bot.pool.execute(
            "INSERT INTO level.role (guild_id, role_id, level) VALUES ($1, $2, $3)",
            ctx.guild.id, role.id, level
        )
        await ctx.approve(f"I have **added** {role.mention} for level **{level}** reward.")

    @rewards.command()
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx: Context, level: int):
        existing = await self.bot.pool.fetchrow(
            "SELECT * FROM level.role WHERE guild_id = $1 AND level = $2",
            ctx.guild.id, level
        )
        if not existing:
            return await ctx.warn(f"There is **no** role assigned for level **{level}**.")
        
        await self.bot.pool.execute(
            "DELETE FROM level.role WHERE guild_id = $1 AND level = $2",
            ctx.guild.id, level
        )
        await ctx.approve(f"I have **removed** level **{level}** reward.")

    @rewards.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def rewards_reset(self, ctx: Context):
        results = await self.bot.pool.fetch(
            "SELECT * FROM level.role WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.warn("There are **no** role rewards in this server.")
        
        await self.bot.pool.execute(
            "DELETE FROM level.role WHERE guild_id = $1", ctx.guild.id
        )
        await ctx.approve("I have reset **all** level rewards.")

    @rewards.command(name="list")
    async def rewards_list(self, ctx: Context):
        results = await self.bot.pool.fetch(
            "SELECT * FROM level.role WHERE guild_id = $1 ORDER BY level",
            ctx.guild.id
        )
        if not results:
            return await ctx.warn("There are **no** role rewards in this server.")
        
        description = ""
        for i, row in enumerate(results[:10], 1):
            role = ctx.guild.get_role(row['role_id'])
            role_mention = role.mention if role else f"<@&{row['role_id']}>"
            description += f"\n`{i}` level **{row['level']}** - {role_mention}"
        
        embed = discord.Embed(
            color=ctx.config.colors.information,
            description=description
        ).set_author(
            name="Level Rewards",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        
        await ctx.send(embed=embed)

    @level.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def level_reset(self, ctx: Context, *, member: discord.Member = None):
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("Levels are not configured.")
        
        if not member:
            await self.bot.pool.execute(
                "DELETE FROM level.member WHERE guild_id = $1", ctx.guild.id
            )
            await ctx.approve("I have reset levels for **all** members.")
        else:
            await self.bot.pool.execute(
                "DELETE FROM level.member WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, member.id
            )
            await ctx.approve(f"I have reset levels for **{member}**.")

    @level.command(aliases=["lb"])
    async def leaderboard(self, ctx: Context):
        results = await self.bot.pool.fetch(
            "SELECT * FROM level.member WHERE guild_id = $1 ORDER BY total_xp DESC LIMIT 10",
            ctx.guild.id
        )
        if not results:
            return await ctx.warn("Nobody is on the **level leaderboard**")
        
        description = ""
        for i, row in enumerate(results, 1):
            user = self.bot.get_user(row['user_id']) or f"<@{row['user_id']}>"
            crown = "<:crown:1263741407969939467>" if i == 1 else f"`{i}`"
            description += f"\n{crown} **{user}** - **{row['xp']}** xp (level {row['level']})"
        
        embed = discord.Embed(
            color=ctx.config.colors.information,
            description=description
        ).set_author(
            name="Level Leaderboard",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        
        await ctx.send(embed=embed)

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def toggle(self, ctx: Context):
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        
        if not config:
            await self.bot.pool.execute(
                "INSERT INTO level.config (guild_id) VALUES ($1)", ctx.guild.id
            )
            await ctx.approve("I have **enabled** the leveling system.")
        else:
            new_status = not config['status']
            await self.bot.pool.execute(
                "UPDATE level.config SET status = $1 WHERE guild_id = $2",
                new_status, ctx.guild.id
            )
            status_text = "enabled" if new_status else "disabled"
            await ctx.approve(f"I have **{status_text}** the leveling system.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def levelup(self, ctx: Context, destination: str):
        if destination not in ["dms", "channel", "off"]:
            return await ctx.warn("You passed an **invalid** destination.")
        
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("The leveling system is **not** enabled.")
        
        dm_setting = destination == "dms"
        await self.bot.pool.execute(
            "INSERT INTO level.notification (guild_id, dm) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET dm = $2",
            ctx.guild.id, dm_setting
        )
        
        await ctx.approve(f"I have **updated** the level up message destination: **{destination}**.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def message(self, ctx: Context, *, template: str = None):
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("The leveling system is **not** enabled.")
        
        if not template:
            await self.bot.pool.execute(
                "UPDATE level.notification SET template = NULL WHERE guild_id = $1",
                ctx.guild.id
            )
            await ctx.approve("Reset level up message to default.")
        else:
            await self.bot.pool.execute(
                "INSERT INTO level.notification (guild_id, template) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET template = $2",
                ctx.guild.id, template
            )
            await ctx.approve("Set custom level up message. Use any variable from the script system.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def channel(self, ctx: Context, *, channel: discord.TextChannel = None):
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("The leveling system is **not** enabled.")
        
        if not channel:
            await self.bot.pool.execute(
                "UPDATE level.notification SET channel_id = NULL WHERE guild_id = $1",
                ctx.guild.id
            )
            await ctx.approve("I have **removed** the channel for level up messages.")
        else:
            await self.bot.pool.execute(
                "INSERT INTO level.notification (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2",
                ctx.guild.id, channel.id
            )
            await ctx.approve(f"I have set the channel for level up messages to {channel.mention}.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def cooldown(self, ctx: Context, seconds: int):
        if seconds < 0 or seconds > 3600:
            return await ctx.warn("Cooldown must be between **0** and **3600** seconds.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET cooldown = $1 WHERE guild_id = $2",
            seconds, ctx.guild.id
        )
        await ctx.approve(f"Set XP cooldown to **{seconds}** seconds.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def multiplier(self, ctx: Context, multiplier: float):
        if multiplier < 0.1 or multiplier > 10:
            return await ctx.warn("Multiplier must be between **0.1** and **10**.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET xp_multiplier = $1 WHERE guild_id = $2",
            multiplier, ctx.guild.id
        )
        await ctx.approve(f"Set XP multiplier to **{multiplier}x**.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def xprange(self, ctx: Context, min_xp: int, max_xp: int):
        if min_xp < 1 or max_xp < min_xp or max_xp > 100:
            return await ctx.warn("Invalid XP range. Min must be ≥1, max must be ≥min and ≤100.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET xp_min = $1, xp_max = $2 WHERE guild_id = $3",
            min_xp, max_xp, ctx.guild.id
        )
        await ctx.approve(f"Set XP range to **{min_xp}-{max_xp}** per message.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def maxlevel(self, ctx: Context, max_level: int = None):
        if max_level is not None and max_level < 1:
            return await ctx.warn("Max level must be at least **1** or **0** to disable.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET max_level = $1 WHERE guild_id = $2",
            max_level or 0, ctx.guild.id
        )
        
        if max_level:
            await ctx.approve(f"Set max level to **{max_level}**.")
        else:
            await ctx.approve("Removed max level limit.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def stackroles(self, ctx: Context):
        config = await self.bot.pool.fetchrow(
            "SELECT stack_roles FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("Levels are not configured.")
        
        new_setting = not config['stack_roles']
        await self.bot.pool.execute(
            "UPDATE level.config SET stack_roles = $1 WHERE guild_id = $2",
            new_setting, ctx.guild.id
        )
        
        status = "enabled" if new_setting else "disabled"
        await ctx.approve(f"Role stacking has been **{status}**.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def effort(self, ctx: Context, toggle: str = None):
        if toggle and toggle.lower() not in ["on", "off"]:
            return await ctx.warn("Use **on** or **off** to toggle effort rewards.")
        
        config = await self.bot.pool.fetchrow(
            "SELECT effort_status FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("Levels are not configured.")
        
        if toggle:
            new_setting = toggle.lower() == "on"
            await self.bot.pool.execute(
                "UPDATE level.config SET effort_status = $1 WHERE guild_id = $2",
                new_setting, ctx.guild.id
            )
            status = "enabled" if new_setting else "disabled"
            await ctx.approve(f"Effort rewards have been **{status}**.")
        else:
            status = "enabled" if config['effort_status'] else "disabled"
            await ctx.neutral(f"Effort rewards are currently **{status}**.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def efforttext(self, ctx: Context, characters: int):
        if characters < 10 or characters > 500:
            return await ctx.warn("Text effort threshold must be between **10** and **500** characters.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET effort_text = $1 WHERE guild_id = $2",
            characters, ctx.guild.id
        )
        await ctx.approve(f"Set text effort threshold to **{characters}** characters.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def effortimage(self, ctx: Context, bonus_xp: int):
        if bonus_xp < 0 or bonus_xp > 50:
            return await ctx.warn("Image effort bonus must be between **0** and **50** XP.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET effort_image = $1 WHERE guild_id = $2",
            bonus_xp, ctx.guild.id
        )
        await ctx.approve(f"Set image effort bonus to **{bonus_xp}** XP.")

    @level.command()
    @commands.has_permissions(manage_guild=True)
    async def boosterbonus(self, ctx: Context, bonus_xp: int):
        if bonus_xp < 0 or bonus_xp > 100:
            return await ctx.warn("Booster bonus must be between **0** and **100** XP.")
        
        await self.bot.pool.execute(
            "UPDATE level.config SET effort_booster = $1 WHERE guild_id = $2",
            bonus_xp, ctx.guild.id
        )
        await ctx.approve(f"Set booster bonus to **{bonus_xp}** XP.")

    @level.command()
    async def config(self, ctx: Context):
        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", ctx.guild.id
        )
        if not config:
            return await ctx.warn("Levels are not configured.")
        
        embed = discord.Embed(
            title="Level Configuration",
            color=ctx.config.colors.information
        )
        
        embed.add_field(name="Status", value="Enabled" if config['status'] else "Disabled")
        embed.add_field(name="Cooldown", value=f"{config['cooldown']}s")
        embed.add_field(name="XP Range", value=f"{config['xp_min']}-{config['xp_max']}")
        embed.add_field(name="XP Multiplier", value=f"{config['xp_multiplier']}x")
        embed.add_field(name="Max Level", value=config['max_level'] or "None")
        embed.add_field(name="Stack Roles", value="Yes" if config['stack_roles'] else "No")
        embed.add_field(name="Effort Rewards", value="Enabled" if config['effort_status'] else "Disabled")
        embed.add_field(name="Text Threshold", value=f"{config['effort_text']} chars")
        embed.add_field(name="Image Bonus", value=f"{config['effort_image']} XP")
        embed.add_field(name="Booster Bonus", value=f"{config['effort_booster']} XP")
        
        notification = await self.bot.pool.fetchrow(
            "SELECT * FROM level.notification WHERE guild_id = $1", ctx.guild.id
        )
        if notification:
            embed.add_field(name="Level Up DMs", value="Yes" if notification['dm'] else "No")
            embed.add_field(name="Level Up Channel", value=f"<#{notification['channel_id']}>" if notification['channel_id'] else "Current")
            embed.add_field(name="Custom Message", value="Yes" if notification['template'] else "Default")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Levels(bot))
    await bot.add_cog(LevelEvents(bot))