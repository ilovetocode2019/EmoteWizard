import discord
from discord.ext import commands

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

        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        if ctx.guild.me.guild_permissions.manage_messages and webhook and webhook["webhook_id"]:
            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            if webhook.channel_id != ctx.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": ctx.channel.id})

            files = [discord.File(BytesIO(await x.read()), filename=x.filename, spoiler=x.is_spoiler()) for x in ctx.message.attachments]
            await webhook.send(content=sticker["content_url"], files=files, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url)
            await ctx.message.delete()
        else:
            await ctx.send(sticker["content_url"])

    @sticker.command(name="create", description="Create a sticker")
    async def sticker_create(self, ctx, name):
        if len(ctx.message.attachments) == 0:
            return await ctx.send(":x: You must attach the sticker to the message")
        url = ctx.message.attachments[0].url

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

def setup(bot):
    bot.add_cog(Stickers(bot))
