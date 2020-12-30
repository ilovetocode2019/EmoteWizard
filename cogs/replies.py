import discord
from discord.ext import commands

import functools
import io
import datetime
import typing
from PIL import Image, ImageDraw, ImageOps

from .utils import converters

class Reply:
    def __init__(self, message, reply, author, emoji, mention):
        self.message = message
        self.reply = reply
        self.author = author
        self.emoji = emoji
        self.mention = mention

    def __str__(self):
        author = f"> {self.emoji} {self.message.author.mention}{f'<:bottag:779737977856720906>' if self.message.author.bot else ''}"
        reply = f"> [Jump to message](<{self.message.jump_url}>) \n{discord.utils.escape_mentions(self.reply)}"

        if self.message.content:
            content = "\n".join([f"> {discord.utils.escape_mentions(line)}" for line in self.message.content.split("\n")])
        else:
            content = "> Jump to view embed(s) <:imageicon:779737947121123349>"

        return f"{author} \n{content} \n{reply}"

class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="reply", description="Reply to a message", invoke_without_command=True)
    @commands.bot_has_permissions(manage_messages=True, manage_webhooks=True)
    async def reply(self, ctx, channel: typing.Optional[discord.TextChannel], message: converters.MessageConverter, *, reply):
        channel = channel if isinstance(channel, discord.TextChannel) else ctx.channel
        if not message:
            messages = await channel.history(limit=1, before=ctx.message).flatten()
            if not messages:
                return await ctx.send(":x: I couldn't find a message to react to")
            message = messages[0]

        mention = True
        if reply.startswith("--no-mention"):
            mention = False
            reply = reply[len("--no-mention"):]
        elif reply.startswith("-n"):
            mention = False
            reply = reply[len("-n"):]

        config = await self.bot.get_webhook_config(ctx.guild)
        webhook = await config.webhook()
        if not webhook:
            return await ctx.send(":x: No webhook is set")

        # Fetch emoji
        emoji = self.bot.avatar_emojis.get(message.author.id)

        # If the emoji does not exist or the emoji is an outdated avatar, make a new emoji
        if not emoji or emoji["avatar_url"] != str(message.author.avatar_url) or not self.bot.get_emoji(emoji["emoji_id"]):
            # If the emoji is outdated, delete it
            if emoji and emoji["avatar_url"] != str(message.author.avatar_url):
                emoji = self.bot.get_emoji(emoji["emoji_id"])
                await emoji.delete()

            # If the emoji slots are full, remove the oldest used one
            if len(self.bot.stickers_guild.emojis) >= 50:
                emojis = self.bot.avatar_emojis.values()
                emojis = sorted(emojis, key = lambda x: x["last_used"])
                to_delete = emojis[0]
                await to_delete.delete()

                # Remove emoji from database
                query = """DELETE FROM avatar_emojis
                           WHERE avatar_emojis.emoji_id=$1;
                        """
                await self.bot.db.execute(query, to_delete.id)

                # Pop the emoji out of the cache
                for emoji in self.bot.avatar_emojis:
                    if emoji["emoij_id"] == to_delete.id:
                        self.bot.avatar_emojis.pop(emoji["user_id"])

            emoji = await self.create_avatar_emoji(message.author)

            # Update/insert a row
            query = """INSERT INTO avatar_emojis (user_id, emoji_id, avatar_url)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (user_id)
                       DO UPDATE SET emoji_id=$2, avatar_url=$3, last_used=$4;
                    """
            await self.bot.db.execute(query, message.author.id, emoji.id, str(message.author.avatar_url), datetime.datetime.utcnow())

            # Update cache
            self.bot.avatar_emojis[message.author.id] = {"user_id": ctx.author.id, "emoji_id": emoji.id, "avatar_url": str(message.author.avatar_url), "last_used": datetime.datetime.utcnow()}

        # Otherwise just fetch the emoji and update the row
        else:
            emoji = self.bot.get_emoji(emoji["emoji_id"])

            # Update the last used
            query = """UPDATE avatar_emojis
                       SET last_used=$1
                       WHERE avatar_emojis.user_id=$2;
                    """
            await self.bot.db.execute(query, datetime.datetime.utcnow(), message.author.id)

            # Update cache
            self.bot.avatar_emojis[message.author.id]["last_used"] = datetime.datetime.utcnow()

        # Prepare content
        reply = Reply(message, reply, ctx.author, emoji, mention)
        content = str(reply)

        # Send message
        await ctx.message.delete()

        # Update webhook if needed
        if webhook.channel_id != ctx.channel.id:
            await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

        message = await webhook.send(content=content, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url, allowed_mentions=discord.AllowedMentions(users=mention), wait=True)
        self.bot.reposted_messages[message.id] = reply

    async def create_avatar_emoji(self, user):
        # Fetch the avatar
        async with self.bot.session.get(str(user.avatar_url_as(format="png"))) as resp:
            avatar = io.BytesIO(await resp.read())
            avatar = Image.open(avatar)

        # Round it
        mask = Image.new("L", (128, 128), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + (128, 128), fill=255)

        output = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
        output.putalpha(mask)

        # Save to file
        avatar = io.BytesIO()
        output.save(avatar, "PNG")
        avatar.seek(0)

        return await self.bot.stickers_guild.create_custom_emoji(name=f"user_{user.id}", image=avatar.read())

def setup(bot):
    bot.add_cog(Replies(bot))
