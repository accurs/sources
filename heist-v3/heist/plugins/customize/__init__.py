import discord
from discord import app_commands, Interaction, Embed, ButtonStyle
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
from heist.framework.discord.decorators import check_donor, donor_only
from heist.framework.discord import CommandCache
from heist.framework.tools.separator import makeseparator, maketintedlogo
import io
from PIL import Image, ImageDraw

class SetColorModal(Modal):
    def __init__(self, user_id: int, cog, message: discord.Message, view: View):
        super().__init__(title="Set Embed Color")
        self.user_id = user_id
        self.cog = cog
        self.message = message
        self.view = view
        self.color_input = TextInput(label="Enter a HEX color code (e.g., #ff5733)", placeholder="#000000", max_length=7, required=True, style=discord.TextStyle.short)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: Interaction):
        color_code = self.color_input.value.strip()
        if not color_code.startswith("#") or len(color_code) != 7:
            await interaction.response.warn("Invalid color. Use format **`#rrggbb`**.", ephemeral=True)
            return
        color_value = int(color_code[1:], 16)
        await self.cog.db_execute("INSERT INTO preferences (user_id, color) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET color = EXCLUDED.color", (self.user_id, color_value))
        await self.cog.cache_color(self.user_id, color_value)
        sep_bytes = await makeseparator(self.cog.bot, self.user_id)
        sep = discord.File(io.BytesIO(sep_bytes), filename="separator.png")
        logo_bytes = await maketintedlogo(self.cog.bot, self.user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed = Embed(description=f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> Customize Heist's **embed color** using the buttons below.\n> -# This will __only__ apply to **user-app** commands.\n-# Current color: **#{color_value:06x}**", color=color_value)
        embed.set_image(url="attachment://separator.png")
        embed.set_thumbnail(url="attachment://heist.png")
        await interaction.response.defer()
        await self.message.edit(embed=embed, view=self.view, attachments=[sep, logo])

class SetGradientModal(Modal):
    def __init__(self, user_id: int, cog, message: discord.Message, view: View, which: str):
        super().__init__(title=f"Set {which.title()} Gradient Color")
        self.user_id = user_id
        self.cog = cog
        self.message = message
        self.view = view
        self.which = which
        self.color_input = TextInput(label="Enter a HEX color code (e.g., #ff5733)", placeholder="#000000", max_length=7, required=True, style=discord.TextStyle.short)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: Interaction):
        color_code = self.color_input.value.strip()
        if not color_code.startswith("#") or len(color_code) != 7:
            await interaction.response.warn("Invalid color. Use format **`#rrggbb`**.", ephemeral=True)
            return
        color_value = int(color_code[1:], 16)
        await self.cog.db_execute(f"INSERT INTO wallet_colors (user_id, {self.which}_color) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET {self.which}_color = EXCLUDED.{self.which}_color", (self.user_id, color_value))
        start_color, end_color = await self.cog.get_wallet_colors(self.user_id)
        await self.cog.cache_wallet_colors(self.user_id, start_color, end_color)
        img_bytes = await self.cog.generate_preview(start_color, end_color)
        file = discord.File(io.BytesIO(img_bytes), filename="wallet.png")
        logo_bytes = await maketintedlogo(self.cog.bot, self.user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed = Embed(description=f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> 🎨 Customize your **wallet gradient** colors.\n-# Primary: **#{start_color:06x}**\n-# Secondary: **#{end_color:06x}**", color=start_color)
        embed.set_image(url="attachment://wallet.png")
        embed.set_thumbnail(url="attachment://heist.png")
        await interaction.response.defer()
        await self.message.edit(embed=embed, view=self.view, attachments=[file, logo])

class Customize(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    customize = app_commands.Group(name="customize", description="Heist customization", allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True), allowed_installs=app_commands.AppInstallationType(guild=True, user=True))
    wallet = app_commands.Group(name="wallet", description="Customize your Heist wallet", allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True), allowed_installs=app_commands.AppInstallationType(guild=True, user=True), parent=customize)

    async def db_execute(self, query, params=(), fetchone=False):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                if fetchone:
                    return await conn.fetchrow(query, *params)
                return await conn.execute(query, *params)

    async def get_color(self, user_id: int) -> int:
        redis_key = f"color:{user_id}"
        cached = await self.bot.redis.get(redis_key)
        if cached:
            return int(cached)
        row = await self.db_execute("SELECT color FROM preferences WHERE user_id = $1", (user_id,), fetchone=True)
        color_value = row["color"] if row else 0xD3D6F1
        await self.cache_color(user_id, color_value)
        return color_value

    async def cache_color(self, user_id: int, color_value: int):
        await self.bot.redis.set(f"color:{user_id}", str(color_value), ex=300)

    async def reset_color(self, user_id: int):
        await self.db_execute("DELETE FROM preferences WHERE user_id = $1", (user_id,))
        await self.bot.redis.delete(f"color:{user_id}")

    async def reset_wallet_colors(self, user_id: int):
        await self.db_execute("DELETE FROM wallet_colors WHERE user_id = $1", (user_id,))
        await self.bot.redis.delete(f"wallet_color:{user_id}:primary")
        await self.bot.redis.delete(f"wallet_color:{user_id}:secondary")

    async def cache_wallet_colors(self, user_id: int, start_color: int, end_color: int):
        await self.bot.redis.set(f"wallet_color:{user_id}:primary", str(start_color), ex=600)
        await self.bot.redis.set(f"wallet_color:{user_id}:secondary", str(end_color), ex=600)

    async def get_wallet_colors(self, user_id: int):
        row = await self.db_execute("SELECT primary_color, secondary_color FROM wallet_colors WHERE user_id=$1", (user_id,), fetchone=True)
        donor = await check_donor(self.bot, user_id)
        default_primary, default_secondary = ((0x0F0F0F, 0x2A2A2A) if donor else (0x0A50F0, 0x3278FA))
        if not row:
            return default_primary, default_secondary
        start_color = row["primary_color"] or default_primary
        end_color = row["secondary_color"] or default_secondary
        await self.cache_wallet_colors(user_id, start_color, end_color)
        return start_color, end_color

    async def generate_preview(self, start_color: int, end_color: int):
        w, h = 450, 120
        img = Image.new("RGBA", (w, h))
        draw = ImageDraw.Draw(img)
        sr, sg, sb = (start_color >> 16) & 255, (start_color >> 8) & 255, start_color & 255
        er, eg, eb = (end_color >> 16) & 255, (end_color >> 8) & 255, end_color & 255
        for y in range(h):
            r = int(sr + (er - sr) * (y / h))
            g = int(sg + (eg - sg) * (y / h))
            b = int(sb + (eb - sb) * (y / h))
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=30, fill=255)
        img = Image.composite(img, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        return buf.getvalue()

    @wallet.command(name="color", description="✨⚙️ Customize your wallet gradient colors")
    @donor_only()
    async def walletcolor(self, interaction: Interaction):
        user_id = interaction.user.id
        start_color, end_color = await self.get_wallet_colors(user_id)
        embed = Embed(description=f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> 🎨 Customize your **wallet gradient** colors.\n-# Primary: **#{start_color:06x}**\n-# Secondary: **#{end_color:06x}**", color=start_color)
        preview_bytes = await self.generate_preview(start_color, end_color)
        file = discord.File(io.BytesIO(preview_bytes), filename="wallet.png")
        logo_bytes = await maketintedlogo(self.bot, user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed.set_image(url="attachment://wallet.png")
        embed.set_thumbnail(url="attachment://heist.png")
        view = View(timeout=None)

        async def set_primary(inter: Interaction):
            await inter.response.send_modal(SetGradientModal(user_id, self, message, view, "primary"))

        async def set_secondary(inter: Interaction):
            await inter.response.send_modal(SetGradientModal(user_id, self, message, view, "secondary"))

        async def reset_wallet(inter: Interaction):
            await self.reset_wallet_colors(user_id)
            new_start, new_end = await self.get_wallet_colors(user_id)
            img_bytes = await self.generate_preview(new_start, new_end)
            file_new = discord.File(io.BytesIO(img_bytes), filename="wallet.png")
            logo_bytes2 = await maketintedlogo(self.bot, user_id)
            logo2 = discord.File(io.BytesIO(logo_bytes2), filename="heist.png")
            embed.color = new_start
            embed.description = f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> 🎨 Customize your **wallet gradient** colors.\n-# Primary: **#{new_start:06x}**\n-# Secondary: **#{new_end:06x}**"
            embed.set_thumbnail(url="attachment://heist.png")
            await inter.response.defer()
            await message.edit(embed=embed, view=view, attachments=[file_new, logo2])

        primary_button = Button(label="Primary", style=ButtonStyle.primary, emoji="🟦")
        secondary_button = Button(label="Secondary", style=ButtonStyle.secondary, emoji="🟪")
        reset_button = Button(label="Reset", style=ButtonStyle.danger, emoji="🧼")
        primary_button.callback = set_primary
        secondary_button.callback = set_secondary
        reset_button.callback = reset_wallet
        view.add_item(primary_button)
        view.add_item(secondary_button)
        view.add_item(reset_button)
        await interaction.response.send_message(embed=embed, view=view, files=[file, logo], ephemeral=True)
        message = await interaction.original_response()

    async def get_guild_activity(self, user_id: int):
        result = await self.db_execute("SELECT guild_activity FROM preferences WHERE user_id = $1", (user_id,), fetchone=True)
        if result:
            return result["guild_activity"]
        await self.db_execute("INSERT INTO preferences (user_id) VALUES ($1)", (user_id,))
        return True

    async def get_lastfm_hidden(self, user_id: int):
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT hidden FROM lastfm_users WHERE discord_id = $1", user_id)
            return row["hidden"] if row else None

    @app_commands.command(name="settings", description="⚙️ Manage your Heist settings")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settings(self, interaction: Interaction):
        user_id = interaction.user.id
        guild_activity = await self.get_guild_activity(user_id)
        hidden_lastfm = await self.get_lastfm_hidden(user_id)
        color_value = await self.get_color(user_id)
        approve = getattr(self.bot.config.emojis.context, "approve", "✅")
        warn = getattr(self.bot.config.emojis.context, "warn", "⚠️")
        guild_state = f"{approve} Enabled" if guild_activity else f"{warn} Disabled"
        if hidden_lastfm is None:
            lastfm_state = f"{warn} Not Linked"
        else:
            lastfm_state = f"{approve} Shown" if not hidden_lastfm else f"{warn} Hidden"
        setcolor = await CommandCache.get_mention(self.bot, "customize color")
        embed = Embed(
            title="Settings",
            description=f"* **Guild Activity**:\n-# > **{guild_state}**\n\n* **Last.fm Username**:\n-# > **{lastfm_state}**\n\n-# Looking to customise your embed color? Use {setcolor}.",
            color=color_value,
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)

        logo_bytes = await maketintedlogo(self.bot, user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed.set_thumbnail(url="attachment://heist.png")

        guild_button_label = "Disable Guild Activity" if guild_activity else "Enable Guild Activity"
        lastfm_button_label = "Hide Last.fm Username" if not hidden_lastfm else "Show Last.fm Username"
        toggle_guild = Button(label=guild_button_label, style=ButtonStyle.secondary, emoji="<:group:1343755056536621066>", custom_id="toggle_guild")
        toggle_lastfm = Button(label=lastfm_button_label, style=ButtonStyle.secondary, emoji="<:lastfmv2:1426636679174815966>", custom_id="toggle_lastfm")
        view = View()
        view.add_item(toggle_guild)
        view.add_item(toggle_lastfm)

        sepbyte = await makeseparator(self.bot, user_id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")
        embed.set_image(url="attachment://separator.png")

        await interaction.response.send_message(embed=embed, view=view, files=[sep, logo], ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if not interaction.data:
            return
        user_id = interaction.user.id
        custom_id = interaction.data.get("custom_id")
        if custom_id not in ["toggle_guild", "toggle_lastfm"]:
            return
        guild_activity = await self.get_guild_activity(user_id)
        hidden_lastfm = await self.get_lastfm_hidden(user_id)
        if custom_id == "toggle_guild":
            guild_activity = not guild_activity
            await self.db_execute("UPDATE preferences SET guild_activity = $1 WHERE user_id = $2", (guild_activity, user_id))
        elif custom_id == "toggle_lastfm":
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT hidden FROM lastfm_users WHERE discord_id = $1", user_id)
                if not row:
                    embed = Embed(description="You haven’t linked a Last.fm account yet.", color=0xFF4747)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                new_value = not row["hidden"]
                await conn.execute("UPDATE lastfm_users SET hidden = $1 WHERE discord_id = $2", new_value, user_id)
                hidden_lastfm = new_value
        color_value = await self.get_color(user_id)
        approve = getattr(self.bot.config.emojis.context, "approve", "✅")
        warn = getattr(self.bot.config.emojis.context, "warn", "⚠️")
        guild_state = f"{approve} Enabled" if guild_activity else f"{warn} Disabled"
        if hidden_lastfm is None:
            lastfm_state = f"{warn} Not Linked"
        else:
            lastfm_state = f"{approve} Shown" if not hidden_lastfm else f"{warn} Hidden"
        setcolor = await CommandCache.get_mention(self.bot, "customize color")
        embed = Embed(
            title="Settings",
            description=f"* **Guild Activity**:\n-# > **{guild_state}**\n\n* **Last.fm Username**:\n-# > **{lastfm_state}**\n\n-# Looking to customise your embed color? Use {setcolor}.",
            color=color_value,
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)

        logo_bytes = await maketintedlogo(self.bot, user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed.set_thumbnail(url="attachment://heist.png")

        guild_button_label = "Disable Guild Activity" if guild_activity else "Enable Guild Activity"
        lastfm_button_label = "Hide Last.fm Username" if not hidden_lastfm else "Show Last.fm Username"
        toggle_guild = Button(label=guild_button_label, style=ButtonStyle.secondary, emoji="<:group:1343755056536621066>", custom_id="toggle_guild")
        toggle_lastfm = Button(label=lastfm_button_label, style=ButtonStyle.secondary, emoji="<:lastfmv2:1426636679174815966>", custom_id="toggle_lastfm")
        view = View()
        view.add_item(toggle_guild)
        view.add_item(toggle_lastfm)

        sepbyte = await makeseparator(self.bot, user_id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")
        embed.set_image(url="attachment://separator.png")

        await interaction.response.edit_message(embed=embed, view=view, attachments=[sep, logo])

    @customize.command(description="✨⚙️ Customize Heist's embed color")
    @donor_only()
    async def color(self, interaction: Interaction):
        user_id = interaction.user.id
        color_value = await self.get_color(user_id)
        embed = Embed(description=f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> ✨ Customize Heist's **embed color** using the buttons below.\n> -# This will __only__ apply to **user-app** commands.\n-# Current color: **#{color_value:06x}**", color=color_value)
        view = View(timeout=None)

        async def set_color_callback(inter: Interaction):
            await inter.response.send_modal(SetColorModal(inter.user.id, self, message, view))

        async def reset_color_callback(inter: Interaction):
            await self.reset_color(inter.user.id)
            new_color = await self.get_color(inter.user.id)
            sep_bytes = await makeseparator(self.bot, inter.user.id)
            sep = discord.File(io.BytesIO(sep_bytes), filename="separator.png")
            logo_bytes2 = await maketintedlogo(self.bot, inter.user.id)
            logo2 = discord.File(io.BytesIO(logo_bytes2), filename="heist.png")
            embed.color = new_color
            embed.description = f"[Color Picker](https://imagecolorpicker.com/color-code/>)\n> ✨ Customize Heist's **embed color** using the buttons below.\n> -# This will __only__ apply to **user-app** commands.\n-# Current color: **#{new_color:06x}**"
            embed.set_thumbnail(url="attachment://heist.png")
            await inter.response.defer()
            await message.edit(embed=embed, view=view, attachments=[sep, logo2])

        set_button = Button(label="Change the paint", style=ButtonStyle.primary, emoji="🎨")
        reset_button = Button(label="Reset color", style=ButtonStyle.secondary, emoji="🧼")
        set_button.callback = set_color_callback
        reset_button.callback = reset_color_callback
        view.add_item(set_button)
        view.add_item(reset_button)

        sepbyte = await makeseparator(self.bot, user_id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")
        logo_bytes = await maketintedlogo(self.bot, user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")
        embed.set_image(url="attachment://separator.png")
        embed.set_thumbnail(url="attachment://heist.png")

        await interaction.response.send_message(embed=embed, view=view, files=[sep, logo], ephemeral=True)
        message = await interaction.original_response()

    async def get_embed_toggle(self, user_id: int) -> bool:
        redis_key = f"wallet_embed:{user_id}"
        cached = await self.bot.redis.get(redis_key)
        if cached is not None:
            val = str(cached).strip()
            return val == "1"
        row = await self.db_execute("SELECT embed FROM wallet_settings WHERE user_id=$1", (user_id,), fetchone=True)
        toggle = bool(row["embed"]) if row else False
        await self.cache_embed_toggle(user_id, toggle)
        return toggle

    async def cache_embed_toggle(self, user_id: int, value: bool):
        val = "1" if value else "0"
        await self.bot.redis.set(f"wallet_embed:{user_id}", val, ex=86400)

    @wallet.command(name="embedtoggle", description="Toggle your wallet between image and embed")
    async def wallet_embedtoggle(self, interaction: Interaction):
        user_id = interaction.user.id
        row = await self.db_execute("SELECT embed FROM wallet_settings WHERE user_id=$1", (user_id,), fetchone=True)
        current = bool(row["embed"]) if row else False
        new_val = not current
        await self.db_execute(
            "INSERT INTO wallet_settings (user_id, embed) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET embed = EXCLUDED.embed",
            (user_id, new_val),
        )
        await self.cache_embed_toggle(user_id, new_val)
        color = await self.bot.get_color(user_id)
        sep_bytes = await makeseparator(self.bot, user_id)
        sep = discord.File(io.BytesIO(sep_bytes), filename="separator.png")
        status = "Embed" if new_val else "Image"
        embed = Embed(description=f"Wallet display set to **{status}**.", color=color)
        embed.set_image(url="attachment://separator.png")
        await interaction.response.send_message(embed=embed, file=sep, ephemeral=True)

    async def get_design_settings(self, user_id: int):
        row = await self.db_execute(
            "SELECT roblox_user_v2, lastfm_nowplaying_v2 FROM design_settings WHERE user_id=$1",
            (user_id,),
            fetchone=True
        )
        if not row:
            return {
                "roblox_user_v2": False,
                "lastfm_nowplaying_v2": False
            }
        return {
            "roblox_user_v2": bool(row["roblox_user_v2"]),
            "lastfm_nowplaying_v2": bool(row["lastfm_nowplaying_v2"])
        }

    async def set_design_setting(self, user_id: int, key: str, value: bool):
        if key not in ("roblox_user_v2", "lastfm_nowplaying_v2"):
            return
        await self.db_execute(
            f"INSERT INTO design_settings (user_id, {key}) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET {key} = EXCLUDED.{key}",
            (user_id, value),
        )

    @customize.command(name="v2design", description="Toggle alternative designs")
    async def v2design(self, interaction: Interaction):
        user_id = interaction.user.id
        settings = await self.get_design_settings(user_id)
        roblox_v2 = settings["roblox_user_v2"]
        lastfm_v2 = settings["lastfm_nowplaying_v2"]
        color = await self.get_color(user_id)

        embed = Embed(
            description="Some of Heist's commands have alternative designs, you can see and toggle them using the select bar below.",
            color=color,
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)

        sep_bytes = await makeseparator(self.bot, user_id)
        sep = discord.File(io.BytesIO(sep_bytes), filename="separator.png")

        logo_bytes = await maketintedlogo(self.bot, user_id)
        logo = discord.File(io.BytesIO(logo_bytes), filename="heist.png")

        embed.set_image(url="attachment://separator.png")
        embed.set_thumbnail(url="attachment://heist.png")

        def opt(label, key, state):
            return discord.SelectOption(
                label=label,
                value=key,
                description="Currently enabled" if state else "Currently disabled",
                emoji="<:check:1344689360527949834>" if state else "<:no:1423109075083989062>",
            )

        options = [
            opt("Roblox User (Cards)", "roblox_user_v2", roblox_v2),
            opt("Last.fm Now Playing", "lastfm_nowplaying_v2", lastfm_v2),
        ]

        select = Select(
            placeholder="Select a design to toggle",
            min_values=1,
            max_values=1,
            options=options
        )

        view = View(timeout=None)

        async def select_callback(inter: Interaction):
            value = select.values[0]
            current = (await self.get_design_settings(user_id)).get(value, False)
            new_val = not current
            await self.set_design_setting(user_id, value, new_val)
            updated = await self.get_design_settings(user_id)
            for optx in select.options:
                if optx.value == value:
                    state = updated[value]
                    optx.emoji = "<:check:1344689360527949834>" if state else "<:no:1423109075083989062>"
                    optx.description = "Currently enabled" if state else "Currently disabled"
            await inter.response.edit_message(embed=embed, view=view)

        select.callback = select_callback
        view.add_item(select)

        await interaction.response.send_message(embed=embed, view=view, files=[sep, logo], ephemeral=True)

async def setup(bot):
    await bot.add_cog(Customize(bot))
