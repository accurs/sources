import discord
from discord.ext import commands
from discord.ext.tasks import loop
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional
from discord import AuditLogEntry, Forbidden, Member, User
from discord.utils import MISSING
from ._undo_methods import REVERT_METHODS
from maniac.core.command_example import example

class Undo(commands.Cog):
    reverted_actions: Dict[int, deque[int]] = defaultdict(deque)
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        self.reverted_actions_cleanup.start()
        return await super().cog_load()
    
    async def cog_unload(self):
        self.reverted_actions_cleanup.cancel()
        return await super().cog_unload()
    
    @loop(minutes=30)
    async def reverted_actions_cleanup(self):
        self.reverted_actions.clear()
    
    async def get_audit_log(
        self,
        guild: discord.Guild,
        user: Optional[User | Member] = None,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
        include_reverted: bool = False,
    ) -> List[AuditLogEntry]:
        _after = datetime.now(tz=timezone.utc) - timedelta(days=7)
        after = max(after, _after) if after is not None else _after
        
        reverted_audit_logs = self.reverted_actions[guild.id]
        
        return [
            audit_log
            async for audit_log in guild.audit_logs(
                limit=100,
                user=user or MISSING,
                after=after,
                before=before or MISSING,
            )
            if (
                any(audit_log.action in actions for actions in REVERT_METHODS.values())
                and (audit_log.id not in reverted_audit_logs or include_reverted)
            )
        ][:5]
    
    @commands.command(aliases=["revert", "ctrlz"])
    @example(",undo ban @offermillions")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def undo(self, ctx, user: Optional[Member | User] = None):
        audit_logs = await self.get_audit_log(ctx.guild, user=user)
        
        if not audit_logs:
            return await ctx.deny("There aren't any recent actions to revert")
        
        revert_method: Optional[Callable[[AuditLogEntry], Coroutine[Any, Any, None]]] = None
        
        for audit_log in audit_logs:
            for method in REVERT_METHODS.values():
                if audit_log.action in method:
                    revert_method = method[audit_log.action]
                    break
            if revert_method:
                break
        
        if not revert_method:
            return await ctx.deny("There aren't any recent actions to revert")
        
        class UndoConfirmView(discord.ui.View):
            def __init__(self, ctx_inner):
                super().__init__(timeout=30)
                self.ctx = ctx_inner
                self.value = None
            
            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = True
                self.stop()
                await interaction.response.defer()
            
            @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
            async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = False
                self.stop()
                await interaction.response.defer()
        
        action_name = str(audit_log.action).replace("AuditLogAction.", "").replace("_", " ").title()
        target_name = str(audit_log.target) if audit_log.target else "Unknown"
        
        view = UndoConfirmView(ctx)
        from maniac.core.config import Config
        confirm_msg = await ctx.send(
            embed=discord.Embed(
                description=f"{ctx.author.mention}: Are you sure you want to revert the **{action_name}** action on **{target_name}** by {audit_log.user.mention if audit_log.user else 'Unknown User'}?",
                color=Config.COLORS.WARNING
            ),
            view=view
        )
        
        await view.wait()
        
        if view.value is None:
            await confirm_msg.delete()
            return await ctx.deny("Undo action timed out")
        
        if not view.value:
            await confirm_msg.delete()
            return await ctx.deny("Undo action cancelled")
        
        await confirm_msg.delete()
        
        try:
            await revert_method(audit_log)
        except Forbidden:
            return await ctx.deny("I don't have permission to revert this action")
        except Exception as exc:
            return await ctx.deny(f"An error occurred while reverting the action: {exc}")
        
        self.reverted_actions[ctx.guild.id].append(audit_log.id)
        await ctx.approve(f"Successfully reverted the **{action_name}** action by {audit_log.user.mention if audit_log.user else 'Unknown User'}")

async def setup(bot):
    await bot.add_cog(Undo(bot))
