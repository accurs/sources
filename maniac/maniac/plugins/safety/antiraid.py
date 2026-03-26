import discord
from discord.ext import commands
from maniac.core.config import Config
from maniac.core.command_example import example
from datetime import datetime, timedelta, timezone
import re

class ConfirmView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.value = None
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
        
        self.value = True
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
        
        self.value = False
        self.stop()
        await interaction.response.defer()

class AntiRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="raid", help="Remove all members that joined within a time period")
    @example(",raid 10m ban raid cleanup")
    @commands.has_permissions(administrator=True)
    async def raid(self, ctx, duration: str, action: str, *, reason: str = "Raid cleanup"):
        if action.lower() not in ["kick", "ban"]:
            return await ctx.deny("Action must be either `kick` or `ban`")
        
        time_regex = re.match(r"(\d+)([smhd])", duration.lower())
        if not time_regex:
            return await ctx.deny("Invalid duration format. Use: 10s, 5m, 2h, 1d")
        
        amount, unit = time_regex.groups()
        amount = int(amount)
        
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * time_units[unit]
        
        if seconds < 60:
            return await ctx.deny("Duration must be at least 1 minute")
        
        if seconds > 86400:
            return await ctx.warn("Duration cannot exceed 24 hours")
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        
        targets = [
            member for member in ctx.guild.members
            if member.joined_at and member.joined_at > cutoff_time
            and not member.bot
            and member != ctx.guild.owner
            and member.top_role < ctx.guild.me.top_role
            and member != ctx.author
        ]
        
        if not targets:
            return await ctx.warn(f"No members found that joined in the last {duration}")
        
        time_display = f"{amount} {'second' if amount == 1 else 'seconds'}" if unit == 's' else \
                      f"{amount} {'minute' if amount == 1 else 'minutes'}" if unit == 'm' else \
                      f"{amount} {'hour' if amount == 1 else 'hours'}" if unit == 'h' else \
                      f"{amount} {'day' if amount == 1 else 'days'}"
        
        confirm_embed = discord.Embed(
            title="Raid Cleanup Confirmation",
            description=f"Are you sure you want to {action} **{len(targets)}** member{'s' if len(targets) != 1 else ''} who joined in the last {time_display}?",
            color=Config.COLORS.WARNING
        )
        confirm_embed.add_field(name="Action", value=action.capitalize(), inline=True)
        confirm_embed.add_field(name="Reason", value=reason, inline=True)
        confirm_embed.add_field(name="Time Period", value=time_display, inline=True)
        confirm_embed.set_footer(text="This action cannot be undone")
        
        view = ConfirmView(ctx)
        message = await ctx.send(embed=confirm_embed, view=view)
        
        await view.wait()
        
        if view.value is None:
            await message.delete()
            return await ctx.deny("Raid cleanup timed out")
        
        if not view.value:
            await message.delete()
            return await ctx.deny("Raid cleanup cancelled")
        
        await message.delete()
        
        processing_embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} Processing raid cleanup...",
            color=Config.COLORS.LOADING
        )
        status_msg = await ctx.send(embed=processing_embed)
        
        success_count = 0
        failed_count = 0
        
        for member in targets:
            try:
                if action.lower() == "kick":
                    await member.kick(reason=f"{reason} | {ctx.author} ({ctx.author.id})")
                else:
                    await member.ban(reason=f"{reason} | {ctx.author} ({ctx.author.id})")
                success_count += 1
            except:
                failed_count += 1
        
        await status_msg.delete()
        
        result_embed = discord.Embed(
            description=f"Successfully removed **{success_count}** member{'s' if success_count != 1 else ''} with **{action}** in the last **{time_display}**",
            color=Config.COLORS.SUCCESS
        )
        
        if failed_count > 0:
            result_embed.add_field(
                name="Failed",
                value=f"{failed_count} member{'s' if failed_count != 1 else ''} could not be {action}ed",
                inline=False
            )
        
        result_embed.set_footer(text=f"Reason: {reason}")
        
        await ctx.send(embed=result_embed)

async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
