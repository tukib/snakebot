import discord
from discord.ext import commands
import orjson
import platform
import os
from datetime import datetime
import psutil
import logging
from PIL import Image
from io import BytesIO
import difflib
import cogs.utils.database as DB


class events(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def poll_check(self, payload):
        """Keeps track of poll results.

        payload: discord.RawReactionActionEvent
            A payload of raw data about the reaction and member.
        """
        if not payload.guild_id or payload.emoji.is_custom_emoji():
            return

        polls = DB.db.get(b"polls")

        if not polls:
            return

        polls = orjson.loads(polls)
        guild = str(payload.guild_id)

        if guild not in polls:
            return

        message = str(payload.message_id)

        print(polls[guild], payload.message_id)

        if message not in polls[guild]:
            return

        if payload.emoji.name not in polls[guild][message]:
            return

        polls[guild][message][payload.emoji.name]["count"] += 1

        DB.db.put(b"polls", orjson.dumps(polls))

    async def emoji_submission_check(self, payload):
        """Checks if an emoji submission has passed 8 votes.

        payload: discord.RawReactionActionEvent
            A payload of raw data about the reaction and member.
        """
        emojis = DB.db.get(b"emoji_submissions")

        if not payload.emoji.is_custom_emoji():
            return

        if not emojis or payload.emoji.name.lower() != "upvote":
            return

        emojis = orjson.loads(emojis)
        message_id = str(payload.message_id)

        if message_id not in emojis:
            return

        if payload.user_id not in emojis[message_id]["users"]:
            emojis[message_id]["users"].append(payload.user_id)

        if len(emojis[message_id]["users"]) >= 8:
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            file = message.attachments[0]
            file = BytesIO(await file.read())
            file = Image.open(file)
            file.thumbnail((256, 256), Image.LANCZOS)

            imgByteArr = BytesIO()
            file.save(imgByteArr, format="PNG")
            file = imgByteArr.getvalue()

            name = emojis[message_id]["name"]

            if not discord.utils.get(message.guild.emojis, name=name):
                emoji = await message.guild.create_custom_emoji(name=name, image=file)
                await message.add_reaction(emoji)

            emojis.pop(message_id)

        DB.db.put(b"emoji_submissions", orjson.dumps(emojis))

    async def reaction_role_check(self, payload):
        """Checks if a reaction was on a reaction role message.

        payload: discord.RawReactionActionEvent
            A payload of raw data about the reaction and member.
        """
        message_id = str(payload.message_id).encode()
        reaction = DB.rrole.get(message_id)

        if not reaction:
            return

        reaction = orjson.loads(reaction)

        if str(payload.emoji) in reaction:
            role_id = int(reaction[str(payload.emoji)])
        elif payload.emoji.name in reaction:
            role_id = int(reaction[payload.emoji.name])
        else:
            return

        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id)
        if payload.event_type == "REACTION_REMOVE":
            return (role, guild)
        return role

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Gives roles based off reaction added if message in reaction_roles.json.

        payload: discord.RawReactionActionEvent
            A payload of raw data about the reaction and member.
        """
        if payload.member == self.bot.user:
            return

        await self.emoji_submission_check(payload)
        await self.poll_check(payload)

        role = await self.reaction_role_check(payload)
        if role is not None:
            await payload.member.add_roles(role)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Removes roles based off reaction added if message in reaction_roles.json.

        payload: discord.RawReactionActionEvent
            A payload of raw data about the reaction and member.
        """
        try:
            role, guild = await self.reaction_role_check(payload)
        except TypeError:
            return
        if role is not None:
            member = guild.get_member(payload.user_id)
            await member.remove_roles(role)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """The event called when a reaction is added to a message in the cache.

        reaction: discord.Reaction
        user: Union[discord.User, discord.Member]
        """
        if not reaction.custom_emoji:
            return

        if reaction.message.author == user:
            return

        time_since = (datetime.utcnow() - reaction.message.created_at).total_seconds()

        if time_since > 1800:
            return

        if reaction.emoji.name.lower() == "downvote":
            await DB.add_karma(reaction.message.author.id, -1)
        elif reaction.emoji.name.lower() == "upvote":
            await DB.add_karma(reaction.message.author.id, 1)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        """The event called when a reaction is removed from a message in the cache.

        reaction: discord.Reaction
        user: Union[discord.User, discord.Member]
        """
        if not reaction.custom_emoji:
            return

        if reaction.message.author == user:
            return

        time_since = (datetime.utcnow() - reaction.message.created_at).total_seconds()

        if time_since > 1800:
            return

        if reaction.emoji.name.lower() == "downvote":
            await DB.add_karma(reaction.message.author.id, 1)
        elif reaction.emoji.name.lower() == "upvote":
            await DB.add_karma(reaction.message.author.id, -1)

    @commands.Cog.listener()
    async def on_reaction_clear(self, message, reactions):
        """The event called when the reactions on a message are cleared.

        message: discord.Message
        reactions: List[discord.Reaction]
        """
        if await DB.get_blacklist(message.author.id, message.guild.id) == b"1":
            await message.add_reaction("<:downvote:766414744730206228>")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Disconnects a member from voice if they are downvoted.

        member: discord.Member
            The member.
        before: discord.VoiceState
            The old voice state.
        after: discord.VoiceState
            The new voice state.
        """
        if not after.channel:
            return

        if await DB.get_blacklist(member.id, member.guild.id) == b"1":
            await member.edit(voice_channel=None)
            await DB.add_karma(member.id, -1)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        """Logs edited messages to the logs channel.

        before: discord.Message
            The old message.
        after: discord.Message
            The new message.
        """
        if (
            not before.guild
            or DB.db.get(f"{after.guild.id}-logging".encode())
            or not after.content
            or before.content == after.content
            or after.author == self.bot.user
        ):
            return

        member_id = str(after.author.id).encode()
        edited = DB.edited.get(member_id)

        if not edited:
            edited = {}
        else:
            edited = orjson.loads(edited)

        date = str(datetime.now())[:-7]
        edited[date] = [before.content, after.content]
        DB.edited.put(member_id, orjson.dumps(edited))
        DB.db.put(
            f"{before.guild.id}-editsnipe_message".encode(),
            orjson.dumps([before.content, after.content, before.author.display_name]),
        )

        if after.content.startswith("https"):
            return

        channel = discord.utils.get(after.guild.channels, name="logs")

        if not channel:
            return

        # Replaces backticks with a backtick and a zero width space
        before.content = before.content.replace("`", "`​")
        after.content = after.content.replace("`", "`​")

        embed = discord.Embed(
            title=f"{before.author.display_name} edited:",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="From:", value=f"```{before.content}```")
        embed.add_field(name="To:", value=f"```{after.content}```")
        embed.set_footer(text=f"Member ID: {before.author.id}")

        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Logs deleted messages to the logs channel.

        message: discord.Message
        """
        if (
            not message.guild
            or DB.db.get(f"{message.guild.id}-logging".encode())
            or DB.db.get(b"playing_chess")
            or message.author == self.bot.user
            or not message.content
            and not message.attachments
        ):
            return

        image_urls = [
            attachment.url
            for attachment in message.attachments
            if attachment.content_type.startswith("image/")
        ]

        content = "{}\n{}".format(
            (message.content.replace("`", "`​") if message.content else ""),
            "\n".join(image_urls),
        )

        member_id = str(message.author.id).encode()
        deleted = DB.deleted.get(member_id)

        if not deleted:
            deleted = {}
        else:
            deleted = orjson.loads(deleted)

        date = str(datetime.now())[:-7]
        deleted[date] = message.content

        DB.deleted.put(member_id, orjson.dumps(deleted))
        DB.db.put(
            f"{message.guild.id}-snipe_message".encode(),
            orjson.dumps([content, message.author.display_name]),
        )

        if message.raw_mentions:
            timesince = datetime.utcnow() - message.created_at

            if timesince.total_seconds() < 30:
                DB.blacklist.put(
                    f"{message.guild.id}-{message.author.id}".encode(), b"1"
                )

        channel = discord.utils.get(message.guild.channels, name="logs")

        if not channel:
            return

        embed = discord.Embed(
            title=f"{message.author.display_name} deleted:",
            description=f"```\n{content}```",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Member ID: {message.author.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Downvotes blacklisted members.

        message: discord.Message
        """
        if message.guild:
            guild = message.guild.id

            key = f"{guild}-{message.author.id}".encode()
            count = DB.message_count.get(key)

            if count:
                count = int(count) + 1
            else:
                count = 1

            DB.message_count.put(key, str(count).encode())
        else:
            guild = None

        if await DB.get_blacklist(message.author.id, guild) == b"1":
            await message.add_reaction("<:downvote:766414744730206228>")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Puts members nickname history into the db.

        before: discord.Member
            The member object before the update.
        after: discord.Member
            The member object after the update.
        """
        if before.nick == after.nick:
            return

        member_id = str(after.id).encode()

        nicks = DB.nicks.get(member_id)

        if not nicks:
            nicks = {"nicks": {}, "names": {}}
        else:
            nicks = orjson.loads(nicks)

        now = str(datetime.now())[:-7]

        if "current" in nicks["nicks"]:
            date = nicks["nicks"]["current"][1]
        else:
            date = now

        nicks["nicks"][date] = before.nick
        nicks["nicks"]["current"] = [after.nick, now]

        DB.nicks.put(member_id, orjson.dumps(nicks))

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        """Puts users name history into the db.

        before: discord.User
            The user object before the update.
        after: discord.User
            The user object after the update.
        """
        if before.name == after.name:
            return

        member_id = str(after.id).encode()

        names = DB.nicks.get(member_id)

        if not names:
            names = {"nicks": {}, "names": {}}
        else:
            names = orjson.loads(names)

        now = str(datetime.now())[:-7]

        if "current" in names["names"]:
            date = names["names"]["current"][1]
        else:
            date = now

        names["names"][date] = before.name
        names["names"]["current"] = [after.name, now]

        DB.nicks.put(member_id, orjson.dumps(names))

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Checks which invite someone has joined from.

        member: discord.Member
        """
        for invite in await member.guild.invites():
            key = f"{invite.code}-{invite.guild.id}"
            uses = DB.invites.get(key.encode())

            if not uses:
                DB.invites.put(key.encode(), str(invite.uses).encode())
                continue

            if invite.uses > int(uses):
                DB.invites.put(str(member.id).encode(), invite.code.encode())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Logs when a member leaves a guild.

        member: discord.Member
        """
        channel = discord.utils.get(member.guild.channels, name="logs")

        if not channel:
            return

        embed = discord.Embed(color=discord.Color.blurple())
        embed.description = (
            f"```{member.display_name} left the server" f"\n\nMember ID: {member.id}```"
        )

        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        """Puts invites into the db to get who used the invite.

        invite: discord.Invite
        """
        key = f"{invite.code}-{invite.guild.id}"
        DB.invites.put(key.encode(), str(invite.uses).encode())

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        """Removes invites from the db when they have been deleted.

        invite: discord.Invite
        """
        DB.invites.delete(f"{invite.code}-{invite.guild.id}".encode())

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.

        error: Exception
        """
        if hasattr(ctx.command, "on_error"):
            return

        cog = ctx.cog
        if cog:
            attr = f"_{cog.__class__.__name__}__error"
            if hasattr(cog, attr):
                return

        error = getattr(error, "original", error)
        embed = discord.Embed(color=discord.Color.dark_red())

        if (
            str(error)[:19] == "The check functions"
            or str(error)[:16] == "The global check"
        ):
            return

        if isinstance(error, commands.errors.CommandNotFound):
            if ctx.message.content.startswith(ctx.prefix * 2):
                return

            invoked = ctx.message.content.split()[0].removeprefix(ctx.prefix)

            all_commands = [
                str(command)
                for command in self.bot.walk_commands()
                if not command.hidden
            ]

            matches = difflib.get_close_matches(invoked, all_commands, cutoff=0.5)

            if len(matches) == 0:
                return

            message = "Did you mean:\n\n" + "\n".join(matches)
            embed.title = f"Command {invoked} not found."

        elif isinstance(error, commands.errors.CommandOnCooldown):
            cooldown = int(error.cooldown.get_retry_after())
            message = "You are on cooldown. Try again in {} hours {} minutes and {} seconds".format(
                cooldown // 3600, (cooldown % 3600) // 60, (cooldown % 3600) % 60
            )

        elif isinstance(error, discord.Forbidden):
            message = "I do not have the required permissions to run this command."

        elif isinstance(
            error, (commands.BadArgument, commands.errors.MissingRequiredArgument)
        ):
            ctx.command.reset_cooldown(ctx)
            message = (
                f"{error}\n\nUsage:\n{ctx.prefix}{ctx.command} {ctx.command.signature}"
            )

        elif isinstance(error, commands.errors.ExtensionNotFound):
            message = f"Extension '{error.name}' was not found."

        elif isinstance(error, commands.errors.BotMissingAnyRole):
            message = (
                f"{self.bot.user.name} is missing required roles: {error.missing_roles}"
            )

        elif isinstance(error, commands.errors.BotMissingPermissions):
            message = f"{self.bot.user.name} is missing required permissions: {error.missing_perms}"

        else:
            logging.getLogger("discord").warning(
                f"Unhandled Error: {ctx.command.qualified_name}, Error: {error}, Type: {type(error)}"
            )
            message = error

        if len(str(message)) == 0:
            logging.getLogger("discord").warning(
                f"{ctx.command.qualified_name}, Error: {error}"
            )
            return

        embed.description = f"```{message}```"
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is done preparing the data received from Discord."""
        if not hasattr(self.bot, "uptime"):
            boot_time = (
                datetime.now().timestamp() - psutil.Process(os.getpid()).create_time()
            )

            self.bot.uptime = datetime.utcnow()
            boot_times = DB.db.get(b"boot_times")

            if boot_times:
                boot_times = orjson.loads(boot_times)
            else:
                boot_times = []

            boot_times.append(round(boot_time, 5))
            DB.db.put(b"boot_times", orjson.dumps(boot_times))

            # Wipe the cache and polls as we have no way of knowing if it has expired
            DB.db.put(b"cache", b"{}")
            DB.db.delete(b"polls")

            print(
                f"Logged in as {self.bot.user.name}\n"
                f"Discord.py version: {discord.__version__}\n"
                f"Python version: {platform.python_version()}\n"
                f"Running on: {platform.system()} {platform.release()}({os.name})\n"
                f"Boot time: {boot_time:.3f}s\n"
                "-------------------"
            )

    async def bot_check_once(self, ctx):
        """Checks if a user blacklisted and the if the command is disabled."""
        if ctx.author.id in self.bot.owner_ids:
            return True

        if ctx.guild:
            disabled = DB.db.get(f"{ctx.guild.id}-disabled_channels".encode())

            if (
                disabled
                and ctx.command.name != "disable_channel"
                and str(ctx.guild.id) in (disabled := orjson.loads(disabled))
            ):
                if ctx.channel.id in disabled[str(ctx.guild.id)]:
                    return False

            if ctx.guild and DB.db.get(f"{ctx.guild.id}-{ctx.command}".encode()):
                await ctx.send(
                    embed=discord.Embed(
                        color=discord.Color.red(), description="```Command disabled```"
                    )
                )
                return False

        if await DB.get_blacklist(ctx.author.id, ctx.guild.id if ctx.guild else None):
            await ctx.send(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    description="```You are blacklisted from using commands```",
                )
            )
            return False

        return True

    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Resets command cooldown for owners."""
        logging.getLogger("discord").info(
            f"{ctx.author.id} ran the command {ctx.command.qualified_name}"
        )
        if ctx.author.id in self.bot.owner_ids:
            ctx.command.reset_cooldown(ctx)


def setup(bot: commands.Bot) -> None:
    """Starts events cog."""
    bot.add_cog(events(bot))
