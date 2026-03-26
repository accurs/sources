from __future__ import annotations

import json
from pathlib import Path
from random import choice
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from bot.helpers.context import TormentContext, _color

with open(Path(__file__).parent / "actions.json") as f:
    ACTIONS: dict[str, dict[str, str]] = json.load(f)

NSFW_ACTIONS = {"anal", "blowjob", "cum", "fuck", "pussylick"}

BASE_URL = "https://api.otakugifs.xyz/gif"
NSFW_BASE = "https://purrbot.site/api/img/nsfw"

EMBED_COLOR = _color("EMBED_INFO_COLOR")


class Roleplay(commands.Cog):
    __cog_name__ = "roleplay"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    @property
    def storage(self):
        return self.bot.storage

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_gif(self, action: str, nsfw: bool = False) -> str | None:
        session = await self._get_session()
        try:
            if nsfw:
                url = f"{NSFW_BASE}/{action}/gif"
                async with session.get(url) as resp:
                    data = await resp.json()
                    return data.get("link")
            else:
                async with session.get(BASE_URL, params={"reaction": action}) as resp:
                    data = await resp.json()
                    return data.get("url")
        except Exception:
            return None

    async def _get_count(self, action: str, author_id: int, target_id: int) -> int:
        await self.storage.pool.execute(
            """
            INSERT INTO roleplay_counts (action, author_id, target_id, count)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (action, author_id, target_id)
            DO UPDATE SET count = roleplay_counts.count + 1
            """,
            action, author_id, target_id,
        )
        return await self.storage.pool.fetchval(
            "SELECT count FROM roleplay_counts WHERE action = $1 AND author_id = $2 AND target_id = $3",
            action, author_id, target_id,
        )

    def _ordinal(self, n: int) -> str:
        suffix = ["th", "st", "nd", "rd", "th"][min(n % 10, 4)] if n % 100 not in (11, 12, 13) else "th"
        return f"{n}{suffix}"

    async def _do_roleplay(self, ctx: TormentContext, target: discord.Member, action: str) -> None:
        nsfw = action in NSFW_ACTIONS
        if nsfw and not ctx.channel.is_nsfw():
            return await ctx.warn("This command can only be used in **NSFW** channels.")

        gif = await self._fetch_gif(action, nsfw=nsfw)
        if not gif:
            return await ctx.warn("Something went wrong while fetching the GIF.")

        action_data = ACTIONS[action]
        self_action = ctx.author.id == target.id

        if self_action:
            suffix = f".. {choice(['sus', 'wtf', 'lol?'])}"
            target_text = "themselves"
        else:
            count = await self._get_count(action, ctx.author.id, target.id)
            suffix = f" for the **{self._ordinal(count)}** time!"
            target_text = target.mention

        embed = discord.Embed(
            description=f"{ctx.author.mention} **{action_data['message']}** {target_text}{suffix}",
            color=EMBED_COLOR,
        )
        embed.set_image(url=gif)
        await ctx.reply(embed=embed)

    @commands.command(
        name="roleplay",
        aliases=["rpstats", "rp"],
        help="Check roleplay stats with someone",
        extras={"parameters": "member", "usage": "roleplay (member)"},
    )
    async def roleplay_stats(self, ctx: TormentContext, target: discord.Member) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT action, count FROM roleplay_counts WHERE author_id = $1 AND target_id = $2",
            ctx.author.id, target.id,
        )
        if not rows:
            return await ctx.warn(f"You haven't roleplayed with {target.mention} yet.")

        sorted_rows = sorted(rows, key=lambda r: r["count"], reverse=True)
        parts = []
        for row in sorted_rows:
            action = row["action"]
            count = row["count"]
            plural = ("es" if action.endswith("s") else "s") if count > 1 else ""
            parts.append(f"{count} {action}{plural}")

        joined = ", ".join(parts[:-1]) + (f" and {parts[-1]}" if len(parts) > 1 else parts[0])
        embed = discord.Embed(
            description=f"You have roleplayed **{joined}** with {target.mention}",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed)


    @commands.command(name="airkiss", help=ACTIONS["airkiss"]["description"], extras={"parameters": "[member]", "usage": "airkiss [member]"})
    async def airkiss(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "airkiss")

    @commands.command(name="angrystare", help=ACTIONS["angrystare"]["description"], extras={"parameters": "[member]", "usage": "angrystare [member]"})
    async def angrystare(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "angrystare")

    @commands.command(name="anal", help=ACTIONS["anal"]["description"], extras={"parameters": "[member]", "usage": "anal [member]"})
    async def anal(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "anal")

    @commands.command(name="bite", help=ACTIONS["bite"]["description"], extras={"parameters": "[member]", "usage": "bite [member]"})
    async def bite(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "bite")

    @commands.command(name="bleh", help=ACTIONS["bleh"]["description"], extras={"parameters": "[member]", "usage": "bleh [member]"})
    async def bleh(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "bleh")

    @commands.command(name="blush", help=ACTIONS["blush"]["description"], extras={"parameters": "[member]", "usage": "blush [member]"})
    async def blush(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "blush")

    @commands.command(name="blowjob", help=ACTIONS["blowjob"]["description"], extras={"parameters": "[member]", "usage": "blowjob [member]"})
    async def blowjob(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "blowjob")

    @commands.command(name="brofist", help=ACTIONS["brofist"]["description"], extras={"parameters": "[member]", "usage": "brofist [member]"})
    async def brofist(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "brofist")

    @commands.command(name="celebrate", help=ACTIONS["celebrate"]["description"], extras={"parameters": "[member]", "usage": "celebrate [member]"})
    async def celebrate(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "celebrate")

    @commands.command(name="cheers", help=ACTIONS["cheers"]["description"], extras={"parameters": "[member]", "usage": "cheers [member]"})
    async def cheers(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "cheers")

    @commands.command(name="clap", help=ACTIONS["clap"]["description"], extras={"parameters": "[member]", "usage": "clap [member]"})
    async def clap(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "clap")

    @commands.command(name="confused", help=ACTIONS["confused"]["description"], extras={"parameters": "[member]", "usage": "confused [member]"})
    async def confused(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "confused")

    @commands.command(name="cool", help=ACTIONS["cool"]["description"], extras={"parameters": "[member]", "usage": "cool [member]"})
    async def cool(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "cool")

    @commands.command(name="cry", help=ACTIONS["cry"]["description"], extras={"parameters": "[member]", "usage": "cry [member]"})
    async def cry(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "cry")

    @commands.command(name="cuddle", help=ACTIONS["cuddle"]["description"], extras={"parameters": "[member]", "usage": "cuddle [member]"})
    async def cuddle(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "cuddle")

    @commands.command(name="cum", help=ACTIONS["cum"]["description"], extras={"parameters": "[member]", "usage": "cum [member]"})
    async def cum(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "cum")

    @commands.command(name="dance", help=ACTIONS["dance"]["description"], extras={"parameters": "[member]", "usage": "dance [member]"})
    async def dance(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "dance")

    @commands.command(name="drool", help=ACTIONS["drool"]["description"], extras={"parameters": "[member]", "usage": "drool [member]"})
    async def drool(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "drool")

    @commands.command(name="evillaugh", help=ACTIONS["evillaugh"]["description"], extras={"parameters": "[member]", "usage": "evillaugh [member]"})
    async def evillaugh(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "evillaugh")

    @commands.command(name="facepalm", help=ACTIONS["facepalm"]["description"], extras={"parameters": "[member]", "usage": "facepalm [member]"})
    async def facepalm(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "facepalm")

    @commands.command(name="fuck", help=ACTIONS["fuck"]["description"], extras={"parameters": "[member]", "usage": "fuck [member]"})
    async def fuck(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "fuck")

    @commands.command(name="handhold", help=ACTIONS["handhold"]["description"], extras={"parameters": "[member]", "usage": "handhold [member]"})
    async def handhold(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "handhold")

    @commands.command(name="happy", help=ACTIONS["happy"]["description"], extras={"parameters": "[member]", "usage": "happy [member]"})
    async def happy(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "happy")

    @commands.command(name="headbang", help=ACTIONS["headbang"]["description"], extras={"parameters": "[member]", "usage": "headbang [member]"})
    async def headbang(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "headbang")

    @commands.command(name="hug", help=ACTIONS["hug"]["description"], extras={"parameters": "[member]", "usage": "hug [member]"})
    async def hug(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "hug")

    @commands.command(name="kiss", help=ACTIONS["kiss"]["description"], extras={"parameters": "[member]", "usage": "kiss [member]"})
    async def kiss(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "kiss")

    @commands.command(name="laugh", help=ACTIONS["laugh"]["description"], extras={"parameters": "[member]", "usage": "laugh [member]"})
    async def laugh(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "laugh")

    @commands.command(name="lick", help=ACTIONS["lick"]["description"], extras={"parameters": "[member]", "usage": "lick [member]"})
    async def lick(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "lick")

    @commands.command(name="love", help=ACTIONS["love"]["description"], extras={"parameters": "[member]", "usage": "love [member]"})
    async def love(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "love")

    @commands.command(name="mad", help=ACTIONS["mad"]["description"], extras={"parameters": "[member]", "usage": "mad [member]"})
    async def mad(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "mad")

    @commands.command(name="nervous", help=ACTIONS["nervous"]["description"], extras={"parameters": "[member]", "usage": "nervous [member]"})
    async def nervous(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "nervous")

    @commands.command(name="no", help=ACTIONS["no"]["description"], extras={"parameters": "[member]", "usage": "no [member]"})
    async def no(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "no")

    @commands.command(name="nom", help=ACTIONS["nom"]["description"], extras={"parameters": "[member]", "usage": "nom [member]"})
    async def nom(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "nom")

    @commands.command(name="nosebleed", help=ACTIONS["nosebleed"]["description"], extras={"parameters": "[member]", "usage": "nosebleed [member]"})
    async def nosebleed(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "nosebleed")

    @commands.command(name="nuzzle", help=ACTIONS["nuzzle"]["description"], extras={"parameters": "[member]", "usage": "nuzzle [member]"})
    async def nuzzle(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "nuzzle")

    @commands.command(name="nyah", help=ACTIONS["nyah"]["description"], extras={"parameters": "[member]", "usage": "nyah [member]"})
    async def nyah(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "nyah")

    @commands.command(name="pat", help=ACTIONS["pat"]["description"], extras={"parameters": "[member]", "usage": "pat [member]"})
    async def pat(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "pat")

    @commands.command(name="peek", help=ACTIONS["peek"]["description"], extras={"parameters": "[member]", "usage": "peek [member]"})
    async def peek(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "peek")

    @commands.command(name="pinch", help=ACTIONS["pinch"]["description"], extras={"parameters": "[member]", "usage": "pinch [member]"})
    async def pinch(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "pinch")

    @commands.command(name="poke", help=ACTIONS["poke"]["description"], extras={"parameters": "[member]", "usage": "poke [member]"})
    async def poke(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "poke")

    @commands.command(name="pout", help=ACTIONS["pout"]["description"], extras={"parameters": "[member]", "usage": "pout [member]"})
    async def pout(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "pout")

    @commands.command(name="punch", help=ACTIONS["punch"]["description"], extras={"parameters": "[member]", "usage": "punch [member]"})
    async def punch(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "punch")

    @commands.command(name="pussylick", aliases=["eat"], help=ACTIONS["pussylick"]["description"], extras={"parameters": "[member]", "usage": "pussylick [member]"})
    async def pussylick(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "pussylick")

    @commands.command(name="roll", help=ACTIONS["roll"]["description"], extras={"parameters": "[member]", "usage": "roll [member]"})
    async def roll(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "roll")

    @commands.command(name="sad", help=ACTIONS["sad"]["description"], extras={"parameters": "[member]", "usage": "sad [member]"})
    async def sad(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sad")

    @commands.command(name="scared", help=ACTIONS["scared"]["description"], extras={"parameters": "[member]", "usage": "scared [member]"})
    async def scared(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "scared")

    @commands.command(name="shout", help=ACTIONS["shout"]["description"], extras={"parameters": "[member]", "usage": "shout [member]"})
    async def shout(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "shout")

    @commands.command(name="shrug", help=ACTIONS["shrug"]["description"], extras={"parameters": "[member]", "usage": "shrug [member]"})
    async def shrug(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "shrug")

    @commands.command(name="shy", help=ACTIONS["shy"]["description"], extras={"parameters": "[member]", "usage": "shy [member]"})
    async def shy(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "shy")

    @commands.command(name="sigh", help=ACTIONS["sigh"]["description"], extras={"parameters": "[member]", "usage": "sigh [member]"})
    async def sigh(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sigh")

    @commands.command(name="sip", help=ACTIONS["sip"]["description"], extras={"parameters": "[member]", "usage": "sip [member]"})
    async def sip(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sip")

    @commands.command(name="slap", help=ACTIONS["slap"]["description"], extras={"parameters": "[member]", "usage": "slap [member]"})
    async def slap(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "slap")

    @commands.command(name="sleep", help=ACTIONS["sleep"]["description"], extras={"parameters": "[member]", "usage": "sleep [member]"})
    async def sleep(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sleep")

    @commands.command(name="slowclap", help=ACTIONS["slowclap"]["description"], extras={"parameters": "[member]", "usage": "slowclap [member]"})
    async def slowclap(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "slowclap")

    @commands.command(name="smack", help=ACTIONS["smack"]["description"], extras={"parameters": "[member]", "usage": "smack [member]"})
    async def smack(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "smack")

    @commands.command(name="smile", help=ACTIONS["smile"]["description"], extras={"parameters": "[member]", "usage": "smile [member]"})
    async def smile(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "smile")

    @commands.command(name="smug", help=ACTIONS["smug"]["description"], extras={"parameters": "[member]", "usage": "smug [member]"})
    async def smug(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "smug")

    @commands.command(name="sneeze", help=ACTIONS["sneeze"]["description"], extras={"parameters": "[member]", "usage": "sneeze [member]"})
    async def sneeze(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sneeze")

    @commands.command(name="sorry", help=ACTIONS["sorry"]["description"], extras={"parameters": "[member]", "usage": "sorry [member]"})
    async def sorry(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sorry")

    @commands.command(name="stare", help=ACTIONS["stare"]["description"], extras={"parameters": "[member]", "usage": "stare [member]"})
    async def stare(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "stare")

    @commands.command(name="surprised", help=ACTIONS["surprised"]["description"], extras={"parameters": "[member]", "usage": "surprised [member]"})
    async def surprised(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "surprised")

    @commands.command(name="sweat", help=ACTIONS["sweat"]["description"], extras={"parameters": "[member]", "usage": "sweat [member]"})
    async def sweat(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "sweat")

    @commands.command(name="thumbsup", help=ACTIONS["thumbsup"]["description"], extras={"parameters": "[member]", "usage": "thumbsup [member]"})
    async def thumbsup(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "thumbsup")

    @commands.command(name="tickle", help=ACTIONS["tickle"]["description"], extras={"parameters": "[member]", "usage": "tickle [member]"})
    async def tickle(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "tickle")

    @commands.command(name="tired", help=ACTIONS["tired"]["description"], extras={"parameters": "[member]", "usage": "tired [member]"})
    async def tired(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "tired")

    @commands.command(name="wave", help=ACTIONS["wave"]["description"], extras={"parameters": "[member]", "usage": "wave [member]"})
    async def wave(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "wave")

    @commands.command(name="wink", help=ACTIONS["wink"]["description"], extras={"parameters": "[member]", "usage": "wink [member]"})
    async def wink(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "wink")

    @commands.command(name="woah", help=ACTIONS["woah"]["description"], extras={"parameters": "[member]", "usage": "woah [member]"})
    async def woah(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "woah")

    @commands.command(name="yawn", help=ACTIONS["yawn"]["description"], extras={"parameters": "[member]", "usage": "yawn [member]"})
    async def yawn(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "yawn")

    @commands.command(name="yay", help=ACTIONS["yay"]["description"], extras={"parameters": "[member]", "usage": "yay [member]"})
    async def yay(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "yay")

    @commands.command(name="yes", help=ACTIONS["yes"]["description"], extras={"parameters": "[member]", "usage": "yes [member]"})
    async def yes(self, ctx: TormentContext, target: Optional[discord.Member] = None) -> None:
        await self._do_roleplay(ctx, target or ctx.author, "yes")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roleplay(bot))
