from __future__ import annotations

import asyncio
import random
import re
import time

import aiohttp

import discord
from discord import app_commands
from discord.ext import commands

from src.services.economy import store

RPS_MOVES = {
    "rock": ("Rock", "🪨"),
    "paper": ("Paper", "📄"),
    "scissors": ("Scissors", "✂️"),
}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

TYPING_RACE_PHRASES = (
    "The quickest hands still need an accurate mind.",
    "A tiny mistake can change the entire message.",
    "Discord nights always last longer than expected.",
    "Practice turns difficult things into easy habits.",
    "The blue moon disappeared behind the quiet clouds.",
    "Fast fingers and sharp focus make a perfect team.",
    "Someone left an iced coffee beside the keyboard.",
    "Every great idea starts as a slightly strange thought.",
    "The last train arrived exactly three minutes early.",
    "Nothing beats winning by a single well timed keystroke.",
)


def guess_hint_range(guesses: list[int], secret: int) -> str:
    """Show only the closest known lower and upper bounds."""
    if secret in guesses:
        return f"{secret} (Correct)"
    lower = max((guess for guess in guesses if guess < secret), default=None)
    upper = min((guess for guess in guesses if guess > secret), default=None)
    hints: list[str] = []
    if lower is not None:
        hints.append(f"{lower} (H)")
    if upper is not None:
        hints.append(f"{upper} (L)")
    return "  ·  ".join(hints) if hints else "None yet"


def rps_result(first: str, second: str) -> int:
    if first == second:
        return 0
    return 1 if RPS_BEATS[first] == second else -1


class RPSMoveButton(discord.ui.Button):
    def __init__(self, move: str) -> None:
        label, emoji = RPS_MOVES[move]
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
        self.move = move

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, RPSGameView):
            await view.choose(interaction, self.move)


class RPSGameView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        player_one: discord.abc.User,
        player_two: discord.abc.User | None = None,
        difficulty: str | None = None,
    ) -> None:
        super().__init__(timeout=120)
        self.player_one = player_one
        self.player_two = player_two
        self.difficulty = difficulty
        self.moves: dict[int, str] = {}
        self.message: discord.Message | None = None
        self.move_row = discord.ui.ActionRow(
            *(RPSMoveButton(move) for move in RPS_MOVES)
        )
        self.render()

    def render(self, result_text: str | None = None) -> None:
        self.clear_items()
        if result_text:
            body = result_text
        elif self.player_two:
            ready = len(self.moves)
            body = (
                f"{self.player_one.mention} vs {self.player_two.mention}\n"
                f"**Moves locked in:** {ready}/2\n\n"
                "Choose privately below. Your move is hidden until both players choose."
            )
        else:
            body = (
                f"{self.player_one.mention} vs **Robot ({self.difficulty.title()})**\n\n"
                "Choose your move."
            )
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay("## Rock Paper Scissors"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(body),
        ]
        if not result_text:
            items.extend([discord.ui.Separator(), self.move_row])
        self.add_item(discord.ui.Container(*items))

    def robot_move(self, player_move: str) -> str:
        if self.difficulty == "medium":
            return random.choice(list(RPS_MOVES))
        outcome = random.choices(
            ("win", "draw", "lose"),
            weights=(
                (20, 20, 60)
                if self.difficulty == "easy"
                else (60, 20, 20)
            ),
        )[0]
        if outcome == "draw":
            return player_move
        if outcome == "lose":
            return RPS_BEATS[player_move]
        return next(move for move, beaten in RPS_BEATS.items() if beaten == player_move)

    async def choose(self, interaction: discord.Interaction, move: str) -> None:
        allowed_ids = {self.player_one.id}
        if self.player_two:
            allowed_ids.add(self.player_two.id)
        if interaction.user.id not in allowed_ids:
            await interaction.response.send_message(
                "You are not a player in this game.", ephemeral=True
            )
            return
        if interaction.user.id in self.moves:
            await interaction.response.send_message(
                "Your move is already locked in.", ephemeral=True
            )
            return
        self.moves[interaction.user.id] = move

        if self.player_two and len(self.moves) < 2:
            self.render()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"You selected **{RPS_MOVES[move][0]}**.", ephemeral=True
            )
            return

        first_move = self.moves[self.player_one.id]
        if self.player_two:
            second_move = self.moves[self.player_two.id]
            second_name = self.player_two.mention
        else:
            second_move = self.robot_move(first_move)
            second_name = "Robot"
        outcome = rps_result(first_move, second_move)
        if outcome == 0:
            winner = "**It is a draw.**"
        elif outcome > 0:
            winner = f"🏆 {self.player_one.mention} wins!"
        else:
            winner = f"🏆 {second_name} wins!"
        first_label, first_emoji = RPS_MOVES[first_move]
        second_label, second_emoji = RPS_MOVES[second_move]
        result_text = (
            f"{self.player_one.mention}: {first_emoji} **{first_label}**\n"
            f"{second_name}: {second_emoji} **{second_label}**\n\n{winner}"
        )
        if self.player_two is None and outcome > 0:
            reward = {"easy": 750, "medium": 1_500, "hard": 2_500}.get(self.difficulty or "", 0)
            awarded = await asyncio.to_thread(
                store.award_game_reward, self.player_one.id, "rpc", reward
            )
            if awarded:
                result_text += f"\n\n💰 **Cash prize: {awarded:,}**"
        self.render(result_text)
        self.stop()
        await interaction.response.edit_message(view=self)


class RPSDifficultySelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose robot difficulty",
            options=[
                discord.SelectOption(label="Easy", description="The robot is easier to beat", emoji="🟢"),
                discord.SelectOption(label="Medium", description="Fair and fully random", emoji="🟡"),
                discord.SelectOption(label="Hard", description="The robot is harder to beat", emoji="🔴"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, RPSDifficultyView):
            return
        game = RPSGameView(player_one=interaction.user, difficulty=self.values[0].lower())
        await interaction.response.edit_message(view=game)
        game.message = interaction.message


class RPSDifficultyView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        row = discord.ui.ActionRow(RPSDifficultySelect())
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Choose Your Opponent"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Select the robot difficulty."),
                row,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class RPSUserSelect(discord.ui.UserSelect):
    def __init__(self) -> None:
        super().__init__(placeholder="Choose someone to challenge", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, RPSUserSelectView):
            return
        selected = self.values[0]
        if selected.id == interaction.user.id or selected.bot:
            await interaction.response.send_message(
                "Choose another human player.", ephemeral=True
            )
            return
        challenge = RPSChallengeView(challenger=interaction.user, opponent=selected)
        await interaction.response.edit_message(view=challenge)
        challenge.message = interaction.message


class RPSUserSelectView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Challenge a Player"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Choose a user from this conversation."),
                discord.ui.ActionRow(RPSUserSelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class RPSChallengeButton(discord.ui.Button):
    def __init__(self, accept: bool) -> None:
        super().__init__(
            label="Accept" if accept else "Decline",
            style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
        )
        self.accept = accept

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, RPSChallengeView):
            return
        if interaction.user.id != view.opponent.id:
            await interaction.response.send_message(
                "Only the challenged user can answer.", ephemeral=True
            )
            return
        if not self.accept:
            view.stop()
            declined = discord.ui.LayoutView()
            declined.add_item(
                discord.ui.Container(discord.ui.TextDisplay("## Challenge Declined"))
            )
            await interaction.response.edit_message(view=declined)
            return
        game = RPSGameView(player_one=view.challenger, player_two=view.opponent)
        view.stop()
        await interaction.response.edit_message(view=game)
        game.message = interaction.message


class RPSChallengeView(discord.ui.LayoutView):
    def __init__(self, challenger: discord.abc.User, opponent: discord.abc.User) -> None:
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.message: discord.Message | None = None
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Rock Paper Scissors Challenge"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"{opponent.mention}, {challenger.mention} challenged you."
                ),
                discord.ui.ActionRow(RPSChallengeButton(True), RPSChallengeButton(False)),
            )
        )


TTT_WINS = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def ttt_winner(board: list[str | None]) -> str | None:
    for first, second, third in TTT_WINS:
        if board[first] and board[first] == board[second] == board[third]:
            return board[first]
    return None


def ttt_minimax(board: list[str | None], maximizing: bool) -> int:
    winner = ttt_winner(board)
    if winner == "O":
        return 1
    if winner == "X":
        return -1
    if all(board):
        return 0
    scores = []
    mark = "O" if maximizing else "X"
    for index, value in enumerate(board):
        if value is not None:
            continue
        board[index] = mark
        scores.append(ttt_minimax(board, not maximizing))
        board[index] = None
    return max(scores) if maximizing else min(scores)


class TTTCellButton(discord.ui.Button):
    def __init__(
        self,
        index: int,
        value: str | None,
        *,
        locked: bool = False,
    ) -> None:
        style = discord.ButtonStyle.secondary
        if value == "X":
            style = discord.ButtonStyle.danger
        elif value == "O":
            style = discord.ButtonStyle.primary
        super().__init__(label=value or "\u200b", style=style, row=index // 3)
        self.index = index
        self.disabled = locked or value is not None

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, TicTacToeGameView):
            await view.play(interaction, self.index)


