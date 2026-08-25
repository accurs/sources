from __future__ import annotations

import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from src.services.economy import InsufficientFunds, store


def coins(value: int) -> str:
    return f"{value:,}"


def game_card(title: str, body: str, *controls: discord.ui.Item) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    items: list[discord.ui.Item] = [discord.ui.TextDisplay(f"## {title}\n{body}")]
    if controls:
        items.extend((discord.ui.Separator(), *controls))
    view.add_item(discord.ui.Container(*items))
    return view


def card_value(card: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(card, str(card))


def blackjack_card_value(card: int) -> str:
    if card == 1:
        return "1/11"
    return str(min(card, 10))


def blackjack_total(cards: list[int]) -> int:
    total = sum(11 if card == 1 else min(card, 10) for card in cards)
    aces = cards.count(1)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


class HigherLowerButton(discord.ui.Button):
    def __init__(self, higher: bool) -> None:
        super().__init__(label="Higher" if higher else "Lower", style=discord.ButtonStyle.primary)
        self.higher = higher

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, HigherLowerView)
        await view.choose(interaction, self.higher)


class HigherLowerView(discord.ui.LayoutView):
    def __init__(self, user_id: int, bet: int, current: int) -> None:
        super().__init__(timeout=90)
        self.user_id, self.bet, self.current = user_id, bet, current
        self.done = False
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                f"## Higher or Lower\nCurrent card: **{card_value(current)}**\nBet: **{coins(bet)}**"
            ),
            discord.ui.ActionRow(HigherLowerButton(True), HigherLowerButton(False)),
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id: return True
        await interaction.response.send_message("This game belongs to someone else.", ephemeral=True); return False

    async def choose(self, interaction: discord.Interaction, higher: bool) -> None:
        if self.done: return
        self.done = True
        drawn = random.randint(1, 13)
        if drawn == self.current:
            outcome, returned = "push", self.bet
            result = "The cards tied. Your bet was returned."
        else:
            won = drawn > self.current if higher else drawn < self.current
            if won:
                favourable = (13 - self.current) if higher else (self.current - 1)
                chance = max(1, favourable) / 12
                returned = max(self.bet + 1, round(self.bet * .96 / chance))
                outcome = "win"
                result = f"Correct — you received **{coins(returned)}**."
            else:
                outcome, returned = "loss", 0
                result = "Wrong guess — the bet was lost."
        account = await asyncio.to_thread(store.settle_bet, self.user_id, "higher_lower", self.bet, returned, outcome)
        await interaction.response.edit_message(view=game_card(
            "Higher or Lower — Finished",
            f"**{card_value(self.current)} → {card_value(drawn)}**\n{result}\nWallet: **{coins(account.wallet)}**",
        ))
        self.stop()


class BlackjackButton(discord.ui.Button):
    def __init__(self, hit: bool) -> None:
        super().__init__(label="Hit" if hit else "Stand", style=discord.ButtonStyle.primary if hit else discord.ButtonStyle.secondary)
        self.hit = hit

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, BlackjackView)
        await (view.hit(interaction) if self.hit else view.stand(interaction))


