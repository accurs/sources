from discord.ext.commands import group, has_permissions
from discord import TextChannel

from asyncpg import UniqueViolationError

from ...types.plugin import Plugin
from ...types.context import Context

from ...converters.tagscript import TagScript
from ...models.tagscript import ScriptObject
from ...tagscript import parse


class Config(Plugin):
    @group()
    async def prefix(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @prefix.group()
    async def self(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @self.command(name="set")
    async def self_set(self, ctx: Context, *, prefix: str):
        await self.bot.pool.execute(
            """
            INSERT INTO users (id, prefix) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET prefix = $2
            """,
            ctx.author.id,
            prefix,
        )
        return await ctx.respond(f"your prefix has been set to `{prefix}`", state="yes")

    @self.command(name="remove")
    async def self_remove(self, ctx: Context):
        await self.bot.pool.execute(
            """
            INSERT INTO users (id, prefix) VALUES ($1, NULL)
            ON CONFLICT (id) DO UPDATE SET prefix = NULL
            """,
            ctx.author.id,
        )
        return await ctx.respond("your custom prefix has been removed", state="yes")

    @prefix.group()
    async def guild(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @has_permissions(manage_messages=True)
    @guild.command(name="set")
    async def guild_set(self, ctx: Context, *, prefix: str):
        if ctx.guild is None:
            return await ctx.respond(
                "this command can only be used in a guild", state="warn"
            )
        await self.bot.pool.execute(
            """
            INSERT INTO guilds (id, prefix) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET prefix = $2
            """,
            ctx.guild.id,
            prefix,
        )
        return await ctx.respond(
            f"the guild prefix has been set to `{prefix}`", state="yes"
        )

    @has_permissions(manage_messages=True)
    @guild.command(name="remove")
    async def guild_remove(self, ctx: Context):
        if ctx.guild is None:
            return await ctx.respond(
                "this command can only be used in a guild", state="warn"
            )
        await self.bot.pool.execute(
            """
            INSERT INTO guilds (id, prefix) VALUES ($1, NULL)
            ON CONFLICT (id) DO UPDATE SET prefix = NULL
            """,
            ctx.guild.id,
        )
        return await ctx.respond(
            "the guild's custom prefix has been removed", state="yes"
        )

    @group()
    async def welcome(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @welcome.command(name="set")
    @has_permissions(manage_guild=True)
    async def welcome_set(
        self, ctx: Context, channel: TextChannel, *, script: TagScript
    ):
        if destruct := ctx.flags.get("self_destruct"):
            if destruct < 5:
                return await ctx.respond(
                    "self-destruct time must be at least 5 seconds", state="warn"
                )
            if destruct > 86400:
                return await ctx.respond(
                    "self-destruct time cannot exceed 24 hours", state="warn"
                )

        try:
            await self.bot.pool.execute(
                """
                INSERT INTO welcomes (guild_id, channel_id, message, self_destruct) 
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id) DO UPDATE SET 
                    channel_id = $2,
                    message = $3,
                    self_destruct = $4
                """,
                ctx.guild.id,
                channel.id,
                script.script,
                destruct,  # type: ignore
            )
        except UniqueViolationError:
            return await ctx.respond(
                "a welcome message is already configured for this guild", state="warn"
            )

        return await ctx.respond(
            f"created {'an embedded' if script.type == 'embed' else 'a'} join message in {channel.mention}. {'it will selfdestruct after ' + str(destruct) + ' seconds.' if destruct else ''}",
            state="yes",
        )  # type: ignore

    @welcome.command(name="remove")
    @has_permissions(manage_guild=True)
    async def welcome_remove(self, ctx: Context):
        await self.bot.pool.execute(
            """
            DELETE FROM welcomes
            WHERE guild_id = $1
            """,
            ctx.guild.id,  # type: ignore
        )
        return await ctx.respond(
            "the guilds welcome message has been removed", state="yes"
        )

    @welcome.command(name="test")
    @has_permissions(manage_guild=True)
    async def welcome_test(self, ctx: Context):
        record = await self.bot.pool.fetchrow(
            """
            SELECT channel_id, message, self_destruct
            FROM welcomes
            WHERE guild_id = $1
            """,
            ctx.guild.id,  # type: ignore
        )
        if not record:
            return await ctx.respond(
                "no welcome message is configured for this guild", state="warn"
            )

        channel = self.bot.get_channel(record["channel_id"])
        if not isinstance(channel, TextChannel):
            return await ctx.respond(
                "the configured welcome channel is invalid", state="warn"
            )

        script: ScriptObject = parse(
            script=record["message"], user=ctx.author, channel=channel
        )
        await channel.send(
            **script.dump,
            delete_after=record["self_destruct"] if record["self_destruct"] else None,
        )  # type: ignore

    @group()
    async def goodbye(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @goodbye.command(name="set")
    @has_permissions(manage_guild=True)
    async def goodbye_set(
        self, ctx: Context, channel: TextChannel, *, script: TagScript
    ):
        if destruct := ctx.flags.get("self_destruct"):
            if destruct < 5:
                return await ctx.respond(
                    "self-destruct time must be at least 5 seconds", state="warn"
                )
            if destruct > 86400:
                return await ctx.respond(
                    "self-destruct time cannot exceed 24 hours", state="warn"
                )

        try:
            await self.bot.pool.execute(
                """
                INSERT INTO lefts (guild_id, channel_id, message, self_destruct) 
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id) DO UPDATE SET 
                    channel_id = $2,
                    message = $3,
                    self_destruct = $4
                """,
                ctx.guild.id,
                channel.id,
                script.script,
                destruct,  # type: ignore
            )
        except UniqueViolationError:
            return await ctx.respond(
                "a goodbye message is already configured for this guild", state="warn"
            )

        return await ctx.respond(
            f"created {'an embedded' if script.type == 'embed' else 'a'} leave message in {channel.mention}. {'it will selfdestruct after ' + str(destruct) + ' seconds.' if destruct else ''}",
            state="yes",
        )  # type: ignore

    @goodbye.command(name="remove")
    @has_permissions(manage_guild=True)
    async def goodbye_remove(self, ctx: Context):
        await self.bot.pool.execute(
            """
            DELETE FROM lefts
            WHERE guild_id = $1
            """,
            ctx.guild.id,  # type: ignore
        )
        return await ctx.respond(
            "the guild's goodbye message has been removed", state="yes"
        )

    @group()
    async def boosts(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @boosts.command(name="set")
    @has_permissions(manage_guild=True)
    async def boosts_set(
        self, ctx: Context, channel: TextChannel, *, script: TagScript
    ):
        try:
            await self.bot.pool.execute(
                """
                INSERT INTO boosts (guild_id, channel_id, message) 
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id) DO UPDATE SET 
                    channel_id = $2,
                    message = $3
                """,
                ctx.guild.id,
                channel.id,
                script.script,  # type: ignore
            )
        except UniqueViolationError:
            return await ctx.respond(
                "a boost message is already configured for this guild", state="warn"
            )

        return await ctx.respond(
            f"created {'an embedded' if script.type == 'embed' else 'a'} boost message in {channel.mention}.",
            state="yes",
        )  # type: ignore

    @boosts.command(name="remove")
    @has_permissions(manage_guild=True)
    async def boosts_remove(self, ctx: Context):
        await self.bot.pool.execute(
            """
            DELETE FROM boosts
            WHERE guild_id = $1
            """,
            ctx.guild.id,  # type: ignore
        )
        return await ctx.respond(
            "the guild's boost message has been removed", state="yes"
        )