class TicTacToeGameView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        player_x: discord.abc.User,
        player_o: discord.abc.User | None = None,
        difficulty: str | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.player_x = player_x
        self.player_o = player_o
        self.difficulty = difficulty
        self.board: list[str | None] = [None] * 9
        self.turn = "X"
        self.finished = False
        self.message: discord.Message | None = None
        self.render()

    def player_for(self, mark: str) -> discord.abc.User | None:
        return self.player_x if mark == "X" else self.player_o

    def status_text(self) -> str:
        if self.player_o:
            matchup = f"❌ {self.player_x.mention} vs ⭕ {self.player_o.mention}"
            current = self.player_for(self.turn)
            return f"{matchup}\n\n**Turn:** {current.mention} ({self.turn})"
        return (
            f"❌ {self.player_x.mention} vs ⭕ **Robot ({self.difficulty.title()})**\n\n"
            f"**Turn:** {self.player_x.mention} (X)"
        )

    def render(self, result: str | None = None) -> None:
        self.clear_items()
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay("## Tic-Tac-Toe"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(result or self.status_text()),
        ]
        items.append(discord.ui.Separator())
        for row in range(3):
            items.append(
                discord.ui.ActionRow(
                    *(
                        TTTCellButton(
                            index,
                            self.board[index],
                            locked=self.finished,
                        )
                        for index in range(row * 3, row * 3 + 3)
                    )
                )
            )
        self.add_item(discord.ui.Container(*items))

    def bot_move(self) -> int:
        available = [index for index, value in enumerate(self.board) if value is None]
        if self.difficulty == "easy":
            return random.choice(available)
        if self.difficulty == "medium" and random.random() < 0.5:
            return random.choice(available)
        best_score = -10
        best_moves = []
        for index in available:
            self.board[index] = "O"
            score = ttt_minimax(self.board, False)
            self.board[index] = None
            if score > best_score:
                best_score = score
                best_moves = [index]
            elif score == best_score:
                best_moves.append(index)
        return random.choice(best_moves)

    def finish_text(self) -> str | None:
        winner = ttt_winner(self.board)
        if winner:
            self.finished = True
            player = self.player_for(winner)
            winner_name = player.mention if player else "Robot"
            return f"🏆 **{winner_name} wins!**\n\n{winner} completed three in a row."
        if all(self.board):
            self.finished = True
            return "**It is a draw.** The board is full."
        return None

    async def play(self, interaction: discord.Interaction, index: int) -> None:
        expected = self.player_for(self.turn)
        if expected is None or interaction.user.id != expected.id:
            await interaction.response.send_message(
                "It is not your turn.", ephemeral=True
            )
            return
        if self.board[index] is not None or self.finished:
            await interaction.response.send_message(
                "That square is unavailable.", ephemeral=True
            )
            return
        self.board[index] = self.turn
        result = self.finish_text()
        if result is None and self.player_o is None:
            self.board[self.bot_move()] = "O"
            result = self.finish_text()
            self.turn = "X"
        elif result is None:
            self.turn = "O" if self.turn == "X" else "X"
        if self.finished:
            if self.player_o is None and ttt_winner(self.board) == "X":
                reward = {"easy": 1_000, "medium": 2_500, "hard": 5_000}.get(self.difficulty or "", 0)
                awarded = await asyncio.to_thread(
                    store.award_game_reward, self.player_x.id, "tic_tac_toe", reward
                )
                if awarded:
                    result += f"\n\n💰 **Cash prize: {awarded:,}**"
            self.stop()
        self.render(result)
        await interaction.response.edit_message(view=self)


class TTTDifficultySelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose robot difficulty",
            options=[
                discord.SelectOption(label="Easy", description="Robot chooses randomly", emoji="🟢"),
                discord.SelectOption(label="Medium", description="Sometimes strategic", emoji="🟡"),
                discord.SelectOption(label="Hard", description="Robot plays optimally", emoji="🔴"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TTTDifficultyView):
            return
        game = TicTacToeGameView(
            player_x=interaction.user,
            difficulty=self.values[0].lower(),
        )
        await interaction.response.edit_message(view=game)
        game.message = interaction.message


class TTTDifficultyView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Tic-Tac-Toe · Robot"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Choose the robot difficulty."),
                discord.ui.ActionRow(TTTDifficultySelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class TTTUserSelect(discord.ui.UserSelect):
    def __init__(self) -> None:
        super().__init__(placeholder="Choose someone to challenge", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TTTUserSelectView):
            return
        selected = self.values[0]
        if selected.id == interaction.user.id or selected.bot:
            await interaction.response.send_message(
                "Choose another human player.", ephemeral=True
            )
            return
        challenge = TTTChallengeView(interaction.user, selected)
        await interaction.response.edit_message(view=challenge)


class TTTUserSelectView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Tic-Tac-Toe · Challenge"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Choose a user from this conversation."),
                discord.ui.ActionRow(TTTUserSelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class TTTChallengeButton(discord.ui.Button):
    def __init__(self, accept: bool) -> None:
        super().__init__(
            label="Accept" if accept else "Decline",
            style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
        )
        self.accept = accept

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TTTChallengeView):
            return
        if interaction.user.id != view.opponent.id:
            await interaction.response.send_message(
                "Only the challenged user can answer.", ephemeral=True
            )
            return
        if not self.accept:
            view.stop()
            declined = discord.ui.LayoutView()
            declined.add_item(
                discord.ui.Container(discord.ui.TextDisplay("## Challenge Declined"))
            )
            await interaction.response.edit_message(view=declined)
            return
        game = TicTacToeGameView(player_x=view.challenger, player_o=view.opponent)
        view.stop()
        await interaction.response.edit_message(view=game)