class BlackjackView(discord.ui.LayoutView):
    def __init__(self, user_id: int, bet: int) -> None:
        super().__init__(timeout=120)
        self.user_id, self.bet = user_id, bet
        self.player = [random.randint(1, 13), random.randint(1, 13)]
        self.dealer = [random.randint(1, 13), random.randint(1, 13)]
        self.done = False
        self.render()

    def render(self) -> None:
        self.clear_items()
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                f"## Blackjack\nDealer: **{blackjack_card_value(self.dealer[0])}, ?**\n"
                f"You: **{', '.join(map(blackjack_card_value, self.player))}** ({blackjack_total(self.player)})\n"
                f"Bet: **{coins(self.bet)}**"
            ),
            discord.ui.ActionRow(BlackjackButton(True), BlackjackButton(False)),
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id: return True
        await interaction.response.send_message("This game belongs to someone else.", ephemeral=True); return False

    async def hit(self, interaction: discord.Interaction) -> None:
        self.player.append(random.randint(1, 13))
        if blackjack_total(self.player) > 21:
            await self.finish(interaction)
        else:
            self.render(); await interaction.response.edit_message(view=self)

    async def stand(self, interaction: discord.Interaction) -> None:
        await self.finish(interaction)

    async def finish(self, interaction: discord.Interaction) -> None:
        if self.done: return
        self.done = True
        player = blackjack_total(self.player)
        while blackjack_total(self.dealer) < 17:
            self.dealer.append(random.randint(1, 13))
        dealer = blackjack_total(self.dealer)
        natural = len(self.player) == 2 and player == 21
        if player > 21 or (dealer <= 21 and dealer > player):
            outcome, returned, result = "loss", 0, "Dealer wins."
        elif player == dealer:
            outcome, returned, result = "push", self.bet, "Push — your bet was returned."
        else:
            returned = round(self.bet * (2.5 if natural else 2))
            outcome, result = "win", f"You received **{coins(returned)}**."
        account = await asyncio.to_thread(store.settle_bet, self.user_id, "blackjack", self.bet, returned, outcome)
        await interaction.response.edit_message(view=game_card(
            "Blackjack — Finished",
            f"Dealer: **{', '.join(map(blackjack_card_value, self.dealer))}** ({dealer})\n"
            f"You: **{', '.join(map(blackjack_card_value, self.player))}** ({player})\n\n{result}\n"
            f"Wallet: **{coins(account.wallet)}**",
        ))
        self.stop()


class MinesTileButton(discord.ui.Button):
    def __init__(self, view: "MinesView", tile: int) -> None:
        if tile in view.safe:
            label, style = "💎", discord.ButtonStyle.success
        elif view.done and tile in view.mines:
            label = "💥" if tile == view.exploded_tile else "💣"
            style = discord.ButtonStyle.danger
        else:
            label, style = "\u2800", discord.ButtonStyle.secondary
        super().__init__(label=label, style=style, disabled=view.done or tile in view.safe)
        self.tile = tile

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, MinesView)
        await view.pick(interaction, self.tile)


class MinesSelect(discord.ui.Select):
    def __init__(self, available: set[int]) -> None:
        super().__init__(placeholder="Choose a tile", options=[
            discord.SelectOption(label=f"Tile {index + 1}", value=str(index))
            for index in sorted(available)
        ][:25])

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view; assert isinstance(view, MinesView)
        await view.pick(interaction, int(self.values[0]))


class MinesCashout(discord.ui.Button):
    def __init__(self) -> None: super().__init__(label="Cash Out", style=discord.ButtonStyle.success)
    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view; assert isinstance(view, MinesView); await view.cashout(interaction)


class MinesView(discord.ui.LayoutView):
    def __init__(self, user_id: int, bet: int, mine_count: int) -> None:
        super().__init__(timeout=180)
        self.user_id, self.bet, self.mine_count = user_id, bet, mine_count
        self.mines = set(random.sample(range(25), mine_count)); self.safe: set[int] = set(); self.done = False; self.exploded_tile: int | None = None
        self.render()

    def multiplier(self) -> float:
        probability = 1.0
        for picked in range(len(self.safe)):
            probability *= (25 - self.mine_count - picked) / (25 - picked)
        return .96 / probability if self.safe else 1.0

    def board(self, reveal: bool = False) -> str:
        cells=[]
        for index in range(25):
            cells.append("💣" if reveal and index in self.mines else "✅" if index in self.safe else "⬛")
        return "\n".join("".join(cells[row:row+5]) for row in range(0,25,5))

    def render(self, result: str | None = None) -> None:
        self.clear_items()
        cashout = round(self.bet * self.multiplier()) if self.safe else 0
        text=(
            f"## Mines\n"
            f"**Bet:** `{coins(self.bet)}`\n"
            f"**Mines:** `{self.mine_count}`\n"
            f"**Safe tiles:** `{len(self.safe)}`\n"
            f"**Multiplier:** `{self.multiplier():.2f}×`\n"
            f"**Cash out:** {f'`{coins(cashout)}`' if cashout else 'Reveal a safe tile first'}"
        )
        if result: text += f"\n\n**Result**\n{result}"
        items: list[discord.ui.Item]=[
            discord.ui.TextDisplay(text),
            discord.ui.Separator(),
        ]
        for row in range(5):
            items.append(
                discord.ui.ActionRow(
                    *(MinesTileButton(self, tile) for tile in range(row * 5, row * 5 + 5))
                )
            )
        if not self.done:
            items.extend((discord.ui.Separator(), discord.ui.ActionRow(MinesCashout())))
        self.add_item(discord.ui.Container(*items))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id==self.user_id:return True
        await interaction.response.send_message("This game belongs to someone else.",ephemeral=True);return False

    async def pick(self, interaction: discord.Interaction, tile: int) -> None:
        if tile in self.mines:
            self.exploded_tile=tile; self.done=True; await asyncio.to_thread(store.settle_bet,self.user_id,"mines",self.bet,0,"loss")
            self.render("You hit a mine and lost the bet."); await interaction.response.edit_message(view=self);self.stop();return
        self.safe.add(tile); self.render(); await interaction.response.edit_message(view=self)

    async def cashout(self, interaction: discord.Interaction) -> None:
        if not self.safe:
            await interaction.response.send_message("Reveal at least one safe tile first.",ephemeral=True);return
        self.done=True; returned=round(self.bet*self.multiplier())
        account=await asyncio.to_thread(store.settle_bet,self.user_id,"mines",self.bet,returned,"win")
        self.render(f"Cashed out **{coins(returned)}**. Wallet: **{coins(account.wallet)}**")
        await interaction.response.edit_message(view=self);self.stop()


