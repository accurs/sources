import discord
from discord.ext import commands
from typing import Optional, Literal
import json
import datetime
from maniac.core.command_example import example

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(name="automod", aliases=["am"], invoke_without_command=True)
    @example(",automod list")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        pass
    
    @automod.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def automod_list(self, ctx):
        try:
            rules = await ctx.guild.fetch_automod_rules()
            
            if not rules:
                return await ctx.deny("This server has no automod rules")
            
            embed = discord.Embed(
                title=f"Auto Moderation Rules ({len(rules)})",
                color=Config.COLORS.DEFAULT
            )
            
            for rule in rules:
                status = "🟢 Enabled" if rule.enabled else "🔴 Disabled"
                trigger_types = {
                    1: "Keyword",
                    3: "Spam",
                    4: "Preset",
                    5: "Mention Spam",
                    6: "Member Profile"
                }
                trigger = trigger_types.get(rule.trigger_type, "Unknown")
                
                embed.add_field(
                    name=f"{rule.name} ({status})",
                    value=f"**ID:** `{rule.id}`\n**Type:** {trigger}\n**Actions:** {len(rule.actions)}",
                    inline=True
                )
            
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.deny(f"Failed to fetch automod rules: {str(e)}")
    
    @automod.command(name="view")
    @commands.has_permissions(manage_guild=True)
    async def automod_view(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            embed = discord.Embed(
                title=f"Automod Rule: {rule.name}",
                color=Config.COLORS.DEFAULT
            )
            
            trigger_types = {
                1: "Keyword Filter",
                3: "Spam Detection",
                4: "Keyword Preset",
                5: "Mention Spam",
                6: "Member Profile"
            }
            
            event_types = {
                1: "Message Send",
                2: "Member Update"
            }
            
            embed.add_field(
                name="General",
                value=f"**ID:** `{rule.id}`\n**Enabled:** {'Yes' if rule.enabled else 'No'}\n**Trigger:** {trigger_types.get(rule.trigger_type, 'Unknown')}\n**Event:** {event_types.get(rule.event_type, 'Unknown')}",
                inline=False
            )
            
            if rule.trigger:
                metadata_info = []
                if hasattr(rule.trigger, 'keyword_filter') and rule.trigger.keyword_filter:
                    keywords = ', '.join([f"`{k}`" for k in rule.trigger.keyword_filter[:5]])
                    if len(rule.trigger.keyword_filter) > 5:
                        keywords += f" (+{len(rule.trigger.keyword_filter) - 5} more)"
                    metadata_info.append(f"**Keywords:** {keywords}")
                
                if hasattr(rule.trigger, 'regex_patterns') and rule.trigger.regex_patterns:
                    patterns = ', '.join([f"`{p}`" for p in rule.trigger.regex_patterns[:3]])
                    metadata_info.append(f"**Regex:** {patterns}")
                
                if hasattr(rule.trigger, 'presets') and rule.trigger.presets:
                    preset_names = {1: "Profanity", 2: "Sexual Content", 3: "Slurs"}
                    presets = ', '.join([preset_names.get(p, str(p)) for p in rule.trigger.presets])
                    metadata_info.append(f"**Presets:** {presets}")
                
                if hasattr(rule.trigger, 'mention_limit'):
                    metadata_info.append(f"**Mention Limit:** {rule.trigger.mention_limit}")
                
                if hasattr(rule.trigger, 'mention_raid_protection'):
                    metadata_info.append(f"**Raid Protection:** {'Enabled' if rule.trigger.mention_raid_protection else 'Disabled'}")
                
                if metadata_info:
                    embed.add_field(
                        name="Trigger Settings",
                        value='\n'.join(metadata_info),
                        inline=False
                    )
            
            if rule.actions:
                action_types = {
                    1: "Block Message",
                    2: "Send Alert",
                    3: "Timeout",
                    4: "Block Interaction"
                }
                actions_info = []
                for action in rule.actions:
                    action_name = action_types.get(action.type, "Unknown")
                    if action.metadata:
                        if hasattr(action.metadata, 'channel_id') and action.metadata.channel_id:
                            actions_info.append(f"• {action_name} → <#{action.metadata.channel_id}>")
                        elif hasattr(action.metadata, 'duration_seconds') and action.metadata.duration_seconds:
                            actions_info.append(f"• {action_name} ({action.metadata.duration_seconds}s)")
                        elif hasattr(action.metadata, 'custom_message') and action.metadata.custom_message:
                            actions_info.append(f"• {action_name}: {action.metadata.custom_message}")
                        else:
                            actions_info.append(f"• {action_name}")
                    else:
                        actions_info.append(f"• {action_name}")
                
                embed.add_field(
                    name="Actions",
                    value='\n'.join(actions_info) if actions_info else "None",
                    inline=False
                )
            
            if rule.exempt_roles:
                roles = ', '.join([f"<@&{r}>" for r in rule.exempt_roles[:5]])
                if len(rule.exempt_roles) > 5:
                    roles += f" (+{len(rule.exempt_roles) - 5} more)"
                embed.add_field(name="Exempt Roles", value=roles, inline=False)
            
            if rule.exempt_channels:
                channels = ', '.join([f"<#{c}>" for c in rule.exempt_channels[:5]])
                if len(rule.exempt_channels) > 5:
                    channels += f" (+{len(rule.exempt_channels) - 5} more)"
                embed.add_field(name="Exempt Channels", value=channels, inline=False)
            
            await ctx.reply(embed=embed)
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to fetch rule: {str(e)}")
    
    @automod.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def automod_delete(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            await rule.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully deleted automod rule **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to delete rule: {str(e)}")
    
    @automod.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            await rule.edit(enabled=True, reason=f"Enabled by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully enabled automod rule **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to enable rule: {str(e)}")
    
    @automod.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            await rule.edit(enabled=False, reason=f"Disabled by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully disabled automod rule **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to disable rule: {str(e)}")
    
    @automod.group(name="keyword", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_keyword(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_keyword.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def keyword_create(self, ctx, name: str, *keywords: str):
        if not keywords:
            return await ctx.deny("You need to provide at least one keyword")
        
        if len(keywords) > 1000:
            return await ctx.deny("Maximum 1000 keywords allowed")
        
        try:
            rule = await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    keyword_filter=list(keywords)
                ),
                actions=[discord.AutoModRuleAction()],
                enabled=True,
                reason=f"Created by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully created keyword filter **{rule.name}** with ID `{rule.id}`")
        except Exception as e:
            await ctx.deny(f"Failed to create rule: {str(e)}")
    
    @automod_keyword.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def keyword_add(self, ctx, rule_id: str, *keywords: str):
        if not keywords:
            return await ctx.deny("You need to provide at least one keyword")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.keyword:
                return await ctx.deny("This rule is not a keyword filter")
            
            current_keywords = list(rule.trigger.keyword_filter) if rule.trigger.keyword_filter else []
            new_keywords = current_keywords + list(keywords)
            
            if len(new_keywords) > 1000:
                return await ctx.deny(f"Maximum 1000 keywords allowed (current: {len(current_keywords)})")
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    keyword_filter=new_keywords,
                    regex_patterns=rule.trigger.regex_patterns if rule.trigger.regex_patterns else []
                ),
                reason=f"Keywords added by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added {len(keywords)} keyword(s) to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add keywords: {str(e)}")
    
    @automod_keyword.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def keyword_remove(self, ctx, rule_id: str, *keywords: str):
        if not keywords:
            return await ctx.deny("You need to provide at least one keyword")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.keyword:
                return await ctx.deny("This rule is not a keyword filter")
            
            current_keywords = list(rule.trigger.keyword_filter) if rule.trigger.keyword_filter else []
            new_keywords = [k for k in current_keywords if k not in keywords]
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    keyword_filter=new_keywords,
                    regex_patterns=rule.trigger.regex_patterns if rule.trigger.regex_patterns else []
                ),
                reason=f"Keywords removed by {ctx.author} ({ctx.author.id})"
            )
            removed = len(current_keywords) - len(new_keywords)
            await ctx.approve(f"Successfully removed {removed} keyword(s) from **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to remove keywords: {str(e)}")
    
    @automod_keyword.command(name="regex")
    @commands.has_permissions(manage_guild=True)
    async def keyword_regex(self, ctx, rule_id: str, pattern: str):
        if len(pattern) > 260:
            return await ctx.deny("Regex pattern must be 260 characters or less")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.keyword:
                return await ctx.deny("This rule is not a keyword filter")
            
            current_patterns = list(rule.trigger.regex_patterns) if rule.trigger.regex_patterns else []
            
            if len(current_patterns) >= 10:
                return await ctx.deny("Maximum 10 regex patterns allowed")
            
            current_patterns.append(pattern)
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    keyword_filter=rule.trigger.keyword_filter if rule.trigger.keyword_filter else [],
                    regex_patterns=current_patterns
                ),
                reason=f"Regex pattern added by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added regex pattern to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add regex pattern: {str(e)}")
    
    @automod_keyword.command(name="whitelist")
    @commands.has_permissions(manage_guild=True)
    async def keyword_whitelist(self, ctx, rule_id: str, *words: str):
        if not words:
            return await ctx.deny("You need to provide at least one word")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.keyword:
                return await ctx.deny("This rule is not a keyword filter")
            
            current_whitelist = list(rule.trigger.allow_list) if rule.trigger.allow_list else []
            new_whitelist = current_whitelist + list(words)
            
            if len(new_whitelist) > 100:
                return await ctx.deny(f"Maximum 100 whitelist words allowed (current: {len(current_whitelist)})")
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    keyword_filter=rule.trigger.keyword_filter if rule.trigger.keyword_filter else [],
                    regex_patterns=rule.trigger.regex_patterns if rule.trigger.regex_patterns else [],
                    allow_list=new_whitelist
                ),
                reason=f"Whitelist updated by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added {len(words)} word(s) to whitelist for **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to update whitelist: {str(e)}")

    
    @automod.group(name="spam", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_spam(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_spam.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def spam_create(self, ctx, name: str):
        try:
            rule = await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
                actions=[discord.AutoModRuleAction()],
                enabled=True,
                reason=f"Created by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully created spam filter **{rule.name}** with ID `{rule.id}`")
        except Exception as e:
            await ctx.deny(f"Failed to create rule: {str(e)}")
    
    @automod_spam.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    async def spam_toggle(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.spam:
                return await ctx.deny("This rule is not a spam filter")
            
            new_state = not rule.enabled
            await rule.edit(enabled=new_state, reason=f"Toggled by {ctx.author} ({ctx.author.id})")
            status = "enabled" if new_state else "disabled"
            await ctx.approve(f"Successfully {status} spam filter **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to toggle rule: {str(e)}")
    
    @automod.group(name="preset", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_preset(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_preset.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def preset_create(self, ctx, name: str, preset_type: Literal["profanity", "sexual", "slurs"]):
        preset_map = {
            "profanity": discord.AutoModPresets(profanity=True),
            "sexual": discord.AutoModPresets(sexual_content=True),
            "slurs": discord.AutoModPresets(slurs=True)
        }
        
        preset = preset_map.get(preset_type.lower())
        if not preset:
            return await ctx.deny("Invalid preset type. Use: profanity, sexual, or slurs")
        
        try:
            rule = await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword_preset, presets=preset),
                actions=[discord.AutoModRuleAction()],
                enabled=True,
                reason=f"Created by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully created {preset_type} filter **{rule.name}** with ID `{rule.id}`")
        except Exception as e:
            await ctx.deny(f"Failed to create rule: {str(e)}")
    
    @automod_preset.command(name="whitelist")
    @commands.has_permissions(manage_guild=True)
    async def preset_whitelist(self, ctx, rule_id: str, *words: str):
        if not words:
            return await ctx.deny("You need to provide at least one word")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.keyword_preset:
                return await ctx.deny("This rule is not a preset filter")
            
            current_whitelist = list(rule.trigger.allow_list) if rule.trigger.allow_list else []
            new_whitelist = current_whitelist + list(words)
            
            if len(new_whitelist) > 1000:
                return await ctx.deny(f"Maximum 1000 whitelist words allowed (current: {len(current_whitelist)})")
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    presets=rule.trigger.presets,
                    allow_list=new_whitelist
                ),
                reason=f"Whitelist updated by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added {len(words)} word(s) to whitelist for **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to update whitelist: {str(e)}")
    
    @automod.group(name="mentions", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_mentions(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_mentions.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def mentions_create(self, ctx, name: str, limit: int):
        if limit < 1 or limit > 50:
            return await ctx.deny("Mention limit must be between 1 and 50")
        
        try:
            rule = await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.mention_spam,
                    mention_limit=limit
                ),
                actions=[discord.AutoModRuleAction()],
                enabled=True,
                reason=f"Created by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully created mention spam filter **{rule.name}** with limit {limit} (ID: `{rule.id}`)")
        except Exception as e:
            await ctx.deny(f"Failed to create rule: {str(e)}")
    
    @automod_mentions.command(name="raidprotection")
    @commands.has_permissions(manage_guild=True)
    async def mentions_raidprotection(self, ctx, rule_id: str, state: Literal["on", "off"]):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.mention_spam:
                return await ctx.deny("This rule is not a mention spam filter")
            
            enabled = state.lower() == "on"
            
            await rule.edit(
                trigger=discord.AutoModTrigger(
                    mention_limit=rule.trigger.mention_limit,
                    mention_raid_protection=enabled
                ),
                reason=f"Raid protection {'enabled' if enabled else 'disabled'} by {ctx.author} ({ctx.author.id})"
            )
            status = "enabled" if enabled else "disabled"
            await ctx.approve(f"Successfully {status} raid protection for **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to update raid protection: {str(e)}")
    
    @automod.group(name="profile", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_profile(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_profile.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def profile_create(self, ctx, name: str, *keywords: str):
        if not keywords:
            return await ctx.deny("You need to provide at least one keyword")
        
        if len(keywords) > 1000:
            return await ctx.deny("Maximum 1000 keywords allowed")
        
        try:
            rule = await ctx.guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.member_update,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.member_profile,
                    keyword_filter=list(keywords)
                ),
                actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_member_interactions)],
                enabled=True,
                reason=f"Created by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully created member profile filter **{rule.name}** with ID `{rule.id}`")
        except Exception as e:
            await ctx.deny(f"Failed to create rule: {str(e)}")
    
    @automod_profile.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def profile_add(self, ctx, rule_id: str, *keywords: str):
        if not keywords:
            return await ctx.deny("You need to provide at least one keyword")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type != discord.AutoModRuleTriggerType.member_profile:
                return await ctx.deny("This rule is not a member profile filter")
            
            current_keywords = list(rule.trigger.keyword_filter) if rule.trigger.keyword_filter else []
            new_keywords = current_keywords + list(keywords)
            
            if len(new_keywords) > 1000:
                return await ctx.deny(f"Maximum 1000 keywords allowed (current: {len(current_keywords)})")
            
            await rule.edit(
                trigger=discord.AutoModTrigger(keyword_filter=new_keywords),
                reason=f"Keywords added by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added {len(keywords)} keyword(s) to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add keywords: {str(e)}")
    
    @automod.group(name="action", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_action(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_action.command(name="block")
    @commands.has_permissions(manage_guild=True)
    async def action_block(self, ctx, rule_id: str, *, message: Optional[str] = None):
        if message and len(message) > 150:
            return await ctx.deny("Custom message must be 150 characters or less")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            actions = list(rule.actions)
            
            if message:
                actions.append(discord.AutoModRuleAction(custom_message=message))
            else:
                actions.append(discord.AutoModRuleAction())
            
            await rule.edit(actions=actions, reason=f"Action added by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully added block message action to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add action: {str(e)}")
    
    @automod_action.command(name="alert")
    @commands.has_permissions(manage_guild=True)
    async def action_alert(self, ctx, rule_id: str, channel: discord.TextChannel):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            actions = list(rule.actions)
            actions.append(discord.AutoModRuleAction(channel_id=channel.id))
            
            await rule.edit(actions=actions, reason=f"Action added by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully added alert action to **{rule.name}** (alerts will be sent to {channel.mention})")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add action: {str(e)}")
    
    @automod_action.command(name="timeout")
    @commands.has_permissions(manage_guild=True, moderate_members=True)
    async def action_timeout(self, ctx, rule_id: str, duration: str):
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = duration[-1]
        
        if unit not in time_units:
            return await ctx.deny("Invalid time unit. Use s, m, h, or d")
        
        try:
            amount = int(duration[:-1])
        except ValueError:
            return await ctx.deny("Invalid duration format")
        
        seconds = amount * time_units[unit]
        
        if seconds > 2419200:
            return await ctx.deny("Maximum timeout duration is 4 weeks (2419200 seconds)")
        
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            if rule.trigger_type not in [discord.AutoModRuleTriggerType.keyword, discord.AutoModRuleTriggerType.mention_spam]:
                return await ctx.deny("Timeout action can only be used with keyword or mention spam filters")
            
            actions = list(rule.actions)
            actions.append(discord.AutoModRuleAction(duration=datetime.timedelta(seconds=seconds)))
            
            await rule.edit(actions=actions, reason=f"Action added by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully added timeout action ({duration}) to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add action: {str(e)}")
    
    @automod_action.command(name="blockinteraction")
    @commands.has_permissions(manage_guild=True)
    async def action_blockinteraction(self, ctx, rule_id: str):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            actions = list(rule.actions)
            actions.append(discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_member_interactions))
            
            await rule.edit(actions=actions, reason=f"Action added by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully added block interaction action to **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to add action: {str(e)}")
    
    @automod.group(name="exempt", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_exempt(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_exempt.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def exempt_role(self, ctx, rule_id: str, role: discord.Role):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            exempt_roles = list(rule.exempt_roles) if rule.exempt_roles else []
            
            if role.id in exempt_roles:
                return await ctx.deny(f"{role.mention} is already exempt from this rule")
            
            if len(exempt_roles) >= 20:
                return await ctx.deny("Maximum 20 exempt roles allowed")
            
            exempt_roles.append(role.id)
            
            await rule.edit(exempt_roles=exempt_roles, reason=f"Role exempted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully exempted {role.mention} from **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to exempt role: {str(e)}")
    
    @automod_exempt.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def exempt_channel(self, ctx, rule_id: str, channel: discord.TextChannel):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            exempt_channels = list(rule.exempt_channels) if rule.exempt_channels else []
            
            if channel.id in exempt_channels:
                return await ctx.deny(f"{channel.mention} is already exempt from this rule")
            
            if len(exempt_channels) >= 50:
                return await ctx.deny("Maximum 50 exempt channels allowed")
            
            exempt_channels.append(channel.id)
            
            await rule.edit(exempt_channels=exempt_channels, reason=f"Channel exempted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully exempted {channel.mention} from **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to exempt channel: {str(e)}")
    
    @automod.group(name="unexempt", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_unexempt(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_unexempt.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def unexempt_role(self, ctx, rule_id: str, role: discord.Role):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            exempt_roles = list(rule.exempt_roles) if rule.exempt_roles else []
            
            if role.id not in exempt_roles:
                return await ctx.deny(f"{role.mention} is not exempt from this rule")
            
            exempt_roles.remove(role.id)
            
            await rule.edit(exempt_roles=exempt_roles, reason=f"Role unexempted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully removed exemption for {role.mention} from **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to unexempt role: {str(e)}")
    
    @automod_unexempt.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def unexempt_channel(self, ctx, rule_id: str, channel: discord.TextChannel):
        try:
            rule = await ctx.guild.fetch_automod_rule(int(rule_id))
            
            exempt_channels = list(rule.exempt_channels) if rule.exempt_channels else []
            
            if channel.id not in exempt_channels:
                return await ctx.deny(f"{channel.mention} is not exempt from this rule")
            
            exempt_channels.remove(channel.id)
            
            await rule.edit(exempt_channels=exempt_channels, reason=f"Channel unexempted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully removed exemption for {channel.mention} from **{rule.name}**")
        except discord.NotFound:
            await ctx.deny(f"Automod rule with ID `{rule_id}` not found")
        except Exception as e:
            await ctx.deny(f"Failed to unexempt channel: {str(e)}")

    
    @automod.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod_setup(self, ctx):
        await ctx.send_help(ctx.command)
    
    @automod_setup.command(name="profanity")
    @commands.has_permissions(manage_guild=True)
    async def setup_profanity(self, ctx, channel: Optional[discord.TextChannel] = None):
        try:
            actions = [discord.AutoModRuleAction()]
            
            if channel:
                actions.append(discord.AutoModRuleAction(channel_id=channel.id))
            
            rule = await ctx.guild.create_automod_rule(
                name="Profanity Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword_preset,
                    presets=discord.AutoModPresets(profanity=True)
                ),
                actions=actions,
                enabled=True,
                reason=f"Quick setup by {ctx.author} ({ctx.author.id})"
            )
            
            msg = f"Successfully created profanity filter with ID `{rule.id}`"
            if channel:
                msg += f"\nAlerts will be sent to {channel.mention}"
            await ctx.approve(msg)
        except Exception as e:
            await ctx.deny(f"Failed to create profanity filter: {str(e)}")
    
    @automod_setup.command(name="spam")
    @commands.has_permissions(manage_guild=True)
    async def setup_spam(self, ctx, channel: Optional[discord.TextChannel] = None):
        try:
            actions = [discord.AutoModRuleAction()]
            
            if channel:
                actions.append(discord.AutoModRuleAction(channel_id=channel.id))
            
            rule = await ctx.guild.create_automod_rule(
                name="Spam Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
                actions=actions,
                enabled=True,
                reason=f"Quick setup by {ctx.author} ({ctx.author.id})"
            )
            
            msg = f"Successfully created spam filter with ID `{rule.id}`"
            if channel:
                msg += f"\nAlerts will be sent to {channel.mention}"
            await ctx.approve(msg)
        except Exception as e:
            await ctx.deny(f"Failed to create spam filter: {str(e)}")
    
    @automod_setup.command(name="mentions")
    @commands.has_permissions(manage_guild=True)
    async def setup_mentions(self, ctx, limit: int, channel: Optional[discord.TextChannel] = None):
        if limit < 1 or limit > 50:
            return await ctx.deny("Mention limit must be between 1 and 50")
        
        try:
            actions = [discord.AutoModRuleAction()]
            
            if channel:
                actions.append(discord.AutoModRuleAction(channel_id=channel.id))
            
            rule = await ctx.guild.create_automod_rule(
                name="Mention Spam Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.mention_spam,
                    mention_limit=limit,
                    mention_raid_protection=True
                ),
                actions=actions,
                enabled=True,
                reason=f"Quick setup by {ctx.author} ({ctx.author.id})"
            )
            
            msg = f"Successfully created mention spam filter with limit {limit} (ID: `{rule.id}`)"
            if channel:
                msg += f"\nAlerts will be sent to {channel.mention}"
            await ctx.approve(msg)
        except Exception as e:
            await ctx.deny(f"Failed to create mention spam filter: {str(e)}")
    
    @automod_setup.command(name="slurs")
    @commands.has_permissions(manage_guild=True)
    async def setup_slurs(self, ctx, channel: Optional[discord.TextChannel] = None):
        try:
            actions = [discord.AutoModRuleAction()]
            
            if channel:
                actions.append(discord.AutoModRuleAction(channel_id=channel.id))
            
            rule = await ctx.guild.create_automod_rule(
                name="Slurs Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword_preset,
                    presets=discord.AutoModPresets(slurs=True)
                ),
                actions=actions,
                enabled=True,
                reason=f"Quick setup by {ctx.author} ({ctx.author.id})"
            )
            
            msg = f"Successfully created slurs filter with ID `{rule.id}`"
            if channel:
                msg += f"\nAlerts will be sent to {channel.mention}"
            await ctx.approve(msg)
        except Exception as e:
            await ctx.deny(f"Failed to create slurs filter: {str(e)}")
    
    @automod.command(name="stats")
    @commands.has_permissions(manage_guild=True)
    async def automod_stats(self, ctx):
        try:
            rules = await ctx.guild.fetch_automod_rules()
            
            if not rules:
                return await ctx.deny("This server has no automod rules")
            
            enabled_count = sum(1 for r in rules if r.enabled)
            disabled_count = len(rules) - enabled_count
            
            trigger_counts = {}
            trigger_names = {
                1: "Keyword",
                3: "Spam",
                4: "Preset",
                5: "Mention Spam",
                6: "Member Profile"
            }
            
            for rule in rules:
                trigger_name = trigger_names.get(rule.trigger_type, "Unknown")
                trigger_counts[trigger_name] = trigger_counts.get(trigger_name, 0) + 1
            
            embed = discord.Embed(
                title="Auto Moderation Statistics",
                color=Config.COLORS.DEFAULT
            )
            
            embed.add_field(
                name="Overview",
                value=f"**Total Rules:** {len(rules)}\n**Enabled:** {enabled_count}\n**Disabled:** {disabled_count}",
                inline=False
            )
            
            if trigger_counts:
                trigger_info = '\n'.join([f"**{name}:** {count}" for name, count in trigger_counts.items()])
                embed.add_field(
                    name="Rules by Type",
                    value=trigger_info,
                    inline=False
                )
            
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.deny(f"Failed to fetch statistics: {str(e)}")
    
    @automod.command(name="export")
    @commands.has_permissions(manage_guild=True)
    async def automod_export(self, ctx):
        try:
            rules = await ctx.guild.fetch_automod_rules()
            
            if not rules:
                return await ctx.deny("This server has no automod rules to export")
            
            export_data = []
            
            for rule in rules:
                rule_data = {
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "event_type": rule.event_type.value,
                    "trigger_type": rule.trigger_type.value,
                    "trigger_metadata": {},
                    "actions": [],
                    "exempt_roles": [str(r) for r in rule.exempt_roles] if rule.exempt_roles else [],
                    "exempt_channels": [str(c) for c in rule.exempt_channels] if rule.exempt_channels else []
                }
                
                if rule.trigger:
                    if hasattr(rule.trigger, 'keyword_filter') and rule.trigger.keyword_filter:
                        rule_data["trigger_metadata"]["keyword_filter"] = list(rule.trigger.keyword_filter)
                    if hasattr(rule.trigger, 'regex_patterns') and rule.trigger.regex_patterns:
                        rule_data["trigger_metadata"]["regex_patterns"] = list(rule.trigger.regex_patterns)
                    if hasattr(rule.trigger, 'presets') and rule.trigger.presets:
                        rule_data["trigger_metadata"]["presets"] = [p.value for p in rule.trigger.presets]
                    if hasattr(rule.trigger, 'allow_list') and rule.trigger.allow_list:
                        rule_data["trigger_metadata"]["allow_list"] = list(rule.trigger.allow_list)
                    if hasattr(rule.trigger, 'mention_limit'):
                        rule_data["trigger_metadata"]["mention_limit"] = rule.trigger.mention_limit
                    if hasattr(rule.trigger, 'mention_raid_protection'):
                        rule_data["trigger_metadata"]["mention_raid_protection"] = rule.trigger.mention_raid_protection
                
                for action in rule.actions:
                    action_data = {"type": action.type.value}
                    if action.metadata:
                        action_data["metadata"] = {}
                        if hasattr(action.metadata, 'channel_id') and action.metadata.channel_id:
                            action_data["metadata"]["channel_id"] = str(action.metadata.channel_id)
                        if hasattr(action.metadata, 'duration_seconds') and action.metadata.duration_seconds:
                            action_data["metadata"]["duration_seconds"] = action.metadata.duration_seconds
                        if hasattr(action.metadata, 'custom_message') and action.metadata.custom_message:
                            action_data["metadata"]["custom_message"] = action.metadata.custom_message
                    rule_data["actions"].append(action_data)
                
                export_data.append(rule_data)
            
            json_data = json.dumps(export_data, indent=2)
            
            if len(json_data) > 1900:
                import io
                file = discord.File(io.BytesIO(json_data.encode()), filename="automod_rules.json")
                await ctx.reply("Exported automod rules:", file=file)
            else:
                await ctx.reply(f"```json\n{json_data}\n```")
        except Exception as e:
            await ctx.deny(f"Failed to export rules: {str(e)}")
    
    @automod.command(name="import")
    @commands.has_permissions(manage_guild=True)
    async def automod_import(self, ctx, *, json_data: str = None):
        if not json_data and not ctx.message.attachments:
            return await ctx.deny("You need to provide JSON data or attach a JSON file")
        
        try:
            if ctx.message.attachments:
                attachment = ctx.message.attachments[0]
                if not attachment.filename.endswith('.json'):
                    return await ctx.deny("Attachment must be a JSON file")
                json_data = (await attachment.read()).decode('utf-8')
            else:
                json_data = json_data.strip('`').strip()
                if json_data.startswith('json'):
                    json_data = json_data[4:].strip()
            
            rules_data = json.loads(json_data)
            
            if not isinstance(rules_data, list):
                return await ctx.deny("Invalid JSON format. Expected a list of rules")
            
            created_count = 0
            failed_count = 0
            
            for rule_data in rules_data:
                try:
                    trigger_metadata = None
                    if rule_data.get("trigger_metadata"):
                        metadata_dict = rule_data["trigger_metadata"]
                        
                        presets = None
                        if metadata_dict.get("presets"):
                            preset_flags = {}
                            for p in metadata_dict.get("presets", []):
                                if p == 1:
                                    preset_flags["profanity"] = True
                                elif p == 2:
                                    preset_flags["sexual_content"] = True
                                elif p == 3:
                                    preset_flags["slurs"] = True
                            presets = discord.AutoModPresets(**preset_flags) if preset_flags else None
                        
                        trigger_metadata = discord.AutoModTrigger(
                            type=discord.AutoModRuleTriggerType(rule_data["trigger_type"]),
                            keyword_filter=metadata_dict.get("keyword_filter"),
                            regex_patterns=metadata_dict.get("regex_patterns"),
                            presets=presets,
                            allow_list=metadata_dict.get("allow_list"),
                            mention_limit=metadata_dict.get("mention_limit"),
                            mention_raid_protection=metadata_dict.get("mention_raid_protection")
                        )
                    
                    actions = []
                    for action_data in rule_data.get("actions", []):
                        action_metadata = None
                        if action_data.get("metadata"):
                            meta = action_data["metadata"]
                            action_metadata = discord.AutoModActionMetadata(
                                channel_id=int(meta["channel_id"]) if meta.get("channel_id") else None,
                                duration_seconds=meta.get("duration_seconds"),
                                custom_message=meta.get("custom_message")
                            )
                        action_type = discord.AutoModRuleActionType(action_data["type"])
                        if action_type == discord.AutoModRuleActionType.send_alert_message and action_metadata:
                            actions.append(discord.AutoModRuleAction(channel_id=int(meta["channel_id"])))
                        elif action_type == discord.AutoModRuleActionType.timeout and action_metadata:
                            actions.append(discord.AutoModRuleAction(duration=datetime.timedelta(seconds=meta.get("duration_seconds"))))
                        elif action_type == discord.AutoModRuleActionType.block_message and meta.get("custom_message"):
                            actions.append(discord.AutoModRuleAction(custom_message=meta.get("custom_message")))
                        else:
                            actions.append(discord.AutoModRuleAction(type=action_type))
                    
                    await ctx.guild.create_automod_rule(
                        name=rule_data["name"],
                        event_type=discord.AutoModRuleEventType(rule_data["event_type"]),
                        trigger=trigger_metadata,
                        actions=actions,
                        enabled=rule_data.get("enabled", True),
                        exempt_roles=[int(r) for r in rule_data.get("exempt_roles", [])],
                        exempt_channels=[int(c) for c in rule_data.get("exempt_channels", [])],
                        reason=f"Imported by {ctx.author} ({ctx.author.id})"
                    )
                    created_count += 1
                except Exception:
                    failed_count += 1
            
            msg = f"Successfully imported {created_count} rule(s)"
            if failed_count > 0:
                msg += f"\nFailed to import {failed_count} rule(s)"
            await ctx.approve(msg)
        except json.JSONDecodeError:
            await ctx.deny("Invalid JSON format")
        except Exception as e:
            await ctx.deny(f"Failed to import rules: {str(e)}")

async def setup(bot):
    await bot.add_cog(AutoMod(bot))