class TTTChallengeView(discord.ui.LayoutView):
    def __init__(self, challenger: discord.abc.User, opponent: discord.abc.User) -> None:
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Tic-Tac-Toe Challenge"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"{opponent.mention}, {challenger.mention} challenged you."
                ),
                discord.ui.ActionRow(TTTChallengeButton(True), TTTChallengeButton(False)),
            )
        )


GAME_OPPONENTS = [
    app_commands.Choice(name="Bot", value="bot"),
    app_commands.Choice(name="User", value="user"),
]


class GameOpponentSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose who to play against",
            options=[
                discord.SelectOption(
                    label="Bot",
                    value="bot",
                    description="Choose a robot difficulty",
                ),
                discord.SelectOption(
                    label="User",
                    value="user",
                    description="Challenge someone in this conversation",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, GameOpponentView)
        against_bot = self.values[0] == "bot"
        if view.game == "rpc":
            next_view = (
                RPSDifficultyView(interaction.user.id)
                if against_bot
                else RPSUserSelectView(interaction.user.id)
            )
        elif view.game == "tic-tac-toe":
            next_view = (
                TTTDifficultyView(interaction.user.id)
                if against_bot
                else TTTUserSelectView(interaction.user.id)
            )
        else:
            next_view = (
                Connect4DifficultyView(interaction.user.id)
                if against_bot
                else Connect4UserSelectView(interaction.user.id)
            )
        await interaction.response.edit_message(view=next_view)


class GameOpponentView(discord.ui.LayoutView):
    TITLES = {
        "rpc": "Rock Paper Scissors",
        "tic-tac-toe": "Tic-Tac-Toe",
        "connect4": "Connect Four",
    }

    def __init__(self, author_id: int, game: str) -> None:
        super().__init__(timeout=60)
        self.author_id, self.game = author_id, game
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {self.TITLES[game]}\nChoose who you want to play against."
                ),
                discord.ui.ActionRow(GameOpponentSelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


def connect4_winner(board: list[list[int]]) -> int:
    for row in range(6):
        for column in range(7):
            player = board[row][column]
            if not player: continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                if all(
                    0 <= row + dr * step < 6
                    and 0 <= column + dc * step < 7
                    and board[row + dr * step][column + dc * step] == player
                    for step in range(4)
                ):
                    return player
    return 0


class Connect4Button(discord.ui.Button):
    def __init__(self, column: int, *, disabled: bool = False) -> None:
        super().__init__(
            label=str(column + 1),
            style=discord.ButtonStyle.secondary,
            row=column // 5,
            disabled=disabled,
        )
        self.column = column
    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view; assert isinstance(view, Connect4View)
        await view.play(interaction, self.column)


class Connect4View(discord.ui.LayoutView):
    def __init__(self, player: discord.abc.User, opponent: discord.abc.User | None, difficulty: str) -> None:
        super().__init__(timeout=300); self.player=player;self.opponent=opponent;self.difficulty=difficulty
        self.board=[[0]*7 for _ in range(6)];self.turn=1;self.finished=False;self.render()
    def drop(self,column:int,player:int)->bool:
        for row in reversed(range(6)):
            if self.board[row][column]==0:self.board[row][column]=player;return True
        return False
    def render(self,result:str|None=None)->None:
        self.clear_items();icons={0:"⚫",1:"🔴",2:"🟡"};grid="\n".join("".join(icons[cell] for cell in row) for row in self.board)
        opponent=self.opponent.mention if self.opponent else f"Robot ({self.difficulty.title()})"
        body=f"{self.player.mention} 🔴 vs {opponent} 🟡\n\n{grid}\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        if result:body+=f"\n\n{result}"
        items=[discord.ui.TextDisplay("## Connect Four\n"+body)]
        if not self.finished:
            items.extend((
                discord.ui.ActionRow(*(
                    Connect4Button(i, disabled=self.board[0][i] != 0)
                    for i in range(5)
                )),
                discord.ui.ActionRow(*(
                    Connect4Button(i, disabled=self.board[0][i] != 0)
                    for i in range(5, 7)
                )),
            ))
        self.add_item(discord.ui.Container(*items))
    def bot_column(self)->int:
        available=[c for c in range(7) if self.board[0][c]==0]
        if self.difficulty=="easy":return random.choice(available)
        for player in (2,1):
            for column in available:
                copy=[row[:] for row in self.board]
                for row in reversed(range(6)):
                    if copy[row][column]==0:copy[row][column]=player;break
                if connect4_winner(copy)==player:return column
        if self.difficulty=="medium" and random.random()<.5:return random.choice(available)
        return min(available,key=lambda column:abs(column-3))
    async def interaction_check(self,i):
        allowed={self.player.id}|({self.opponent.id} if self.opponent else set())
        if i.user.id in allowed:return True
        await i.response.send_message("You are not playing this game.",ephemeral=True);return False
    async def play(self,i,column):
        expected=self.player if self.turn==1 else self.opponent
        if expected is None or i.user.id!=expected.id:await i.response.send_message("It is not your turn.",ephemeral=True);return
        if not self.drop(column,self.turn):await i.response.send_message("That column is full.",ephemeral=True);return
        winner=connect4_winner(self.board)
        if not winner and not self.opponent:
            self.drop(self.bot_column(),2);winner=connect4_winner(self.board)
        elif not winner:self.turn=2 if self.turn==1 else 1
        full=all(self.board[0]);result=None
        if winner:
            self.finished=True;name=self.player.mention if winner==1 else self.opponent.mention if self.opponent else "Robot";result=f"🏆 **{name} wins!**"
            if not self.opponent and winner==1:
                reward={"easy":2_000,"medium":4_000,"hard":7_500}[self.difficulty]
                awarded=await asyncio.to_thread(store.award_game_reward,self.player.id,"connect4",reward)
                if awarded:result+=f"\n\n💰 **Cash prize: {awarded:,}**"
        elif full:self.finished=True;result="**It is a draw.**"
        self.render(result);await i.response.edit_message(view=self)
        if self.finished:self.stop()


class Connect4DifficultySelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose robot difficulty",
            options=[
                discord.SelectOption(label="Easy", description="Robot mostly chooses randomly"),
                discord.SelectOption(label="Medium", description="Robot sometimes plays strategically"),
                discord.SelectOption(label="Hard", description="Robot looks for wins and blocks"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        game = Connect4View(
            interaction.user,
            None,
            self.values[0].lower(),
        )
        await interaction.response.edit_message(view=game)


class Connect4DifficultyView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Connect Four · Robot\nChoose the robot difficulty."),
                discord.ui.ActionRow(Connect4DifficultySelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class Connect4UserSelect(discord.ui.UserSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choose someone to challenge",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        if selected.id == interaction.user.id or selected.bot:
            await interaction.response.send_message(
                "Choose another human player.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            view=Connect4ChallengeView(interaction.user, selected)
        )


class Connect4UserSelectView(discord.ui.LayoutView):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Connect Four · Challenge\nChoose a user from this conversation."
                ),
                discord.ui.ActionRow(Connect4UserSelect()),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This menu is not yours.", ephemeral=True)
        return False


class Connect4ChallengeButton(discord.ui.Button):
    def __init__(self, accept: bool) -> None:
        super().__init__(
            label="Accept" if accept else "Decline",
            style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
        )
        self.accept = accept

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, Connect4ChallengeView)
        if interaction.user.id != view.opponent.id:
            await interaction.response.send_message(
                "Only the challenged user can answer.", ephemeral=True
            )
            return
        view.stop()
        if self.accept:
            await interaction.response.edit_message(
                view=Connect4View(view.challenger, view.opponent, "medium")
            )
        else:
            declined = discord.ui.LayoutView()
            declined.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("## Connect Four Challenge Declined")
                )
            )
            await interaction.response.edit_message(view=declined)


class Connect4ChallengeView(discord.ui.LayoutView):
    def __init__(self, challenger: discord.abc.User, opponent: discord.abc.User) -> None:
        super().__init__(timeout=60)
        self.challenger, self.opponent = challenger, opponent
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Connect Four Challenge\n{opponent.mention}, "
                    f"{challenger.mention} challenged you."
                ),
                discord.ui.ActionRow(
                    Connect4ChallengeButton(True),
                    Connect4ChallengeButton(False),
                ),
            )
        )