class TowerTileButton(discord.ui.Button):
    def __init__(self, view: "TowersView", game_row: int, tile: int) -> None:
        passed = game_row < len(view.history)
        selected = passed and view.history[game_row] == tile
        loser = view.done and view.losers[game_row] == tile
        failed = view.failed == (game_row, tile)
        label = "✅" if selected else "💥" if failed else "💣" if loser else "\u2800"
        style = discord.ButtonStyle.success if selected else discord.ButtonStyle.danger if loser else discord.ButtonStyle.secondary
        active = not view.done and game_row == view.row
        super().__init__(label=label, style=style, disabled=not active)
        self.game_row, self.tile = game_row, tile

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TowersView)
        await view.pick(interaction, self.tile, self.game_row)


class TowerSelect(discord.ui.Select):
    def __init__(self, width: int, row: int) -> None:
        super().__init__(placeholder=f"Choose a tile on row {row + 1}",options=[discord.SelectOption(label=f"Tile {i+1}",value=str(i)) for i in range(width)])
    async def callback(self,interaction:discord.Interaction)->None:
        view=self.view;assert isinstance(view,TowersView);await view.pick(interaction,int(self.values[0]))


class TowerCashout(discord.ui.Button):
    def __init__(self):super().__init__(label="Cash Out",style=discord.ButtonStyle.success)
    async def callback(self,interaction:discord.Interaction)->None:
        view=self.view;assert isinstance(view,TowersView);await view.cashout(interaction)


class TowersView(discord.ui.LayoutView):
    def __init__(self,user_id:int,bet:int,width:int,difficulty:str)->None:
        super().__init__(timeout=180);self.user_id=user_id;self.bet=bet;self.width=width;self.difficulty=difficulty;self.row=0;self.history=[];self.done=False;self.failed=None;self.losers=[random.randrange(width) for _ in range(5)];self.render()
    def multiplier(self)->float:return .96/(((self.width-1)/self.width)**self.row) if self.row else 1
    def render(self,result:str|None=None)->None:
        self.clear_items()
        cashout=round(self.bet*self.multiplier()) if self.row else 0
        text=(
            f"## Towers\n"
            f"**Bet:** `{coins(self.bet)}`\n"
            f"**Rows cleared:** `{self.row}/5`\n"
            f"**Multiplier:** `{self.multiplier():.2f}×`\n"
            f"**Cash out:** {f'`{coins(cashout)}`' if cashout else 'Clear a row first'}"
        )
        if result:text+=f"\n\n**Result**\n{result}"
        items=[discord.ui.TextDisplay(text),discord.ui.Separator()]
        for game_row in reversed(range(5)):
            items.append(discord.ui.ActionRow(*(TowerTileButton(self,game_row,tile) for tile in range(self.width))))
        if not self.done:items.extend((discord.ui.Separator(),discord.ui.ActionRow(TowerCashout())))
        self.add_item(discord.ui.Container(*items))
    async def interaction_check(self,i):
        if i.user.id==self.user_id:return True
        await i.response.send_message("This game belongs to someone else.",ephemeral=True);return False
    async def pick(self,i,tile,game_row=None):
        if game_row is not None and game_row != self.row:
            await i.response.send_message("Choose a tile from the active row.",ephemeral=True);return
        if tile==self.losers[self.row]:
            self.failed=(self.row,tile);self.done=True;await asyncio.to_thread(store.settle_bet,self.user_id,"towers",self.bet,0,"loss");self.render("You found the losing tile.");await i.response.edit_message(view=self);self.stop();return
        self.history.append(tile);self.row+=1
        if self.row==5:await self.cashout(i);return
        self.render();await i.response.edit_message(view=self)
    async def cashout(self,i):
        if not self.row:await i.response.send_message("Clear at least one row first.",ephemeral=True);return
        self.done=True;returned=round(self.bet*self.multiplier());account=await asyncio.to_thread(store.settle_bet,self.user_id,"towers",self.bet,returned,"win");self.render(f"Cashed out **{coins(returned)}**. Wallet: **{coins(account.wallet)}**");await i.response.edit_message(view=self);self.stop()


