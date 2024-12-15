import discord
from discord.ext import commands

import functools
import io
import datetime
import typing
from PIL import Image, ImageDraw, ImageOps

from .utils import checks, converters, faked, formats

class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="reply", description="Reply to a message", invoke_without_command=True)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True, manage_webhooks=True)
    async def reply(self, ctx, message: converters.MessageConverter, *, content):
        if content.startswith("--no-mention"):
            mention = False
            content = content[len("--no-mention"):]
        elif content.startswith("-n"):
            mention = False
            content = content[len("-n"):]
        else:
            mention = True

        config = await self.bot.get_webhook_config(ctx.guild)
        webhook = await config.webhook()
        if not webhook:
            return await ctx.send(":x: No webhook is set")

        # Fetch emoji
        emoji = self.bot.avatar_emojis.get(message.author.id)

        # If the emoji does not exist or the emoji is an outdated avatar, make a new emoji
        if not emoji or emoji["avatar_url"] != message.author.display_avatar.url or not self.bot.get_emoji(emoji["emoji_id"]):
            # If the emoji is outdated, delete it
            if emoji and emoji["avatar_url"] != message.author.display_avatar.url:
                emoji = self.bot.get_emoji(emoji["emoji_id"])
                await emoji.delete()

            # If the emoji slots are full, remove the oldest used one
            if len(self.bot.guild.emojis) >= 50:
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
            await self.bot.db.execute(
                query,
                message.author.id,
                emoji.id,
                message.author.display_avatar.url,
                datetime.datetime.utcnow()
            )

            # Update cache
            self.bot.avatar_emojis[message.author.id] = {
                "user_id": ctx.author.id,
                "emoji_id": emoji.id,
                "avatar_url": message.author.display_avatar.url,
                "last_used": datetime.datetime.utcnow()
            }

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
        reply = faked.Reply(bot=self.bot, quote=message, emoji=emoji, mention=mention)
        formatted_content, _ = self.bot.replace_emojis(reply.format_with(content))

        await ctx.message.delete()

        # Update webhook if needed
        if webhook.channel != ctx.channel:
            await webhook.edit(channel=ctx.channel)

        replacement = await webhook.send(
            content=formatted_content,
            username=ctx.author.display_name,
            avatar_url=ctx.author.display_avatar.url,
            allowed_mentions=reply.allowed_mentions,
            wait=True
        )

        self.bot.faked_messages[replacement.id] = faked.FakedMessage(
            original=ctx.message,
            replacement=replacement,
            reply=reply
        )

    async def create_avatar_emoji(self, user):
        avatar = io.BytesIO(await user.display_avatar.with_format("png").read())
        avatar = Image.open(avatar).convert("RGBA")

        partial = functools.partial(self.round_avatar, avatar)
        avatar = await self.bot.loop.run_in_executor(None, partial)

        return await self.bot.guild.create_custom_emoji(name=f"user_{user.id}", image=avatar.read())

    def round_avatar(self, avatar):
        mask = Image.new("L", (128, 128), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + (128, 128), fill=255)

        output = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
        output.putalpha(mask)

        avatar = io.BytesIO()
        output.save(avatar, "PNG")
        avatar.seek(0)

        return avatar

async def setup(bot):
    await bot.add_cog(Replies(bot))
