import discord
from discord.ext import commands
from .config import Config
from .database import db
from .tools.context import CustomContext
from .events import setup_events
from .loader import load_cogs
import os

os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "False"
os.environ["JISHAKU_HIDE"] = "True"

intents = discord.Intents.all()

async def get_prefix(bot, message):
    return Config.PREFIX

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None,
    owner_ids={1460003194771083296, 1285277569113133161}
)

async def get_context(message, *, cls=CustomContext):
    return await super(commands.Bot, bot).get_context(message, cls=cls)

bot.get_context = get_context

@bot.event
async def setup_hook():
    await db.connect()
    bot.db = db
    await setup_events(bot)
    await bot.load_extension("jishaku")
    await load_cogs(bot)

