import discord
from discord import ui

class AgeCheck:
    @staticmethod
    async def check(bot, user_id):
        result = await bot.pool.fetchrow("SELECT age FROM age_verification WHERE user_id = $1", user_id)
        return result and result['age'] >= 18

class AgeCheckView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=240)
        self.cog = cog
        self.age = None

    @ui.button(label="Set Age", style=discord.ButtonStyle.primary)
    async def set_age(self, interaction: discord.Interaction, button: ui.Button):
        modal = AgeModal(self)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.delete()
            except:
                pass

class AgeModal(ui.Modal, title="Age Verification"):
    def __init__(self, view):
        super().__init__(timeout=240)
        self.view = view

    age_input = ui.TextInput(
        label="Enter your age",
        placeholder="18",
        min_length=1,
        max_length=3,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            age = int(self.age_input.value)
            self.view.age = age
            
            embed = discord.Embed(
                title="Confirm Your Age",
                description=f"Are you **{age}** years old?",
                color=0xd3d6f1
            )
            
            view = ConfirmAgeView(self.view, age, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await interaction.original_response()
            
        except ValueError:
            await interaction.response.warn("Please enter a valid number for your age.", ephemeral=True)

    async def on_timeout(self):
        pass

class ConfirmAgeView(ui.View):
    def __init__(self, parent_view, age, user_id):
        super().__init__(timeout=240)
        self.parent_view = parent_view
        self.age = age
        self.user_id = user_id

    @ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if self.age >= 18:
            await self.parent_view.cog.bot.pool.execute(
                "INSERT INTO age_verification (user_id, age) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET age = $2",
                self.user_id, self.age
            )
            try:
                await self.parent_view.message.delete()
            except:
                pass
            await interaction.response.approve(f"Age set to **{self.age}**, you can now run the command.", ephemeral=True)
        else:
            try:
                await self.parent_view.message.delete()
            except:
                pass
            await interaction.response.warn("You must be 18 or older to use Heist+.", ephemeral=True)

    @ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await self.parent_view.message.delete()
        except:
            pass
        await interaction.response.warn("Age verification cancelled.", ephemeral=True)

    async def on_timeout(self):
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.delete()
            except:
                pass