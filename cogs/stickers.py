import discord
from discord.ext import commands

import io

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
            if webhook.channel_id != ctx.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

            files = [discord.File(BytesIO(await x.read()), filename=x.filename, spoiler=x.is_spoiler()) for x in ctx.message.attachments]
            await webhook.send(
                content=sticker["content_url"],
                files=files,
                username=ctx.author.display_name,
                avatar_url=ctx.author.avatar.url
            )
            await ctx.message.delete()
        else:
            await ctx.send(sticker["content_url"])

    @sticker.command(name="create", description="Create a sticker")
    async def sticker_create(self, ctx, name):
        if len(ctx.message.attachments) == 0:
            return await ctx.send(":x: You must attach the sticker to the message")

        attachment = ctx.message.attachments[0]
        async with self.bot.session.get(attachment.url) as resp:
            file = io.BytesIO(await resp.read())
        result = await self.bot.channel.send(file=discord.File(file, filename=attachment.filename))
        url = result.attachments[0].url

        query = """SELECT COUNT(*)
                   FROM stickers
                   WHERE stickers.name=$1;
                """
        count = await self.bot.db.fetchrow(query, name)
        if count and count["count"] != 0:
            return await ctx.send(":x: A sticker with this name already exists")

        query = """INSERT INTO stickers (owner_id, name, content_url)
                   VALUES($1, $2, $3);
                """
        await self.bot.db.execute(query, ctx.author.id, name, url)

        await ctx.send(":white_check_mark: Created your sticker")

    @sticker.command(name="delete", description="Delete a sticker")
    async def sticker_delete(self, ctx, name):
        query = """DELETE FROM stickers
                   WHERE stickers.owner_id=$1 AND stickers.name=$2;
                """
        result = await self.bot.db.execute(query, ctx.author.id, name)
        if result == "DELETE 0":
            return await ctx.send(":x: That is not a sticker or you do not own it")
        await ctx.send(":white_check_mark: Deleted your sticker")

async def setup(bot):
    await bot.add_cog(Stickers(bot))
