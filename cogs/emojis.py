import discord
from discord.ext import commands

import re
from io import BytesIO

class EmojiConverter(commands.Converter):
    async def convert(self, ctx, arg):
        emoji = discord.utils.get(ctx.bot.emojis, name=arg)
        if not emoji:
            raise commands.errors.BadArgument(f"`{arg}` is not an emoji")
        return emoji

class WebhookConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            arg = int(arg)
        except:
            arg = re.findall("https://(?:(?:ptb|canary)\.)?discord(?:app)?.com/api/webhooks/([0-9]+)/.+", arg)
            if arg:
                arg = int(arg[0])

        if not arg:
            raise commands.errors.BadArgument("That is not a webhook URL or ID")
        return arg

class Emojis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        emojis = re.finditer("\;[^;]+\;", message.content)
        message_content = message.content

        found = []
        for name in emojis:
            emoji = discord.utils.get(self.bot.emojis, name=name.group(0).replace(";", ""))
            if emoji:
                message_content = message_content.replace(name.group(0), str(emoji))
                found.append(str(emoji))
        if len(found) == 0:
            return

        webhook_config = await self.get_webhook_config(message.guild)
        if message.guild.me.guild_permissions.manage_messages and webhook_config["webhook_id"]:
            webhook = await self.bot.fetch_webhook(webhook_config["webhook_id"])
            if webhook.channel_id != message.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": message.channel.id})

            files = [discord.File(BytesIO(await x.read()), filename=x.filename, spoiler=x.is_spoiler()) for x in message.attachments]
            await webhook.send(content=discord.utils.escape_mentions(message_content), files=files, username=message.author.display_name, avatar_url=message.author.avatar_url)
            await message.delete()
        else:
            return await message.channel.send(" ".join(found))

    async def get_webhook_config(self, guild):
        select_query = """SELECT *
                    FROM webhooks
                    WHERE webhooks.guild_id=$1;
                """
        webhook_config = await self.bot.db.fetchrow(select_query, guild.id)

        if not webhook_config:
            insert_query = """INSERT INTO webhooks(guild_id, webhook_id)
                              VALUES ($1, $2);"""
            await self.bot.db.execute(insert_query, guild.id, None)
            webhook_config = await self.bot.db.fetchrow(select_query, guild.id)

        return webhook_config

    async def cog_before_invoke(self, ctx):
        ctx.webhook_config = await self.get_webhook_config(ctx.guild)

    @commands.group(name="webhook", description="View the current webhook for the server", invoke_without_command=True)
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook(self, ctx):
        if not ctx.webhook_config["webhook_id"]:
            return await ctx.send(":x: No webhook set")

        webhook = await self.bot.fetch_webhook(ctx.webhook_config["webhook_id"])
        await ctx.send(f"The webhook set is `{webhook.name}` ({webhook.id})")

    @webhook.command(name="set", description="Set the webhook")
    async def webhook_set(self, ctx, webhook: WebhookConverter):
        try:
            webhook = await self.bot.fetch_webhook(webhook)
        except discord.NotFound:
            return await ctx.send(":x: That webhook does not exist")

        if webhook.guild_id != ctx.guild.id:
            return await ctx.send(":x: That webhook does not exist")
        webhook_id = webhook.id

        query = """UPDATE webhooks
                   SET webhook_id=$1
                   WHERE webhooks.guild_id=$2;
                """
        await self.bot.db.execute(query, webhook_id, webhook.guild.id)
        await ctx.send(":white_check_mark: Webhook set")

    @webhook.command(name="create", description="Creates a webhook for the bot")
    async def webhook_create(self, ctx):
        webhook = await ctx.channel.create_webhook(name="Nitro Hook")

        query = """UPDATE webhooks
                   SET webhook_id=$1
                   WHERE webhooks.guild_id=$2;
                """
        await self.bot.db.execute(query, webhook.id, ctx.guild.id)
        await ctx.send(":white_check_mark: Webhook ceated")

    @webhook.command(name="unbind", description="Unbund the webhook")
    async def webhook_unbind(self, ctx):
        query = """UPDATE webhooks
                   SET webhook_id=$1
                   WHERE webhooks.guild_id=$2;
                """
        await self.bot.db.execute(query, None, ctx.guild.id)
        await ctx.send(":white_check_mark: Unbound webhook")

    @commands.command(name="react", descrition="React to a message with any emoji")
    async def react(self, ctx, emoji: EmojiConverter, message: int = -1):
        try:
            await ctx.message.delete()
            deleted = True
        except:
            deleted = False

        if message < 0:
            limit = message * -1
            if not deleted:
                limit += 1
            history = await ctx.channel.history(limit=limit).flatten()
            message = history[limit-1]
        else:
            message = await ctx.channel.fetch_message(message)
        await message.add_reaction(emoji)

        def check(event):
            return event.user_id == ctx.author.id and event.message_id == message.id and event.emoji.id == emoji.id
        await self.bot.wait_for("raw_reaction_add", check=check)
        await message.remove_reaction(emoji, self.bot.user)

def setup(bot):
    bot.add_cog(Emojis(bot))
