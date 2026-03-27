import discord, jishaku, os, sys, traceback, asyncpg, datetime, asyncio, aiohttp, json, time, secrets, string

from discord import User, Message
from pathlib import Path
from typing import Optional
from .session import Session
from .helpers import NeoContext, HelpCommand
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

class Evy(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=",",
            shard_count=1,
            intents=discord.Intents.all(),
            case_insensitive=True,
            help_command=HelpCommand(),
            activity=discord.Activity(type=discord.ActivityType.watching, name="over you"),
            status=discord.Status.idle,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            owner_ids={513684550753320971, 713128996287807600, 1280856653230505994}
        )
        self.mcd = commands.CooldownMapping.from_cooldown(
            4, 5, commands.BucketType.user
        ) 
        self.ccd = commands.CooldownMapping.from_cooldown(
            4, 5, commands.BucketType.channel
        )
        self.gcd = commands.CooldownMapping.from_cooldown(
            1, 5, commands.BucketType.guild
        )
        self.yes = "<:yes:1110790866444418098>"
        self.no = "<:no:1110790867824417864>"
        self.warning = "<:warning:1110790865174419486>"
        self.session = Session()
        self.color = 0x3d2d3f
        self.uptime = time.time()
        self.error_cache = {}

    async def create_db_pool(self):
        self.db = await asyncpg.create_pool(
            user="postgres.lzyfrwblyiyvkovnrhud",
            password="xD3FZY1olkMfplsQ",
            database="postgres",
            host="aws-1-eu-central-1.pooler.supabase.com",
            port="6543",
            statement_cache_size=0,
        )

    async def get_context(self, message, *, cls=NeoContext):
        return await super().get_context(message, cls=cls) 

    async def load_schema(self):
        schema_path = Path("start/schema.sql")

        if not schema_path.exists():
            print("Schema file not found.")
            return

        schema = schema_path.read_text()

        async with self.db.acquire() as conn:
            for query in schema.split(";"):
                query = query.strip()
                if query:
                    await conn.execute(query)

        print("Database schema loaded.")

    async def setup_hook(self) -> None:
        await self.create_db_pool()
        await self.load_schema()
        await self.load_extension("jishaku")

        for filename in os.listdir("./disk"):
            if filename.endswith(".py"):
                await self.load_extension(f"disk.{filename[:-3]}")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} command(s)")

    def convert_datetime(self, date: datetime.datetime=None):
        if date is None: return None  
        month = f'0{date.month}' if date.month < 10 else date.month 
        day = f'0{date.day}' if date.day < 10 else date.day 
        year = date.year 
        minute = f'0{date.minute}' if date.minute < 10 else date.minute 
        if date.hour < 10: 
            hour = f'0{date.hour}'
            meridian = "AM"
        elif date.hour > 12: 
            hour = f'0{date.hour - 12}' if date.hour - 12 < 10 else f"{date.hour - 12}"
            meridian = "PM"
        else: 
            hour = date.hour
            meridian = "PM"  
        return f"{month}/{day}/{year} at {hour}:{minute} {meridian} ({discord.utils.format_dt(date, style='R')})" 

    def ordinal(self, num: int) -> str:
        numb = str(num) 
        if numb.startswith("0"): numb = numb.strip('0')
        if numb in ["11", "12", "13"]: return numb + "th"
        if numb.endswith("1"): return numb + "st"
        elif numb.endswith("2"):  return numb + "nd"
        elif numb.endswith("3"): return numb + "rd"
        else: return numb + "th" 

    def generate_error_id(self, length: int = 10) -> str:
        letters = string.ascii_letters
        return "".join(secrets.choice(letters) for _ in range(length))

    async def on_command_error(self, ctx, error):
        error = getattr(error, "original", error)

        if hasattr(ctx.command, "on_error"):
            return

        if ctx.command and ctx.command.hidden:
            return

        embed = discord.Embed(color=self.color, timestamp=datetime.datetime.utcnow())
        error_id = self.generate_error_id(10)

        trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        self.error_cache[error_id] = (
            f"[{datetime.datetime.utcnow()}] {error_id}\n"
            f"Command: {ctx.command}\n"
            f"User: {ctx.author} ({ctx.author.id})\n"
            f"Guild: {ctx.guild}\n"
            f"{trace}"
        )
        if len(self.error_cache) > 200:
            oldest_key = next(iter(self.error_cache))
            self.error_cache.pop(oldest_key, None)

        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "Missing Argument"
            embed.description = f"`{error.param.name}` is required."

        elif isinstance(error, commands.BadArgument):
            embed.title = "Invalid Argument"
            embed.description = "Invalid argument provided."

        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Cooldown"
            embed.description = f"Retry in `{round(error.retry_after, 2)}s`."

        elif isinstance(error, commands.MissingPermissions):
            embed.title = "Permission Denied"
            embed.description = f"Missing: `{', '.join(error.missing_permissions)}`."

        elif isinstance(error, commands.BotMissingPermissions):
            embed.title = "Bot Missing Permissions"
            embed.description = f"Need: `{', '.join(error.missing_permissions)}`."

        elif isinstance(error, commands.NotOwner):
            return

        elif isinstance(error, commands.CheckFailure):
            embed.title = "Check Failed"
            embed.description = "You cannot use this command."

        elif isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, discord.Forbidden):
            embed.title = "Forbidden"
            embed.description = "Missing permissions to execute."

        elif isinstance(error, discord.HTTPException):
            embed.title = "HTTP Error"
            embed.description = "Discord API error occurred."

        else:
            embed.title = "Error"
            embed.description = "Unexpected error"

            with open("errors.log", "a", encoding="utf-8") as f:
                f.write(
                    f"\n[{datetime.datetime.utcnow()}] {error_id}\n"
                    f"Command: {ctx.command}\n"
                    f"User: {ctx.author} ({ctx.author.id})\n"
                    f"Guild: {ctx.guild}\n"
                    f"{''.join(traceback.format_exception(type(error), error, error.__traceback__))}\n"
                )

        embed.description = f"{embed.description}\n-# Error: **{error_id}**"

        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            pass


evy = Evy()
evy.run(os.getenv("TOKEN"))