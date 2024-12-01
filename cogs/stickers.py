import discord
from discord.ext import commands

import os

from .utils import faked

class Stickers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="sticker", description="Use a sticker", invoke_without_command=True)
    async def sticker(self, ctx, name):
        query = """SELECT *
                   FROM stickers
                   WHERE stickers.name=$1;
                """
        sticker = await self.bot.db.fetchrow(query, name)
        if not sticker:
            return await ctx.send(":x: No sticker with that name")

        if isinstance(ctx.channel, discord.DMChannel) or not (ctx.me.guild_permissions.manage_messages and ctx.me.guild_permissions.manage_webhooks):
            return await ctx.send(sticker["content_url"])

        config = await self.bot.get_webhook_config(ctx.guild)
        webhook = await config.webhook()

        if webhook:
            if webhook.channel != ctx.channel:
                await webhook.edit(channel=ctx.channel)

            replacement = await webhook.send(
                file=discord.File(sticker["content_path"]),
                username=ctx.author.display_name,
                avatar_url=ctx.author.display_avatar.url,
                wait=True
            )

            self.bot.faked_messages[replacement.id] = faked.FakedMessage(
                original=ctx.message,
                replacement=replacement,
                is_sticker=True
            )

            await ctx.message.delete()
        else:
            await ctx.send(file=discord.File(sticker["content_url"]))

    @sticker.command(name="create", description="Create a sticker", aliases=["add", "new"])
    async def sticker_create(self, ctx, name):
        if len(ctx.message.attachments) == 0:
            return await ctx.send(":x: You must attach the sticker to the message")

        query = """SELECT COUNT(*)
                   FROM stickers
                   WHERE stickers.name=$1;
                """
        count = await self.bot.db.fetchrow(query, name)
        if count and count["count"] != 0:
            return await ctx.send(":x: This name is already in use")

        attachment = ctx.message.attachments[0]
        path = f"stickers/{ctx.message.id}_{attachment.filename}"

        async with self.bot.session.get(attachment.url) as resp:
            with open(path, "wb") as file:
                file.write(await resp.read())

        query = """INSERT INTO stickers (owner_id, name, content_path)
                   VALUES($1, $2, $3);
                """
        await self.bot.db.execute(query, ctx.author.id, name, path)

        await ctx.send(f":white_check_mark: Created the sticker `{name}`")

    @sticker.command(name="delete", description="Delete a sticker", aliases=["remove"])
    async def sticker_delete(self, ctx, name):
        query = """SELECT FROM stickers
                   WHERE stickers.owner_id=$1 AND stickers.name=$2;
                """
        result = await self.bot.db.fetchrow(query, ctx.author.id, name)

        if not result:
            return await ctx.send(":x: You don't own any stickers by this name")

        query = """DELETE FROM stickers
                   WHERE stickers.owner_id=$1 AND stickers.name=$2;
                """
        await self.bot.db.fetchrow(query, ctx.author.id, name)

        os.remove(result["content_path"])

        await ctx.send(f":white_check_mark: Deleted the sticker `{name}`")

async def setup(bot):
    await bot.add_cog(Stickers(bot))
