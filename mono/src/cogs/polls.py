from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


DB = Path(__file__).resolve().parents[2] / ".cache" / "polls.db"


class PollStore:
    def __init__(self) -> None:
        DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS polls(
              message_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL,
              owner_id INTEGER NOT NULL, question TEXT NOT NULL, options TEXT NOT NULL,
              max_choices INTEGER NOT NULL, anonymous INTEGER NOT NULL, ends_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS poll_votes(
              message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, choices TEXT NOT NULL,
              PRIMARY KEY(message_id,user_id), FOREIGN KEY(message_id) REFERENCES polls(message_id) ON DELETE CASCADE
            );""")
    @contextmanager
    def connect(self):
        con=sqlite3.connect(DB,timeout=30);con.row_factory=sqlite3.Row;con.execute("PRAGMA foreign_keys=ON")
        try:yield con;con.commit()
        except Exception:con.rollback();raise
        finally:con.close()
    def add(self,message_id,channel_id,owner_id,question,options,max_choices,anonymous,ends_at):
        with self.connect() as con:con.execute("INSERT INTO polls VALUES(?,?,?,?,?,?,?,?)",(message_id,channel_id,owner_id,question,json.dumps(options),max_choices,int(anonymous),ends_at))
    def polls(self):
        with self.connect() as con:return con.execute("SELECT * FROM polls").fetchall()
    def poll(self,message_id):
        with self.connect() as con:return con.execute("SELECT * FROM polls WHERE message_id=?",(message_id,)).fetchone()
    def votes(self,message_id):
        with self.connect() as con:return con.execute("SELECT * FROM poll_votes WHERE message_id=?",(message_id,)).fetchall()
    def toggle(self,message_id,user_id,index,max_choices):
        with self.connect() as con:
            row=con.execute("SELECT choices FROM poll_votes WHERE message_id=? AND user_id=?",(message_id,user_id)).fetchone();choices=set(json.loads(row[0])) if row else set()
            if index in choices:choices.remove(index)
            elif len(choices)>=max_choices:return False
            else:choices.add(index)
            if choices:con.execute("INSERT INTO poll_votes VALUES(?,?,?) ON CONFLICT(message_id,user_id) DO UPDATE SET choices=excluded.choices",(message_id,user_id,json.dumps(sorted(choices))))
            else:con.execute("DELETE FROM poll_votes WHERE message_id=? AND user_id=?",(message_id,user_id))
            return True
    def delete(self,message_id):
        with self.connect() as con:con.execute("DELETE FROM polls WHERE message_id=?",(message_id,))


poll_store=PollStore()


class VoteButton(discord.ui.Button):
    def __init__(self,poll_id:int,index:int,label:str):super().__init__(label=label[:80],style=discord.ButtonStyle.primary,custom_id=f"poll:{poll_id}:{index}");self.index=index
    async def callback(self,i):
        view=self.view;assert isinstance(view,PollView)
        accepted=await asyncio.to_thread(poll_store.toggle,view.poll_id,i.user.id,self.index,view.max_choices)
        if not accepted:await i.response.send_message(f"You can choose up to {view.max_choices} option(s).",ephemeral=True);return
        view.render();await i.response.edit_message(view=view)


class PollView(discord.ui.LayoutView):
    def __init__(self,poll_id:int,owner_id:int,question:str,options:list[str],max_choices:int,anonymous:bool,ended:bool=False):
        super().__init__(timeout=None);self.poll_id=poll_id;self.owner_id=owner_id;self.question=question;self.options=options;self.max_choices=max_choices;self.anonymous=anonymous;self.ended=ended;self.render()
    def render(self):
        self.clear_items();votes=poll_store.votes(self.poll_id) if self.poll_id else [];counts=[0]*len(self.options)
        for row in votes:
            for index in json.loads(row["choices"]):
                if 0<=index<len(counts):counts[index]+=1
        voters=len(votes);lines=[]
        for option,count in zip(self.options,counts):
            percent=round(count/voters*100) if voters else 0;lines.append(f"**{option}**\n`{'█'*round(percent/10)}{'░'*(10-round(percent/10))}` {count} ({percent}%)")
        state="Poll closed" if self.ended else f"Choose up to {self.max_choices} · Votes can be changed"
        items=[discord.ui.TextDisplay(f"## {self.question}\n"+"\n\n".join(lines)),discord.ui.Separator(),discord.ui.TextDisplay(f"-# {state} · {voters} voter(s) · {'Anonymous' if self.anonymous else 'Public'}")]
        if not self.ended:
            items.append(discord.ui.ActionRow(*(VoteButton(self.poll_id,index,option) for index,option in enumerate(self.options))))
        self.add_item(discord.ui.Container(*items))


class Polls(commands.Cog):
    poll_group = app_commands.Group(
        name="poll",
        description="Create and manage polls",
    )

    def __init__(self,bot):self.bot=bot;self.timers={}
    async def cog_load(self):
        now=int(time.time())
        for row in await asyncio.to_thread(poll_store.polls):
            options=json.loads(row["options"]);view=PollView(row["message_id"],row["owner_id"],row["question"],options,row["max_choices"],bool(row["anonymous"]));self.bot.add_view(view,message_id=row["message_id"])
            if row["ends_at"]:self.timers[row["message_id"]]=asyncio.create_task(self.timer(row["message_id"],max(0,row["ends_at"]-now)))
    def cog_unload(self):
        for task in self.timers.values():task.cancel()
    async def timer(self,message_id,delay):
        await asyncio.sleep(delay);await self.close_poll(message_id)
    async def close_poll(self,message_id):
        row=await asyncio.to_thread(poll_store.poll,message_id)
        if not row:return False
        options=json.loads(row["options"]);view=PollView(message_id,row["owner_id"],row["question"],options,row["max_choices"],bool(row["anonymous"]),True)
        channel=self.bot.get_channel(row["channel_id"])
        if channel:
            try:message=await channel.fetch_message(message_id);await message.edit(view=view)
            except discord.HTTPException:pass
        await asyncio.to_thread(poll_store.delete,message_id);task=self.timers.pop(message_id,None)
        if task and task is not asyncio.current_task():task.cancel()
        return True
    async def can_manage(self,i,row):
        return i.user.id==row["owner_id"] or bool(i.guild and i.permissions.manage_messages)

    @poll_group.command(name="create",description="Create a timed multiple-choice poll")
    @app_commands.default_permissions(create_polls=True)
    async def poll_create(self,i:discord.Interaction,question:str,option_1:str,option_2:str,option_3:str|None=None,option_4:str|None=None,option_5:str|None=None,duration_minutes:app_commands.Range[int,1,10080]|None=None,max_choices:app_commands.Range[int,1,5]=1,anonymous:bool=True):
        if i.guild is not None and not i.permissions.create_polls:
            await i.response.send_message(
                "You need the **Create Polls** permission to use this command here.",
                ephemeral=True,
            )
            return
        options=[x for x in (option_1,option_2,option_3,option_4,option_5) if x]
        if len(set(map(str.casefold,options)))!=len(options):await i.response.send_message("Every option must be different.",ephemeral=True);return
        if max_choices>len(options):await i.response.send_message("Maximum choices cannot exceed the number of options.",ephemeral=True);return
        await i.response.send_message("Creating poll…");message=await i.original_response();ends=int(time.time())+duration_minutes*60 if duration_minutes else None
        await asyncio.to_thread(poll_store.add,message.id,message.channel.id,i.user.id,question,options,max_choices,anonymous,ends)
        view=PollView(message.id,i.user.id,question,options,max_choices,anonymous);await message.edit(content=None,view=view)
        if ends:self.timers[message.id]=asyncio.create_task(self.timer(message.id,duration_minutes*60))

    @poll_group.command(name="close",description="Close a poll by message ID")
    async def poll_close(self,i:discord.Interaction,message_id:str):
        try:poll_id=int(message_id)
        except ValueError:await i.response.send_message("Enter a valid poll message ID.",ephemeral=True);return
        row=await asyncio.to_thread(poll_store.poll,poll_id)
        if not row:await i.response.send_message("That active poll was not found.",ephemeral=True);return
        if not await self.can_manage(i,row):await i.response.send_message("Only the poll creator or a moderator can close it.",ephemeral=True);return
        await self.close_poll(poll_id);await i.response.send_message("Poll closed.")

    @poll_group.command(name="votes",description="DM the voters and their choices for a poll")
    async def poll_votes(self,i:discord.Interaction,message_id:str):
        try:poll_id=int(message_id)
        except ValueError:await i.response.send_message("Enter a valid poll message ID.",ephemeral=True);return
        row=await asyncio.to_thread(poll_store.poll,poll_id)
        if not row:await i.response.send_message("That active poll was not found. Vote details are deleted when polls close.",ephemeral=True);return
        if not await self.can_manage(i,row):await i.response.send_message("Only the poll creator or a moderator can inspect votes.",ephemeral=True);return
        options=json.loads(row["options"]);groups=[[] for _ in options]
        for vote in await asyncio.to_thread(poll_store.votes,poll_id):
            for index in json.loads(vote["choices"]):groups[index].append(f"<@{vote['user_id']}>")
        text="\n\n".join(f"**{option}**\n"+("\n".join(users) if users else "No votes") for option,users in zip(options,groups));view=discord.ui.LayoutView();view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## Votes · {row['question']}\n{text}")))
        try:await i.user.send(view=view)
        except discord.HTTPException:await i.response.send_message("I couldn't DM you. Enable direct messages and try again.",ephemeral=True);return
        await i.response.send_message(
            "I sent the vote breakdown to your DMs.",
            ephemeral=True,
        )


async def setup(bot):await bot.add_cog(Polls(bot))
