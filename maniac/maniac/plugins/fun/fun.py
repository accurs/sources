import discord
from discord.ext import commands
import aiohttp
import io
import random
from maniac.core.config import Config
from maniac.core.command_example import example

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="makemp3", help="Convert video to MP3")
    @example(",makemp3")
    async def makemp3(self, ctx):
        if not ctx.message.reference and not ctx.message.attachments:
            return await ctx.deny("Please reply to a message with a video or attach a video")
        
        video_url = None
        
        if ctx.message.reference:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.attachments:
                    attachment = ref_msg.attachments[0]
                    if attachment.content_type and "video" in attachment.content_type:
                        video_url = attachment.url
            except:
                pass
        
        if not video_url and ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and "video" in attachment.content_type:
                video_url = attachment.url
        
        if not video_url:
            return await ctx.deny("No video found")
        
        await ctx.loading("Converting video to MP3...")
        
        try:
            import subprocess
            import tempfile
            import os
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as r:
                    if r.status != 200:
                        return await ctx.deny("Failed to download video")
                    video_data = await r.read()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as video_file:
                video_file.write(video_data)
                video_path = video_file.name
            
            audio_path = video_path.replace(".mp4", ".mp3")
            
            subprocess.run([
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "libmp3lame",
                "-q:a", "2", audio_path
            ], check=True, capture_output=True)
            
            if os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                if file_size > 8 * 1024 * 1024:
                    os.remove(video_path)
                    os.remove(audio_path)
                    return await ctx.deny("The converted file is too large to send (max 8MB)")
                
                with open(audio_path, "rb") as f:
                    await ctx.send(file=discord.File(f, filename="audio.mp3"))
                
                os.remove(video_path)
                os.remove(audio_path)
            else:
                os.remove(video_path)
                return await ctx.deny("Failed to convert video")
        except subprocess.CalledProcessError:
            return await ctx.deny("FFmpeg is not installed or conversion failed")
        except Exception as e:
            return await ctx.deny(f"An error occurred: {str(e)}")
    
    @commands.command(name="duckduckgo", aliases=["ddg", "search"], help="Search DuckDuckGo")
    @example(",duckduckgo python programming")
    async def duckduckgo(self, ctx, *, query: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1"
                }
            ) as r:
                if r.status != 200:
                    return await ctx.deny("Failed to search DuckDuckGo")
                
                data = await r.json()
        
        abstract = data.get("Abstract", "")
        abstract_url = data.get("AbstractURL", "")
        heading = data.get("Heading", query)
        image = data.get("Image", "")
        
        if not abstract and not data.get("RelatedTopics"):
            return await ctx.deny(f"No results found for `{query}`")
        
        embed = discord.Embed(
            title=heading,
            description=abstract[:2000] if abstract else "No description available",
            url=abstract_url if abstract_url else None,
            color=Config.COLORS.DEFAULT
        )
        
        if image:
            embed.set_thumbnail(url=f"https://duckduckgo.com{image}")
        
        if data.get("RelatedTopics"):
            related = []
            for topic in data["RelatedTopics"][:5]:
                if isinstance(topic, dict) and "Text" in topic:
                    text = topic["Text"][:100]
                    url = topic.get("FirstURL", "")
                    if url:
                        related.append(f"[{text}]({url})")
                    else:
                        related.append(text)
            
            if related:
                embed.add_field(
                    name="Related Topics",
                    value="\n".join(related),
                    inline=False
                )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="8ball", help="Ask the magic 8ball a question")
    @example(",8ball Will I win the lottery?")
    async def eightball(self, ctx, *, question: str):
        responses = [
            "It is certain", "It is decidedly so", "Without a doubt",
            "Yes definitely", "You may rely on it", "As I see it, yes",
            "Most likely", "Outlook good", "Yes", "Signs point to yes",
            "Reply hazy, try again", "Ask again later", "Better not tell you now",
            "Cannot predict now", "Concentrate and ask again",
            "Don't count on it", "My reply is no", "My sources say no",
            "Outlook not so good", "Very doubtful"
        ]
        
        embed = discord.Embed(
            title="🎱 Magic 8Ball",
            color=Config.COLORS.DEFAULT
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="coinflip", aliases=["flip"], help="Flip a coin")
    @example(",coinflip")
    async def coinflip(self, ctx):
        result = random.choice(["Heads", "Tails"])
        
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"The coin landed on **{result}**!",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="roll", aliases=["dice"], help="Roll a dice")
    @example(",roll 20")
    async def roll(self, ctx, sides: int = 6):
        if sides < 2:
            return await ctx.deny("Dice must have at least 2 sides")
        if sides > 100:
            return await ctx.deny("Dice cannot have more than 100 sides")
        
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title=f"🎲 Dice Roll (d{sides})",
            description=f"You rolled a **{result}**!",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="choose", aliases=["pick"], help="Choose between multiple options")
    @example(",choose pizza, burger, tacos")
    async def choose(self, ctx, *, options: str):
        choices = [choice.strip() for choice in options.split(",")]
        
        if len(choices) < 2:
            return await ctx.deny("Please provide at least 2 options separated by commas")
        
        choice = random.choice(choices)
        
        embed = discord.Embed(
            title="🤔 Choice",
            description=f"I choose: **{choice}**",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="reverse", help="Reverse text")
    @example(",reverse Hello World")
    async def reverse(self, ctx, *, text: str):
        reversed_text = text[::-1]
        
        if len(reversed_text) > 2000:
            return await ctx.deny("Reversed text is too long")
        
        await ctx.reply(reversed_text)
    
    @commands.command(name="mock", aliases=["spongebob"], help="MoCk TeXt LiKe ThIs")
    @example(",mock this is a test")
    async def mock(self, ctx, *, text: str):
        mocked = "".join(
            char.upper() if i % 2 == 0 else char.lower()
            for i, char in enumerate(text)
        )
        
        if len(mocked) > 2000:
            return await ctx.deny("Mocked text is too long")
        
        await ctx.reply(mocked)
    
    @commands.command(name="rate", help="Rate something out of 10")
    @example(",rate Discord")
    async def rate(self, ctx, *, thing: str):
        rating = random.randint(0, 10)
        
        embed = discord.Embed(
            title="⭐ Rating",
            description=f"I'd rate **{thing}** a **{rating}/10**",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="ascii", help="Convert text to ASCII art")
    @example(",ascii HELLO")
    async def ascii(self, ctx, *, text: str):
        if len(text) > 10:
            return await ctx.deny("Text must be 10 characters or less")
        
        ascii_art = {
            'a': ['  ▄▀█  ', ' █▀█  ', ' ▀ ▀  '],
            'b': [' █▀▄  ', ' █▀▄  ', ' ▀▀   '],
            'c': ['  ▄▀▀  ', ' █    ', '  ▀▀▀ '],
            'd': [' █▀▄  ', ' █ █  ', ' ▀▀   '],
            'e': [' █▀▀  ', ' █▀▀  ', ' ▀▀▀  '],
            'f': [' █▀▀  ', ' █▀   ', ' ▀    '],
            'g': ['  ▄▀▀  ', ' █ ▀█ ', '  ▀▀▀ '],
            'h': [' █ █  ', ' █▀█  ', ' ▀ ▀  '],
            'i': [' █  ', ' █  ', ' ▀  '],
            'j': ['   █  ', '   █  ', ' ▀▀   '],
            'k': [' █ ▄▀ ', ' █▀▄  ', ' ▀ ▀  '],
            'l': [' █    ', ' █    ', ' ▀▀▀  '],
            'm': [' █▄ ▄█ ', ' █ ▀ █ ', ' ▀   ▀ '],
            'n': [' █▄ █ ', ' █ ▀█ ', ' ▀  ▀ '],
            'o': ['  ▄▀▄  ', ' █ █  ', '  ▀▀   '],
            'p': [' █▀▀  ', ' █▀▀  ', ' ▀    '],
            'q': ['  ▄▀▄  ', ' █ █  ', '  ▀▀█ '],
            'r': [' █▀▄  ', ' █▀▄  ', ' ▀ ▀  '],
            's': ['  ▄▀▀  ', '  ▀▄   ', ' ▀▀   '],
            't': [' ▀█▀  ', '  █   ', '  ▀   '],
            'u': [' █ █  ', ' █ █  ', '  ▀▀  '],
            'v': [' █ █  ', ' █ █  ', '  ▀   '],
            'w': [' █   █ ', ' █ █ █ ', '  ▀▀▀  '],
            'x': [' ▀▄ ▄▀ ', '  █▄█  ', ' ▄▀ ▀▄ '],
            'y': [' █ █  ', '  █   ', '  ▀   '],
            'z': [' ▀▀█  ', '  █   ', ' ▀▀▀  '],
            ' ': ['    ', '    ', '    ']
        }
        
        lines = ['', '', '']
        for char in text.lower():
            if char in ascii_art:
                for i in range(3):
                    lines[i] += ascii_art[char][i]
            else:
                for i in range(3):
                    lines[i] += '  '
        
        result = '\n'.join(lines)
        
        if len(result) > 2000:
            return await ctx.deny("ASCII art is too long")
        
        await ctx.reply(f"```\n{result}\n```")

async def setup(bot):
    await bot.add_cog(Fun(bot))
