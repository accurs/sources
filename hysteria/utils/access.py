from discord import app_commands, Interaction, Embed, ui
from utils.commands import CommandCache
import asyncpg

FREE_ACCESS = False
GET_HEIST = False

async def is_whitelisted(interaction: Interaction) -> bool:
    heistcmd = await CommandCache.get_mention(interaction.client, "heistbot")
    if FREE_ACCESS:
        return True

    if GET_HEIST:
        embed = Embed(
            title="hysteria is now heist",
            description="**hysteria** is now **heist**, you can get heist from the button below for free, it has 30x more features than hysteria available for completely free of charge, enhancing the experience of thousands of users already.",
            color=interaction.client.color
        )
        view = ui.View()
        heist = ui.Button(
            label="heist bot (public)",
            url="https://discord.com/oauth2/authorize?client_id=1225070865935368265",
            emoji="<:heist:1391868311691591691>"
        )
        view.add_item(heist)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return False

    user_id = interaction.user.id
    async with interaction.client.pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT registered FROM users WHERE userid=$1", user_id
        )
        if not record or not record["registered"]:
            embed = Embed(
                title="no access sir",
                description=f"**hysteria** is currently semi-private, if you have heist premium you will get access by opening a ticket [here](https://discord.gg/heistbot). use {heistcmd} for more info.",
                color=interaction.client.color
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
    return True
