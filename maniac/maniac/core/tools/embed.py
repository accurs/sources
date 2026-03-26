import discord
from discord.ext import commands
import re
from datetime import datetime

class EmbedBuilder:
    @staticmethod
    def ordinal(num: int) -> str:
        numb = str(num)
        if numb.startswith("0"):
            numb = numb.strip("0")
        if numb in ["11", "12", "13"]:
            return numb + "th"
        if numb.endswith("1"):
            return numb + "st"
        elif numb.endswith("2"):
            return numb + "nd"
        elif numb.endswith("3"):
            return numb + "rd"
        else:
            return numb + "th"
    
    @staticmethod
    def embed_replacement(user: discord.Member, params: str = None) -> str:
        if params is None:
            return None
        
        if "{user}" in params:
            params = params.replace("{user}", str(user))
        if "{user.mention}" in params:
            params = params.replace("{user.mention}", user.mention)
        if "{user.name}" in params:
            params = params.replace("{user.name}", user.name)
        if "{user.id}" in params:
            params = params.replace("{user.id}", str(user.id))
        if "{user.avatar}" in params:
            params = params.replace("{user.avatar}", str(user.display_avatar.url))
        if "{user.discriminator}" in params:
            params = params.replace("{user.discriminator}", user.discriminator)
        if "{user.display_name}" in params:
            params = params.replace("{user.display_name}", user.display_name)
        if "{user.nickname}" in params:
            params = params.replace("{user.nickname}", user.nick if hasattr(user, 'nick') and user.nick else user.name)
        if "{user.bot}" in params:
            params = params.replace("{user.bot}", "Yes" if user.bot else "No")
        
        if hasattr(user, 'joined_at') and user.joined_at:
            if "{user.joined_at}" in params:
                params = params.replace("{user.joined_at}", discord.utils.format_dt(user.joined_at, style="R"))
            if "{user.join_position}" in params:
                if hasattr(user, 'guild'):
                    members = sorted(user.guild.members, key=lambda m: m.joined_at)
                    position = members.index(user) + 1
                    params = params.replace("{user.join_position}", str(position))
            if "{user.join_position.format}" in params:
                if hasattr(user, 'guild'):
                    members = sorted(user.guild.members, key=lambda m: m.joined_at)
                    position = members.index(user) + 1
                    params = params.replace("{user.join_position.format}", EmbedBuilder.ordinal(position))
        
        if "{user.created_at}" in params:
            params = params.replace("{user.created_at}", discord.utils.format_dt(user.created_at, style="R"))
        
        if hasattr(user, 'premium_since') and user.premium_since:
            if "{user.boost}" in params:
                params = params.replace("{user.boost}", "Yes")
            if "{user.boosted_at}" in params:
                params = params.replace("{user.boosted_at}", discord.utils.format_dt(user.premium_since, style="R"))
        else:
            if "{user.boost}" in params:
                params = params.replace("{user.boost}", "No")
            if "{user.boosted_at}" in params:
                params = params.replace("{user.boosted_at}", "Never")
        
        if hasattr(user, 'guild') and user.guild:
            if "{guild}" in params:
                params = params.replace("{guild}", user.guild.name)
            if "{guild.name}" in params:
                params = params.replace("{guild.name}", user.guild.name)
            if "{guild.id}" in params:
                params = params.replace("{guild.id}", str(user.guild.id))
            if "{guild.count}" in params:
                params = params.replace("{guild.count}", str(user.guild.member_count))
            if "{guild.members}" in params:
                params = params.replace("{guild.members}", str(user.guild.member_count))
            if "{guild.count.format}" in params:
                params = params.replace("{guild.count.format}", EmbedBuilder.ordinal(user.guild.member_count))
            if "{guild.icon}" in params:
                if user.guild.icon:
                    params = params.replace("{guild.icon}", user.guild.icon.url)
                else:
                    params = params.replace("{guild.icon}", "")
            if "{guild.banner}" in params:
                if user.guild.banner:
                    params = params.replace("{guild.banner}", user.guild.banner.url)
                else:
                    params = params.replace("{guild.banner}", "")
            if "{guild.splash}" in params:
                if user.guild.splash:
                    params = params.replace("{guild.splash}", user.guild.splash.url)
                else:
                    params = params.replace("{guild.splash}", "")
            if "{guild.created_at}" in params:
                params = params.replace("{guild.created_at}", discord.utils.format_dt(user.guild.created_at, style="R"))
            if "{guild.boost_count}" in params:
                params = params.replace("{guild.boost_count}", str(user.guild.premium_subscription_count))
            if "{guild.booster_count}" in params:
                params = params.replace("{guild.booster_count}", str(len(user.guild.premium_subscribers)))
            if "{guild.boost_count.format}" in params:
                params = params.replace("{guild.boost_count.format}", EmbedBuilder.ordinal(user.guild.premium_subscription_count))
            if "{guild.booster_count.format}" in params:
                params = params.replace("{guild.booster_count.format}", EmbedBuilder.ordinal(len(user.guild.premium_subscribers)))
            if "{guild.boost_tier}" in params:
                params = params.replace("{guild.boost_tier}", str(user.guild.premium_tier))
            if "{guild.vanity}" in params:
                params = params.replace("{guild.vanity}", f"/{user.guild.vanity_url_code}" if user.guild.vanity_url_code else "none")
            if "{guild.owner}" in params:
                params = params.replace("{guild.owner}", str(user.guild.owner))
            if "{guild.owner.id}" in params:
                params = params.replace("{guild.owner.id}", str(user.guild.owner_id))
            if "{guild.owner.mention}" in params:
                params = params.replace("{guild.owner.mention}", user.guild.owner.mention if user.guild.owner else "Unknown")
            if "{guild.channels}" in params:
                params = params.replace("{guild.channels}", str(len(user.guild.channels)))
            if "{guild.text_channels}" in params:
                params = params.replace("{guild.text_channels}", str(len(user.guild.text_channels)))
            if "{guild.voice_channels}" in params:
                params = params.replace("{guild.voice_channels}", str(len(user.guild.voice_channels)))
            if "{guild.categories}" in params:
                params = params.replace("{guild.categories}", str(len(user.guild.categories)))
            if "{guild.roles}" in params:
                params = params.replace("{guild.roles}", str(len(user.guild.roles)))
            if "{guild.emojis}" in params:
                params = params.replace("{guild.emojis}", str(len(user.guild.emojis)))
        
        if "{invisible}" in params:
            params = params.replace("{invisible}", "2B2D31")
        if "{botcolor}" in params:
            params = params.replace("{botcolor}", "7d7ead")
        
        return params
    
    @staticmethod
    def get_parts(params: str) -> list:
        params = params.replace("{embed}", "")
        return [p[1:][:-1] for p in params.split("$v")]
    
    @staticmethod
    def to_object(params: str) -> tuple:
        x = {}
        fields = []
        content = None
        view = discord.ui.View()
        
        for part in EmbedBuilder.get_parts(params):
            if part.startswith("content:"):
                content = part[len("content:"):]
            
            if part.startswith("title:"):
                x["title"] = part[len("title:"):]
            
            if part.startswith("description:"):
                x["description"] = part[len("description:"):]
            
            if part.startswith("color:"):
                try:
                    x["color"] = int(part[len("color:"):].replace("#", ""), 16)
                except:
                    x["color"] = 0x2F3136
            
            if part.startswith("image:"):
                x["image"] = {"url": part[len("image:"):]}
            
            if part.startswith("thumbnail:"):
                x["thumbnail"] = {"url": part[len("thumbnail:"):]}
            
            if part.startswith("author:"):
                z = part[len("author:"):].split(" && ")
                name = z[0] if len(z) > 0 else None
                icon_url = z[1] if len(z) > 1 else None
                url = z[2] if len(z) > 2 else None
                
                x["author"] = {"name": name}
                if icon_url:
                    x["author"]["icon_url"] = icon_url
                if url:
                    x["author"]["url"] = url
            
            if part.startswith("field:"):
                z = part[len("field:"):].split(" && ")
                name = z[0] if len(z) > 0 else None
                value = z[1] if len(z) > 1 else None
                inline = z[2] if len(z) > 2 else True
                
                if isinstance(inline, str):
                    inline = inline.lower() == "true"
                
                fields.append({"name": name, "value": value, "inline": inline})
            
            if part.startswith("footer:"):
                z = part[len("footer:"):].split(" && ")
                text = z[0] if len(z) > 0 else None
                icon_url = z[1] if len(z) > 1 else None
                
                x["footer"] = {"text": text}
                if icon_url:
                    x["footer"]["icon_url"] = icon_url
            
            if part.startswith("button:"):
                z = part[len("button:"):].split(" && ")
                disabled = True
                style = discord.ButtonStyle.gray
                emoji = None
                label = None
                url = None
                
                for m in z:
                    if "label:" in m:
                        label = m.replace("label:", "")
                    if "url:" in m:
                        url = m.replace("url:", "").strip()
                        disabled = False
                    if "emoji:" in m:
                        emoji = m.replace("emoji:", "").strip()
                    if "disabled" in m:
                        disabled = True
                    if "style:" in m:
                        style_str = m.replace("style:", "").strip()
                        if style_str == "red":
                            style = discord.ButtonStyle.red
                        elif style_str == "green":
                            style = discord.ButtonStyle.green
                        elif style_str == "gray":
                            style = discord.ButtonStyle.gray
                        elif style_str == "blue":
                            style = discord.ButtonStyle.blurple
                
                view.add_item(
                    discord.ui.Button(
                        style=style,
                        label=label,
                        emoji=emoji,
                        url=url,
                        disabled=disabled
                    )
                )
        
        if not x:
            embed = None
        else:
            x["fields"] = fields
            embed = discord.Embed.from_dict(x)
        
        return content, embed, view

class EmbedScript(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        x = EmbedBuilder.to_object(EmbedBuilder.embed_replacement(ctx.author, argument))
        
        if x[0] or x[1]:
            return {
                "content": x[0],
                "embed": x[1],
                "view": x[2]
            }
        
        return {
            "content": EmbedBuilder.embed_replacement(ctx.author, argument)
        }

async def send_embed(destination, message: str, member: discord.Member):
    processed_message = EmbedBuilder.embed_replacement(member, message)
    
    if "{embed}" not in message:
        return await destination.send(processed_message)
    
    content, embed, view = EmbedBuilder.to_object(processed_message)
    
    await destination.send(
        content=content,
        embed=embed,
        view=view if view.children else None
    )
