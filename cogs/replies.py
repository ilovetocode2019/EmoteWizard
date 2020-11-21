import discord
from discord.ext import commands

import datetime
import io
from PIL import Image, ImageDraw, ImageOps

class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="reply", description="Reply to a message", invoke_without_command=True)
    async def reply(self, ctx, message: discord.Message, *, reply):
        mention = True
        if reply.startswith("--no-mention"):
            mention = False
            reply = reply[len("--no-mention"):]
        elif reply.startswith("-n"):
            mention = False
            reply = reply[len("-n"):]

        # Fetch webhook and emoji
        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        emoji = self.bot.avatar_emojis.get(message.author.id)

        # If the emoji does not exist or the emoji is an outdated avatar, make a new emoji
        if not emoji or emoji["avatar_url"] != str(message.author.avatar_url) or not self.bot.get_emoji(emoji["emoji_id"]):
            # If the emoji is outdated, delete it
            if emoji and emoji["avatar_url"] != str(message.author.avatar_url):
                emoji = self.bot.get_emoji(emoji["emoji_id"])
                await emoji.delete()

            # If the emoji slots are full, 
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

            # Fetch the avatar
            async with self.bot.session.get(str(message.author.avatar_url)) as resp:
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
            output.save(avatar, "PNG", trancparency=(0, 0, 0))
            avatar.seek(0)

            # Create the new emoji
            emoji = await self.bot.stickers_guild.create_custom_emoji(name=f"user_{message.author.id}", image=avatar.read())

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
        content = f"> {emoji} **{message.author.mention}** \n> {message.content} \n> [Jump to message](<{message.jump_url}>) \n{discord.utils.escape_mentions(reply)}"

        # Send message
        if ctx.guild.me.guild_permissions.manage_messages and ctx.guild.me.guild_permissions.manage_webhooks and webhook and webhook["webhook_id"]:
            await ctx.message.delete()

            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])

            # Update webhook if needed
            if webhook.channel_id != ctx.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

            await webhook.send(content=content, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url, allowed_mentions=discord.AllowedMentions(users=mention))
        else:
            await ctx.send(":x: I am missing the permissions I need to send a reply", delete_after=5)

    @reply.command(name="embed", description="Reply to a message using an embed")
    async def reply_embed(self, ctx, message: discord.Message, *, reply):
        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        em = discord.Embed(description=f"{message.content} \n\n[Jump to message]({message.jump_url})", color=discord.Color.blurple())
        em.set_author(name=message.author.display_name, icon_url=message.author.avatar_url)
        em.add_field(name="Reply", value=reply)

        if ctx.guild.me.guild_permissions.manage_messages and ctx.guild.me.guild_permissions.manage_webhooks and webhook and webhook["webhook_id"]:
            await ctx.message.delete()

            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            if webhook.channel_id != ctx.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

            await webhook.send(embed=em, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url)
        else:
            await ctx.send(embed=em)

def setup(bot):
    bot.add_cog(Replies(bot))