class Gambling(commands.Cog):
    def __init__(self,bot:commands.Bot)->None:self.bot=bot;self.cooldowns={}
    async def begin(self,ctx:commands.Context,game,bet,cooldown=5)->bool:
        key=(ctx.author.id,game);remaining=self.cooldowns.get(key,0)-time.monotonic()
        if remaining>0:await ctx.send(f"Try again in **{remaining:.1f}s**.",ephemeral=True);return False
        try:await asyncio.to_thread(store.start_bet,ctx.author.id,game,bet)
        except (InsufficientFunds,ValueError):await ctx.send("Your wallet does not have enough money for that bet.",ephemeral=True);return False
        self.cooldowns[key]=time.monotonic()+cooldown;return True

    @commands.hybrid_command(name="coinflip",aliases=["cf"],description="Bet on a coin flip")
    @app_commands.choices(choice=[app_commands.Choice(name="Heads",value="heads"),app_commands.Choice(name="Tails",value="tails")])
    async def coinflip(self,ctx:commands.Context,bet:int,choice:str):
        choice=choice.casefold()
        if choice not in {"heads","tails"}:await ctx.send("Choose `heads` or `tails`.",ephemeral=True);return
        if not await self.begin(ctx,"coinflip",bet,3):return
        message=await ctx.send(view=game_card("Coinflip",f"**Your call:** {choice.title()}\n\n🪙 Tossing the coin..."))
        for frame in ("◐ Spinning...", "◓ Still spinning...", "◑ Coming down..."):
            await asyncio.sleep(.65)
            await message.edit(view=game_card("Coinflip",f"**Your call:** {choice.title()}\n\n{frame}"))
        result=random.choice(("heads","tails"));won=result==choice;returned=bet*2 if won else 0;account=await asyncio.to_thread(store.settle_bet,ctx.author.id,"coinflip",bet,returned,"win" if won else "loss")
        await asyncio.sleep(.45)
        await message.edit(view=game_card("Coinflip",f"The coin landed on **{result.title()}**.\n{'You won **'+coins(returned)+'**.' if won else 'You lost the bet.'}\nWallet: **{coins(account.wallet)}**"))

    @commands.hybrid_command(name="roulette",description="Bet on European roulette")
    async def roulette(self,ctx:commands.Context,bet:int,choice:str):
        choice=choice.lower().strip();valid=choice in {"red","black","odd","even","low","high","green"} or choice.isdigit() and 0<=int(choice)<=36
        if not valid:await ctx.send("Choose `red`, `black`, `odd`, `even`, `low`, `high`, `green`, or a number from 0–36.",ephemeral=True);return
        if not await self.begin(ctx,"roulette",bet,5):return
        message=await ctx.send(view=game_card("Roulette",f"**Bet:** {choice.title()} · **Wager:** {coins(bet)}\n\nThe wheel is spinning... 🎡"))
        for frame in ("The ball is circling the wheel... ⚪", "The ball is slowing down...", "The ball is about to drop..."):
            await asyncio.sleep(.8)
            await message.edit(view=game_card("Roulette",f"**Bet:** {choice.title()} · **Wager:** {coins(bet)}\n\n{frame}"))
        number=random.randint(0,36);reds={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36};colour="green" if number==0 else "red" if number in reds else "black"
        won=(choice==str(number) or choice==colour or choice=="odd" and number and number%2==1 or choice=="even" and number and number%2==0 or choice=="low" and 1<=number<=18 or choice=="high" and 19<=number<=36);returned=bet*(36 if choice.isdigit() or choice=="green" else 2) if won else 0;account=await asyncio.to_thread(store.settle_bet,ctx.author.id,"roulette",bet,returned,"win" if won else "loss")
        await asyncio.sleep(.5)
        await message.edit(view=game_card("Roulette",f"Result: **{number} {colour.title()}**\n{'You received **'+coins(returned)+'**.' if won else 'You lost the bet.'}\nWallet: **{coins(account.wallet)}**"))

    @roulette.autocomplete("choice")
    async def roulette_choice_autocomplete(self,interaction:discord.Interaction,current:str)->list[app_commands.Choice[str]]:
        query=current.casefold().strip()
        recommendations=[
            ("Red — 2× payout","red"),("Black — 2× payout","black"),
            ("Odd — 2× payout","odd"),("Even — 2× payout","even"),
            ("Low (1–18) — 2× payout","low"),("High (19–36) — 2× payout","high"),
            ("Green (0) — 36× payout","green"),
        ]
        options=[app_commands.Choice(name=name,value=value) for name,value in recommendations if query in name.casefold() or query in value]
        options.extend(app_commands.Choice(name=f"Number {number} — 36× payout",value=str(number)) for number in range(37) if query in str(number))
        return options[:25]

    @commands.hybrid_command(name="higher-lower",aliases=["hl"],description="Guess whether the next card is higher or lower")
    async def higher_lower(self,ctx:commands.Context,bet:int):
        if not await self.begin(ctx,"higher_lower",bet,4):return
        await ctx.send(view=HigherLowerView(ctx.author.id,bet,random.randint(1,13)))

    @commands.hybrid_command(name="blackjack",aliases=["bj"],description="Play blackjack against the dealer")
    async def blackjack(self,ctx:commands.Context,bet:int):
        if not await self.begin(ctx,"blackjack",bet,7):return
        await ctx.send(view=BlackjackView(ctx.author.id,bet))

    @commands.hybrid_command(name="mines",description="Play a 5 by 5 mines game")
    async def mines(self,ctx:commands.Context,bet:int,mines:int=3):
        if not 1<=mines<=20:await ctx.send("Choose between `1` and `20` mines.",ephemeral=True);return
        if not await self.begin(ctx,"mines",bet,7):return
        await ctx.send(view=MinesView(ctx.author.id,bet,mines))

    @commands.hybrid_command(name="towers",aliases=["tower"],description="Climb five rows and cash out before losing")
    @app_commands.choices(difficulty=[app_commands.Choice(name="Easy",value="easy"),app_commands.Choice(name="Medium",value="medium"),app_commands.Choice(name="Hard",value="hard")])
    async def towers(self,ctx:commands.Context,bet:int,difficulty:str):
        difficulty=difficulty.casefold()
        if difficulty not in {"easy","medium","hard"}:await ctx.send("Choose `easy`, `medium`, or `hard`.",ephemeral=True);return
        if not await self.begin(ctx,"towers",bet,7):return
        width={"easy":4,"medium":3,"hard":2}[difficulty];await ctx.send(view=TowersView(ctx.author.id,bet,width,difficulty))

    @commands.hybrid_group(name="gambling",aliases=["gamble"],description="Gambling information and statistics",invoke_without_command=True)
    async def gambling(self,ctx:commands.Context):
        await ctx.send("Use `gambling stats` or `gambling odds`.")

    @gambling.command(name="stats",description="Show lifetime gambling statistics")
    async def stats(self,ctx:commands.Context,user:discord.User|None=None):
        target=user or ctx.author;rows=await asyncio.to_thread(store.gambling_stats,target.id)
        if not rows:await ctx.send("That user has no gambling statistics yet.");return
        account=await asyncio.to_thread(store.get_account,target.id)
        games=sum(r["games"] for r in rows);wagered=sum(r["wagered"] for r in rows);returned=sum(r["returned"] for r in rows);wins=sum(r["wins"] for r in rows);losses=sum(r["losses"] for r in rows);bigwin=max(r["biggest_win"] for r in rows);bigloss=max(r["biggest_loss"] for r in rows);favorite=max(rows,key=lambda r:r["games"])["game"]
        pushes=sum(r["pushes"] for r in rows);profit=returned-wagered
        per="\n".join(
            f"**{r['game'].replace('_',' ').title()}**\n"
            f"`{r['games']:,}` played · `{r['wins']:,}`W / `{r['losses']:,}`L / `{r['pushes']:,}`P · "
            f"`{r['returned']-r['wagered']:+,}` profit/loss"
            for r in rows
        )
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## {target.display_name}'s Gambling Stats"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Overview\n"
                f"**Games played:** `{games:,}`\n"
                f"**Record:** `{wins:,}` wins · `{losses:,}` losses · `{pushes:,}` pushes\n"
                f"**Favorite game:** {favorite.replace('_',' ').title()}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Money\n"
                f"**Current wallet:** `{account.wallet:,}`\n"
                f"**Total wagered:** `{wagered:,}`\n"
                f"**Total returned:** `{returned:,}`\n"
                f"**Gambling profit/loss:** `{profit:+,}`"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Highlights\n"
                f"**Biggest win:** `{bigwin:,}`\n"
                f"**Biggest loss:** `{bigloss:,}`"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"### By Game\n{per}\n\n"
                "-# Profit/loss is lifetime gambling returns minus wagers. "
                "Your wallet also includes money from non-gambling activity."
            ),
        ));await ctx.send(view=view)

    @gambling.command(name="odds",description="Explain a game's odds and payouts")
    @app_commands.choices(game=[
        app_commands.Choice(name="Coinflip",value="coinflip"),
        app_commands.Choice(name="Roulette",value="roulette"),
        app_commands.Choice(name="Blackjack",value="blackjack"),
        app_commands.Choice(name="Higher or Lower",value="higher_lower"),
        app_commands.Choice(name="Mines",value="mines"),
        app_commands.Choice(name="Towers",value="towers"),
    ])
    async def odds(self,ctx:commands.Context,game:str):
        game=game.casefold().replace("-","_").replace(" ","_")
        info={
            "coinflip":("Coinflip","50%","2× total return","0%","Choose Heads or Tails. The coin has an equal chance of landing on either side.","Use this when you want the simplest game with fixed odds."),
            "roulette":("Roulette","48.65% for red, black, odd, or even","2× for even-money bets · 36× for zero or a number","2.70%","European Roulette uses numbers 0–36 with one green zero.","Red, black, odd, and even win more often; exact numbers pay much more but only have a 1-in-37 chance."),
            "blackjack":("Blackjack","Changes with your hand and the dealer's card","2× normal win · 2.5× natural Blackjack · bet returned on a push","Varies","Get closer to 21 than the dealer without going over. The dealer draws until at least 17.","Low totals are usually safer to hit; strong totals are usually safer to stand."),
            "higher_lower":("Higher or Lower","Changes with the visible card","Higher payout when your choice is less likely","About 4% on decided rounds","Guess whether the next card is higher or lower. Equal cards return the bet.","Guess higher on low cards and lower on high cards."),
            "mines":("Mines","Depends on mine count and safe tiles already found","Multiplier rises after every safe tile","4%","Choose tiles on a 5×5 board and cash out before finding a mine.","More mines and more safe picks increase the payout, but also increase the risk."),
            "towers":("Towers","Easy: 75% per row · Medium: 66.67% · Hard: 50%","Multiplier rises after every cleared row","4%","Each row contains one losing tile. Clear up to five rows and cash out whenever you want.","Easy is steadier; Hard grows the multiplier fastest."),
        }
        if game not in info:await ctx.send("Choose `coinflip`, `roulette`, `blackjack`, `higher-lower`, `mines`, or `towers`.",ephemeral=True);return
        title,chance,payout,edge,how,tip=info[game]
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## {title} Odds"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Chance\n`{chance}`"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Payout\n`{payout}`"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### House Edge\n`{edge}`"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### How It Works\n{how}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Suggestion\n{tip}"),
        ))
        await ctx.send(view=view,ephemeral=True)


async def setup(bot:commands.Bot)->None:await bot.add_cog(Gambling(bot))
