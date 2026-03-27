import discord, time, asyncpg
from discord.ext import commands
import asyncio
import platform
import aiohttp
import io
from bs4 import BeautifulSoup
from googletrans import Translator, LANGUAGES

async def host_ping():
    try:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        process = await asyncio.create_subprocess_exec(
            "ping", param, "1", "84.247.137.39",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        output = stdout.decode()
        for line in output.split("\n"):
            if "time=" in line.lower():
                return line.split("time=")[-1].split(" ")[0]
    except:
        return "N/A"

class misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.description = "Miscellaneous commands for general use"
        self.start_time = time.time()

    @commands.hybrid_command(name="github", description="Get the github user information", help="misc", usage="<username>")
    async def github(self, ctx: commands.Context, username: str):
        user = await self.bot.session.get_json(f"https://api.github.com/users/{username}")
        if user.get("message") == "Not Found":
            return await ctx.error("> **User not found...**")
        embed = discord.Embed(
            color=self.bot.color,
            title=user["login"],
            url=user["html_url"],
            description=user["bio"] or "No bio",
            timestamp=discord.utils.parse_time(user["created_at"])
        )
        if user.get("avatar_url"):
            embed.set_thumbnail(url=user["avatar_url"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="uptime", description="Get the bot's uptime", help="misc")
    async def uptime(self, ctx: commands.Context):
        uptime = int(time.time() - self.start_time)
        await ctx.send(f"> **Bot has been running for {uptime} seconds...**")

    @commands.hybrid_command(name="ping", description="Get the bot's latency", help="misc")
    async def ping(self, ctx: commands.Context):
        latency = self.bot.latency * 1000
        await ctx.send(f"> {latency:.2f}ms...")

    @commands.hybrid_command(name="invite", description="Get the bot's invite link", help="misc")
    async def invite(self, ctx: commands.Context):
        invite_link = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(8)
        )
        await ctx.send(f"> Invite me to your server: {invite_link}")

    @commands.command(name="source", description="Extract HTML/CSS source from a website", usage="<url>", help="misc")
    async def source(self, ctx: commands.Context, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return await ctx.send(f"> **Failed to fetch the website (status {resp.status})...**")
                    html_content = await resp.text()
        except Exception as e:
            return await ctx.send(f"> **Error fetching website: {e}**")

        soup = BeautifulSoup(html_content, "html.parser")
        css_links = [
            tag["href"] for tag in soup.find_all("link", rel="stylesheet") if tag.get("href")
        ]

        options = [
            discord.SelectOption(label="HTML", description="Get the raw HTML source"),
            discord.SelectOption(label="CSS", description="Get the linked CSS files"),
            discord.SelectOption(label="Both", description="Get both HTML and CSS"),
        ]

        select = discord.ui.Select(placeholder="Choose what to extract...", options=options)

        embed = discord.Embed(
            description=f"What would you like to extract from **{url}**?",
            color=self.bot.color
        )
        embed.set_footer(
            text="Expires in 30s",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )

        async def select_callback(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)

            choice = select.values[0]
            files = []

            embed.description = f"Extracting **{choice}** source from **{url}**..."
            embed.color = self.bot.color
            await interaction.response.edit_message(embed=embed, view=None)

            try:
                if choice in ("HTML", "Both"):
                    files.append(discord.File(fp=io.BytesIO(html_content.encode("utf-8")), filename="source.html"))

                if choice in ("CSS", "Both"):
                    if not css_links:
                        embed.description = f"**{choice}** extracted from **{url}**\n\n> No external CSS files found."
                        embed.color = self.bot.color
                        embed.set_footer(
                            text=f"{ctx.author.name}",
                            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                        )
                        await interaction.message.edit(embed=embed)
                        return

                    all_css = ""
                    async with aiohttp.ClientSession() as session:
                        for link in css_links[:5]:
                            full_url = link if link.startswith("http") else url.rstrip("/") + "/" + link.lstrip("/")
                            try:
                                async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=10)) as css_resp:
                                    if css_resp.status == 200:
                                        css_text = await css_resp.text()
                                        all_css += f"/* === {full_url} === */\n{css_text}\n\n"
                            except:
                                continue

                    if all_css:
                        files.append(discord.File(fp=io.BytesIO(all_css.encode("utf-8")), filename="styles.css"))

                if not files:
                    embed.description = f"> Nothing could be extracted from **{url}**."
                    embed.color = self.bot.color
                else:
                    embed.description = f"**{choice}** extracted from **{url}**"
                    embed.color = self.bot.color
                    file_list = "\n".join(f"`{f.filename}`" for f in files)
                    if embed.fields:
                        embed.set_field_at(0, name="Files", value=file_list)
                    else:
                        embed.add_field(name="Files", value=file_list)

                embed.set_footer(
                    text=f"{ctx.author.name}",
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                )
                await interaction.message.edit(embed=embed, attachments=files)

            except Exception as e:
                embed.description = f"> **Error during extraction: {e}**"
                embed.color = self.bot.color
                await interaction.message.edit(embed=embed)

        select.callback = select_callback
        view = discord.ui.View(timeout=30)
        view.add_item(select)

        async def on_timeout():
            embed.description = f"> Selection expired for **{url}**."
            embed.color = self.bot.color
            embed.set_footer(
                text=f"{ctx.author.name}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            try:
                await message.edit(embed=embed, view=None)
            except:
                pass

        view.on_timeout = on_timeout
        message = await ctx.send(embed=embed, view=view)

    @commands.command(name="translate", description="Translate text to another language", usage="<lang> <text>", help="misc")
    async def translate(self, ctx: commands.Context, lang: str, *, text: str):
        if lang not in LANGUAGES:
            lang_list = ", ".join(f"`{k}` ({v})" for k, v in list(LANGUAGES.items())[:30])
            embed = discord.Embed(
                description=f"**Invalid language code...**\n\n**Some valid codes:**\n{lang_list}",
                color=self.bot.color
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            description=f"Translating to **{LANGUAGES[lang].capitalize()}**...",
            color=self.bot.color
        )
        msg = await ctx.send(embed=embed)

        try:
            async with Translator() as translator:
                result = await translator.translate(text, dest=lang)

            embed.description = None
            embed.add_field(name="Original", value=f"{text}", inline=True)
            embed.add_field(name=f"Translated to {LANGUAGES[lang].capitalize()}", value=f"- {result.text}", inline=False)
            embed.add_field(name="Detected Language", value=f"- **{LANGUAGES.get(result.src, result.src).capitalize()}**", inline=True)
            embed.add_field(name="Target Language", value=f"- **{LANGUAGES[lang].capitalize()}**", inline=False)
            embed.set_author(
                name=ctx.author.name,
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await msg.edit(embed=embed)

        except Exception as e:
            embed.description = f"**Error translating text: {e}**"
            embed.color = self.bot.color
            await msg.edit(embed=embed)

    @commands.command(name="urban", description="Search the Urban Dictionary", usage="<search>", help="misc")
    async def urban(self, ctx: commands.Context, *, search: str):
        bot_ref = self.bot

        class UrbanView(discord.ui.View):
            def __init__(self, definitions: list, ctx: commands.Context):
                super().__init__(timeout=240)
                self.definitions = definitions
                self.current_page = 0
                self.ctx = ctx
                self.message = None
                self.update_button_states()

            def update_button_states(self):
                self.previous_button.disabled = (self.current_page == 0)
                self.next_button.disabled = (self.current_page == len(self.definitions) - 1)

            def build_embed(self, page: int) -> discord.Embed:
                definition_data = self.definitions[page]
                definition = definition_data["definition"]
                word = definition_data["word"]
                url = definition_data["permalink"]

                if len(definition) >= 1000:
                    definition = definition[:1000].rsplit(" ", 1)[0] + "..."

                embed = discord.Embed(
                    title=word,
                    url=url,
                    description=definition,
                    color=bot_ref.color
                )

                if definition_data.get("example"):
                    embed.add_field(name="Example", value=f"> {definition_data['example']}", inline=False)

                embed.set_author(
                    name=self.ctx.author.name,
                    icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else self.ctx.author.default_avatar.url
                )
                embed.set_footer(
                    text=f"Page {page + 1}/{len(self.definitions)}  ·  {definition_data['thumbs_up']} 👍  {definition_data['thumbs_down']} 👎"
                )
                return embed

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:left:1265476224742850633>"), style=discord.ButtonStyle.blurple)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                if self.current_page > 0:
                    self.current_page -= 1
                    self.update_button_states()
                    await interaction.response.edit_message(embed=self.build_embed(self.current_page), view=self)

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:right:1265476229876678768>"), style=discord.ButtonStyle.blurple)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                if self.current_page < len(self.definitions) - 1:
                    self.current_page += 1
                    self.update_button_states()
                    await interaction.response.edit_message(embed=self.build_embed(self.current_page), view=self)

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:sort:1317260205381386360>"), style=discord.ButtonStyle.grey)
            async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)

                view_ref = self

                class GoToPageModal(discord.ui.Modal, title="Go to Page"):
                    page_number = discord.ui.TextInput(
                        label="Page Number",
                        placeholder=f"Enter a page number (1-{len(view_ref.definitions)})",
                        min_length=1,
                        max_length=len(str(len(view_ref.definitions)))
                    )

                    async def on_submit(self, interaction: discord.Interaction):
                        try:
                            page = int(self.page_number.value) - 1
                            if page < 0 or page >= len(view_ref.definitions):
                                raise ValueError
                            view_ref.current_page = page
                            view_ref.update_button_states()
                            await interaction.response.edit_message(embed=view_ref.build_embed(page), view=view_ref)
                        except ValueError:
                            await interaction.response.send_message("> **Invalid page number...**", ephemeral=True)

                await interaction.response.send_modal(GoToPageModal())

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:bin:1317214464231079989>"), style=discord.ButtonStyle.danger)
            async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                await interaction.message.delete()

            async def on_timeout(self):
                try:
                    for item in self.children:
                        item.disabled = True
                    await self.message.edit(view=self)
                except:
                    pass

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.urbandictionary.com/v0/define?term={search}") as resp:
                    if not resp.ok:
                        return await ctx.send("**The Urban Dictionary API is down...**")
                    data = await resp.json()

            if not data["list"]:
                return await ctx.send(f"**No definitions found for **{search}**...**")

            definitions = sorted(data["list"], reverse=True, key=lambda g: int(g["thumbs_up"]))
            view = UrbanView(definitions, ctx)
            view.message = await ctx.send(embed=view.build_embed(0), view=view)

        except Exception as e:
            await ctx.send(f"> **Error fetching definition: {e}**")

    @commands.hybrid_command(name="botinfo", description="Get information about the bot", help="misc", aliases=["stats", "bi"])
    async def botinfo(self, ctx: commands.Context):
        host = await host_ping()
        support_url = getattr(self.bot, "support_url", "https://discord.gg/yHM2SAURCC")
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(8)
        )
        team_text = getattr(
            self.bot,
            "team_text",
            "**Pretend's Team**\n> Owner: <@513684550753320971>\n> Developer: <@713128996287807600>"
        )

        latency = f"{self.bot.latency * 1000:.2f}"
        ws_latency = f"{self.bot.ws.latency * 1000:.2f}"
        total_guilds = len(self.bot.guilds)
        total_users = len(self.bot.users)
        total_commands = len(set(self.bot.walk_commands()))
        total_modules = len(self.bot.cogs)
        uptime_ts = int(self.start_time)

        payload = {
            "flags": 32768,
            "components": [
                {
                    "type": 17,
                    "components": [
                        {
                            "type": 10,
                            "content": f"**A feature-rich bot designed for your server experience**\n- Started <t:{uptime_ts}:R> · {self.bot.shard_count}/1 shards"
                        },
                        {
                            "type": 14
                        },
                        {
                            "type": 9,
                            "components": [
                                {
                                    "type": 10,
                                    "content": (
                                        f"**Instance**\n"
                                        f"> **Servers:** {total_guilds}\n"
                                        f"> **Users:** {total_users:,}\n"
                                        f"> **Commands:** {total_commands}\n"
                                        f"> **Cogs:** {total_modules}\n"
                                        f"**Network**\n"
                                        f"> **Latency:** {latency}ms\n"
                                        f"> **Websocket:** {ws_latency}ms\n"
                                        f"> **Host Ping:** {host}ms\n"
                                        f"> **DB Queue:** {self.bot.db._queue.qsize()} queries"
                                    )
                                }
                            ],
                            "accessory": {
                                "type": 11,
                                "media": {
                                    "url": str(self.bot.user.display_avatar.url)
                                }
                            }
                        },
                        {
                            "type": 14
                        },
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 5,
                                    "url": invite_url,
                                    "label": "Authorize"
                                },
                                {
                                    "type": 2,
                                    "style": 5,
                                    "url": support_url,
                                    "label": "Support"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bot {self.bot.http.token}",
                "Content-Type": "application/json"
            }
            api_url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
            async with session.post(api_url, json=payload, headers=headers) as resp:
                if resp.status not in (200, 201):
                    error_text = await resp.text()
                    print(f"Components v2 failed with status {resp.status}: {error_text}")
                    await ctx.send("> **Failed to send botinfo...**")

async def setup(bot):
    await bot.add_cog(misc(bot))