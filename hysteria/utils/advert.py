import discord, random

ENABLED = False

def advertise() -> discord.ui.View | None:
    if ENABLED and random.random() < 0.15:
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="get heist lol",
                url="https://discord.com/oauth2/authorize?client_id=1225070865935368265",
                emoji="<:heist:1391868311691591691>"
            )
        )
        return view
    return None