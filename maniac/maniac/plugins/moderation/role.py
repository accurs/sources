import discord
from discord.ext import commands
from typing import Optional, List
import re
from maniac.core.config import Config
from maniac.core.command_example import example

CUSTOM_EMOJI_RE = re.compile(r"<(?P<animated>a?):(?P<name>\w+):(?P<id>\d+)>")

class RoleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(aliases=["r"], invoke_without_command=True, help="Add or remove a role from a member")
    @example(",role @offermillions @Member")
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage this role due to role hierarchy")
        
        if role in member.roles:
            await member.remove_roles(role, reason=f"Removed by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully removed {role.mention} from {member.mention}")
        else:
            await member.add_roles(role, reason=f"Added by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully added {role.mention} to {member.mention}")
    
    @role.command(name="add", aliases=["grant"], help="Add a role to a member")
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx, member: discord.Member, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage this role due to role hierarchy")
        
        if role in member.roles:
            return await ctx.deny(f"{member.mention} already has {role.mention}")
        
        await member.add_roles(role, reason=f"Added by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully added {role.mention} to {member.mention}")
    
    @role.command(name="remove", aliases=["rm", "revoke"], help="Remove a role from a member")
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx, member: discord.Member, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage this role due to role hierarchy")
        
        if role not in member.roles:
            return await ctx.deny(f"{member.mention} doesn't have {role.mention}")
        
        await member.remove_roles(role, reason=f"Removed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully removed {role.mention} from {member.mention}")
    
    @role.command(name="create", aliases=["make"], help="Create a new role")
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx, *, name: str):
        if len(name) > 100:
            return await ctx.deny("Role name must be 100 characters or less")
        if len(ctx.guild.roles) >= 250:
            return await ctx.deny("This server has reached the maximum amount of roles")
        
        role = await ctx.guild.create_role(
            name=name,
            reason=f"Created by {ctx.author} ({ctx.author.id})"
        )
        await ctx.approve(f"Successfully created role {role.mention}")
    
    @role.command(name="delete", aliases=["del"], help="Delete a role")
    @commands.has_permissions(manage_roles=True)
    async def role_delete(self, ctx, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot delete this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot delete this role due to role hierarchy")
        
        await role.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully deleted role **{role.name}**")
    
    @role.command(name="color", aliases=["colour"], help="Change a role's color")
    @commands.has_permissions(manage_roles=True)
    async def role_color(self, ctx, role: discord.Role, color: discord.Color):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit this role due to role hierarchy")
        
        await role.edit(color=color, reason=f"Changed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully changed {role.mention}'s color to `{color}`")
    
    @role.command(name="rename", aliases=["name"], help="Rename a role")
    @commands.has_permissions(manage_roles=True)
    async def role_rename(self, ctx, role: discord.Role, *, name: str):
        if len(name) > 100:
            return await ctx.deny("Role name must be 100 characters or less")
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit this role due to role hierarchy")
        
        await role.edit(name=name, reason=f"Renamed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully renamed role to **{name}**")
    
    @role.command(name="hoist", help="Toggle role hoisting")
    @commands.has_permissions(manage_roles=True)
    async def role_hoist(self, ctx, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit this role due to role hierarchy")
        
        await role.edit(hoist=not role.hoist, reason=f"Changed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully {'hoisted' if role.hoist else 'unhoisted'} {role.mention}")
    
    @role.command(name="mentionable", help="Toggle role mentionability")
    @commands.has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit this role due to role hierarchy")
        
        await role.edit(mentionable=not role.mentionable, reason=f"Changed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"{role.mention} is {'now' if role.mentionable else 'no longer'} mentionable")
    
    @role.command(name="icon", help="Set a role's icon")
    @commands.has_permissions(manage_roles=True)
    async def role_icon(self, ctx, role: discord.Role, icon: Optional[str] = None):
        if ctx.guild.premium_tier < 2:
            return await ctx.deny("Role icons require Server Boost Level 2 or higher")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit this role due to role hierarchy")
        
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                return await ctx.deny("Attachment must be an image")
            
            image_bytes = await attachment.read()
            await role.edit(display_icon=image_bytes, reason=f"Changed by {ctx.author} ({ctx.author.id})")
            return await ctx.approve(f"Successfully changed {role.mention}'s icon")
        
        if icon:
            match = CUSTOM_EMOJI_RE.fullmatch(icon)
            if match:
                emoji_id = match.group("id")
                animated = bool(match.group("animated"))
                ext = "gif" if animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                
                async with self.bot.session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.deny("Invalid custom emoji")
                    image_bytes = await resp.read()
                
                await role.edit(display_icon=image_bytes, reason=f"Changed by {ctx.author} ({ctx.author.id})")
                return await ctx.approve(f"Successfully changed {role.mention}'s icon")
            
            emoji_code = "-".join(f"{ord(c):x}" for c in icon)
            url = f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_code}.png"
            
            async with self.bot.session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.deny("Invalid Unicode emoji")
                image_bytes = await resp.read()
            
            await role.edit(display_icon=image_bytes, reason=f"Changed by {ctx.author} ({ctx.author.id})")
            return await ctx.approve(f"Successfully changed {role.mention}'s icon to {icon}")
        
        return await ctx.deny("Provide an emoji or upload an image to set the role icon")
    
    @role.command(name="all", aliases=["everyone"], help="Add a role to all members in the server")
    @commands.has_permissions(manage_roles=True)
    async def role_all(self, ctx, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage this role due to role hierarchy")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage this role due to role hierarchy")
        
        members_added = 0
        async with ctx.typing():
            for member in ctx.guild.members:
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Mass role by {ctx.author} ({ctx.author.id})")
                        members_added += 1
                    except:
                        pass
        
        await ctx.approve(f"Successfully added {role.mention} to {members_added} member(s)")

async def setup(bot):
    await bot.add_cog(RoleManagement(bot))
