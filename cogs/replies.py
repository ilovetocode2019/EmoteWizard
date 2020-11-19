import discord
from discord.ext import commands

import json
import io
from PIL import Image, ImageDraw, ImageOps

class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="reply", description="Reply to a message", invoke_without_command=True)
    async def reply(self, ctx, message: discord.Message, *, reply):
        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        async with self.bot.session.get(str(message.author.avatar_url)) as resp:
            avatar = io.BytesIO(await resp.read())
            avatar = Image.open(avatar)

        mask = Image.new("L", (128, 128), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + (128, 128), fill=255)

        output = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
        output.putalpha(mask)

        avatar = io.BytesIO()
        output.save(avatar, "PNG", trancparency=(0, 0, 0))
        avatar.seek(0)

        if f"user_{message.author.id}" not in [emoji.name for emoji in self.bot.stickers_guild.emojis]:
            if len(self.bot.stickers_guild.emojis) == 50:
                sorted_emojis = sorted(self.bot.stickers_guild.emojis, key= lambda emoji: emoji.created_at)
                await sorted_emojis[0].delete()

            emoji = await self.bot.stickers_guild.create_custom_emoji(name=f"user_{message.author.id}", image=avatar.read())
        else:
            emoji = discord.utils.get(self.bot.stickers_guild.emojis, name=f"user_{message.author.id}")

        content = f"> {emoji} **{message.author.display_name}** \n> {message.content} \n> [Jump to message](<{message.jump_url}>) \n{discord.utils.escape_mentions(reply)}"

        if ctx.guild.me.guild_permissions.manage_messages and ctx.guild.me.guild_permissions.manage_webhooks and webhook and webhook["webhook_id"]:
            await ctx.message.delete()

            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            if webhook.channel_id != ctx.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

            await webhook.send(content=content, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url)
        else:
            await ctx.send(content=content)

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