class WYRButton(discord.ui.Button):
    def __init__(self,index:int,label:str):super().__init__(label=label[:80],style=discord.ButtonStyle.primary);self.index=index
    async def callback(self,i):
        view=self.view;assert isinstance(view,WYRView);view.votes[i.user.id]=self.index;view.render();await i.response.edit_message(view=view)


class WYRView(discord.ui.LayoutView):
    def __init__(self,question:str,choices:list[str]):super().__init__(timeout=180);self.question=question;self.choices=choices;self.votes={};self.render()
    def render(self):
        self.clear_items();counts=[sum(v==index for v in self.votes.values()) for index in range(2)];total=len(self.votes);lines=[]
        for choice,count in zip(self.choices,counts):percent=round(count/total*100) if total else 0;lines.append(f"**{choice}** — **`{percent}%`** ({count})")
        self.add_item(discord.ui.Container(discord.ui.TextDisplay("## Would You Rather\n"+self.question+"\n\n"+"\n".join(lines)),discord.ui.ActionRow(*(WYRButton(i,c) for i,c in enumerate(self.choices)))))


class GuessNumberModal(discord.ui.Modal, title="Guess the number"):
    guess = discord.ui.TextInput(label="Number from -100 to 500", max_length=4)

    def __init__(self, game: "GuessNumberDMView") -> None:
        super().__init__()
        self.game = game

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(str(self.guess.value))
            if not -100 <= value <= 500:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Enter a whole number from -100 to 500.", ephemeral=True)
            return
        await self.game.submit_guess(interaction, value)


class GuessNumberButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Make a Guess", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, GuessNumberDMView):
            await interaction.response.send_modal(GuessNumberModal(view))


class GuessNumberDMView(discord.ui.LayoutView):
    def __init__(self, user_id: int, secret: int) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id
        self.secret = secret
        self.attempts = 0
        self.guesses: list[int] = []
        self.finished = False
        self.render("Pick a number from **-100 to 500**.")

    def render(self, status: str) -> None:
        self.clear_items()
        history = guess_hint_range(self.guesses, self.secret)
        items: list[discord.ui.Item] = [discord.ui.TextDisplay(
            f"## Guess the Number\n{status}\n\n**Current range:** `{history}`\n"
            "-# H = answer is higher · L = answer is lower"
        )]
        if not self.finished:
            items.extend((discord.ui.Separator(), discord.ui.ActionRow(GuessNumberButton())))
        self.add_item(discord.ui.Container(*items))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This game belongs to someone else.", ephemeral=True)
        return False

    async def submit_guess(self, interaction: discord.Interaction, guess: int) -> None:
        self.attempts += 1
        self.guesses.append(guess)
        if guess == self.secret:
            reward = max(500, 3_500 - (self.attempts - 1) * 200)
            awarded = await asyncio.to_thread(store.award_game_reward, self.user_id, "guess_number", reward)
            self.finished = True
            status = f"Correct — it was **{self.secret}** in **{self.attempts}** guesses."
            if awarded:
                status += f" You earned **{awarded:,}**."
        elif self.attempts >= 15:
            self.finished = True
            status = f"No guesses left. The number was **{self.secret}**."
        else:
            status = f"**{'Higher' if guess < self.secret else 'Lower'}** · Guess {self.attempts}/15"
        self.render(status)
        await interaction.response.edit_message(view=self)
        if self.finished:
            self.stop()


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guess_games: dict[tuple[int, int], tuple[int, int]] = {}
        self.last_guess_secrets: dict[int, int] = {}

    def _new_guess_secret(self, user_id: int) -> int:
        previous = self.last_guess_secrets.get(user_id)
        secret = random.randint(-100, 500)
        while secret == previous:
            secret = random.randint(-100, 500)
        self.last_guess_secrets[user_id] = secret
        return secret
        self.typing_races: set[int] = set()

    async def party_question(self, kind: str, rating: str = "pg") -> str:
        timeout=aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://api.truthordarebot.xyz/v1/{kind}",params={"rating":rating}) as response:
                response.raise_for_status();data=await response.json()
        return str(data["question"])

    @staticmethod
    def rating_for(
        interaction: discord.Interaction | commands.Context,
        command: str,
        *users: discord.abc.User,
    ) -> int:
        """Roll a fresh 0-100 score, weighted toward higher results."""
        return max(random.randint(0, 100), random.randint(0, 100))

    @commands.hybrid_command(name="opsec", description="Calculate a user's OPSEC rating")
    async def opsec(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "opsec", target)
        await ctx.send(f"{target.mention}'s OPSEC is **`{score}%`**")

    @commands.hybrid_command(name="autism-rate", aliases=["autism"], description="Calculate a user's autism rate")
    async def autism_rate(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "autism-rate", target)
        await ctx.send(f"{target.mention}'s autism rate is **`{score}%`**")

    @commands.hybrid_command(name="aura", description="Calculate a user's aura")
    async def aura(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "aura", target)
        await ctx.send(f"{target.mention}'s aura is **`{score}%`**")

    @commands.hybrid_command(name="menace", description="Calculate how much of a menace a user is")
    async def menace(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "menace", target)
        await ctx.send(
            f"{target.mention}'s menace level is **`{score}%`**"
        )

    @commands.hybrid_command(name="howblack", description="Calculate how black a user is")
    async def howblack(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "howblack", target)
        await ctx.send(
            f"{target.mention}'s blackness level is **`{score}%`**"
        )

    @commands.hybrid_command(name="ship", description="Calculate the compatibility between two users")
    async def ship(
        self,
        ctx: commands.Context,
        user: discord.User,
        other_user: discord.User | None = None,
    ) -> None:
        first = ctx.author if other_user is None else user
        second = user if other_user is None else other_user
        ordered_users = tuple(sorted((first, second), key=lambda member: member.id))
        score = self.rating_for(ctx, "ship", *ordered_users)
        await ctx.send(
            f"{first.mention} and {second.mention}'s compatibility is **`{score}%`**"
        )

    @commands.hybrid_command(name="trust", description="Calculate how trustworthy a user is")
    async def trust(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "trust", target)
        await ctx.send(f"{target.mention} is **`{score}%`** trustworthy")

    @commands.hybrid_command(name="sus", description="Calculate how suspicious a user is")
    async def sus(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "sus", target)
        await ctx.send(f"{target.mention} is **`{score}%`** sus")

    @commands.hybrid_command(name="luck", description="Calculate a user's luck today")
    async def luck(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "luck", target)
        await ctx.send(f"{target.mention}'s luck today is **`{score}%`**")

    @commands.hybrid_command(name="braincell", aliases=["braincells"], description="Calculate a user's available brain cells")
    async def braincell(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        cells = random.randint(80_000_000_000, 92_000_000_000)
        await ctx.send(
            f"{target.mention} has **`{cells:,}`** brain cells available"
        )

    @commands.hybrid_command(name="chronically-online", aliases=["online"], description="Calculate how chronically online a user is")
    async def chronically_online(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
    ) -> None:
        target = user or ctx.author
        score = self.rating_for(ctx, "chronically-online", target)
        await ctx.send(f"{target.mention} is **`{score}%`** chronically online")

    @commands.hybrid_command(
        name="echo",
        aliases=["say"],
        description="Echoes the message back to you",
    )
    @app_commands.describe(text="The message to echo back")
    async def echo(
        self,
        ctx: commands.Context,
        *,
        text: str,
        ephemeral: bool = False,
    ) -> None:
        await ctx.send(text)

    @echo.error
    async def echo_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if not isinstance(error, commands.MissingRequiredArgument):
            await self.bot.on_command_error(ctx, error)
            return

        view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay("### Missing message"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "You need to provide a message to echo back.\nUsage: `;echo <message>`"
            ),
        )

        view.add_item(container)
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="roll",
        aliases=["dice"],
        description="Roll dice with the specified number of sides",
    )
    @app_commands.describe(n="Number of dice", m="Sides per die")
    async def roll(
        self,
        ctx: commands.Context,
        n: int,
        m: int,
        ephemeral: bool = False,
    ) -> None:
        if n <= 0 or m <= 0 or n > 100 or m > 1000:
            await ctx.send("Please use reasonable values")
            return

        total = sum(random.randint(1, m) for _ in range(n))
        await ctx.send(f"You rolled **`{total}`**")

    @app_commands.command(name="rpc", description="Play rock paper scissors")
    async def rpc(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            view=GameOpponentView(interaction.user.id, "rpc")
        )

    @app_commands.command(name="tic-tac-toe", description="Play tic-tac-toe")
    async def tic_tac_toe(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            view=GameOpponentView(interaction.user.id, "tic-tac-toe")
        )

    @app_commands.command(name="connect4", description="Play Connect Four against a user or robot")
    async def connect4(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            view=GameOpponentView(interaction.user.id, "connect4")
        )

    @commands.hybrid_command(name="guess-number", aliases=["guessnumber"], description="Start a number guessing game")
    async def guess_number(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            secret = self._new_guess_secret(ctx.author.id)
            await ctx.send(view=GuessNumberDMView(ctx.author.id, secret))
            return
        key = (ctx.author.id, ctx.channel.id)
        if key in self.guess_games:
            await ctx.send("You already have a guessing game running in this channel.", ephemeral=True)
            return
        secret = self._new_guess_secret(ctx.author.id)
        self.guess_games[key] = (secret, 0)
        guesses: list[int] = []
        await ctx.send("## Guess the Number\nSend ordinary messages containing numbers from **-100 to 500**. You have **15 guesses** and **5 minutes**.")
        try:
            for attempts in range(1, 16):
                def check(message: discord.Message) -> bool:
                    if message.author.id != ctx.author.id or message.channel.id != ctx.channel.id:
                        return False
                    try:
                        value = int(message.content.strip())
                    except ValueError:
                        return False
                    return -100 <= value <= 500

                message = await self.bot.wait_for("message", check=check, timeout=300)
                guess = int(message.content.strip())
                guesses.append(guess)
                history = guess_hint_range(guesses, secret)
                if guess == secret:
                    reward = max(500, 3_500 - (attempts - 1) * 200)
                    awarded = await asyncio.to_thread(store.award_game_reward, ctx.author.id, "guess_number", reward)
                    text = f"Correct, {ctx.author.mention} — the number was **{secret}** in **{attempts}** guesses."
                    if awarded:
                        text += f" You earned **{awarded:,}**."
                    text += f"\n**Final answer:** `{history}`"
                    await ctx.send(text)
                    return
                await message.reply(
                    f"**{'Higher' if guess < secret else 'Lower'}** · Guess {attempts}/15\n"
                    f"**Current range:** `{history}`\n"
                    "-# H = answer is higher · L = answer is lower",
                    mention_author=False,
                )
            await ctx.send(
                f"No guesses left. The number was **{secret}**.\n"
                f"**Closest range:** `{guess_hint_range(guesses, secret)}`"
            )
        except asyncio.TimeoutError:
            await ctx.send(f"The guessing game expired. The number was **{secret}**.")
        finally:
            self.guess_games.pop(key, None)

    @app_commands.command(name="typing-race", description="Race to type a sentence correctly")
    async def typing_race(self, interaction: discord.Interaction) -> None:
        channel_id = interaction.channel_id
        if channel_id is None:
            await interaction.response.send_message(
                "A typing race cannot be started here.", ephemeral=True
            )
            return
        if channel_id in self.typing_races:
            await interaction.response.send_message(
                "A typing race is already running in this channel.", ephemeral=True
            )
            return
        self.typing_races.add(channel_id)
        phrase = random.choice(TYPING_RACE_PHRASES)
        waiting = discord.ui.LayoutView()
        waiting.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Typing Race\nThe sentence appears in **3 seconds**. Get ready."
                )
            )
        )
        await interaction.response.send_message(view=waiting)
        try:
            await asyncio.sleep(3)
            race = discord.ui.LayoutView()
            race.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        "## Type This First\n"
                        f"```\n{phrase}\n```\n"
                        "-# Exact spelling and punctuation required · 30 second limit"
                    )
                )
            )
            await interaction.edit_original_response(view=race)
            started = time.perf_counter()

            def correct(message: discord.Message) -> bool:
                return (
                    message.channel.id == channel_id
                    and not message.author.bot
                    and message.content.strip() == phrase
                )

            try:
                winner = await self.bot.wait_for("message", check=correct, timeout=30)
            except asyncio.TimeoutError:
                timed_out = discord.ui.LayoutView()
                timed_out.add_item(
                    discord.ui.Container(
                        discord.ui.TextDisplay(
                            "## Typing Race Ended\nNobody typed the sentence correctly in time."
                        )
                    )
                )
                await interaction.edit_original_response(view=timed_out)
                return
            elapsed = max(0.01, time.perf_counter() - started)
            wpm = round(len(phrase.split()) * 60 / elapsed)
            finished = discord.ui.LayoutView()
            finished.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        "## Typing Race Winner\n"
                        f"{winner.author.mention} finished first.\n\n"
                        f"**Time:** `{elapsed:.2f}s`\n"
                        f"**Speed:** `{wpm:,} WPM`"
                    )
                )
            )
            await interaction.edit_original_response(view=finished)
        finally:
            self.typing_races.discard(channel_id)

    @app_commands.command(name="would-you-rather",description="Create a Would You Rather vote")
    async def would_you_rather(self,interaction:discord.Interaction,option_a:str|None=None,option_b:str|None=None)->None:
        if bool(option_a)!=bool(option_b):await interaction.response.send_message("Provide both custom options or leave both empty.",ephemeral=True);return
        if option_a and option_b:question=f"Would you rather {option_a} OR {option_b}?";choices=[option_a,option_b]
        else:
            await interaction.response.defer()
            try:question=await self.party_question("wyr");parts=re.split(r"\s+OR\s+",re.sub(r"^Would you rather\s+","",question,flags=re.I),maxsplit=1,flags=re.I);choices=parts if len(parts)==2 else ["Option A","Option B"]
            except (aiohttp.ClientError,asyncio.TimeoutError,KeyError):question="Would you rather explore space OR the deepest ocean?";choices=["Explore space","Explore the deepest ocean"]
            await interaction.followup.send(view=WYRView(question,choices));return
        await interaction.response.send_message(view=WYRView(question,choices))

    @app_commands.command(name="truth-or-dare",description="Get a truth or dare question")
    @app_commands.choices(kind=[app_commands.Choice(name="Truth",value="truth"),app_commands.Choice(name="Dare",value="dare"),app_commands.Choice(name="Random",value="random")],rating=[app_commands.Choice(name="PG",value="pg"),app_commands.Choice(name="PG-13",value="pg13")])
    async def truth_or_dare(self,interaction:discord.Interaction,kind:app_commands.Choice[str],rating:app_commands.Choice[str]|None=None,custom:str|None=None)->None:
        selected=random.choice(("truth","dare")) if kind.value=="random" else kind.value
        await interaction.response.defer()
        if custom:question=custom
        else:
            try:question=await self.party_question(selected,rating.value if rating else "pg")
            except (aiohttp.ClientError,asyncio.TimeoutError,KeyError):question="What is something you have always wanted to try?" if selected=="truth" else "Do your best dramatic movie-trailer voice."
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## {selected.title()}\n{question}"),discord.ui.Separator(),discord.ui.TextDisplay("-# Truth or Dare API · custom fallback available")));await interaction.followup.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
