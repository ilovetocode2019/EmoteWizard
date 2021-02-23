import discord
from discord.ext import commands

import re

class MessageConverter(commands.Converter):
    async def convert(self, ctx, arg):
        # Attempt to convert the message normally
        try:
            message = await commands.MessageConverter().convert(ctx, arg)
            return message
        except commands.BadArgument:
            pass

        # Fetch history
        channel = ctx.args[-1] if isinstance(ctx.args[-1], discord.TextChannel) else ctx.channel
        history = await channel.history(limit=200, before=ctx.message).flatten()

        # Get message by content
        message = discord.utils.get(history, content=arg)
        if message:
            return message

        # Get message by user
        try:
            author = await commands.MemberConverter().convert(ctx, arg)
            message = discord.utils.get(history, author=author)
            if message:
                return message
        except commands.BadArgument:
            pass

        # Get message by offset
        try:
            int_arg = int(arg)
            limit = (int_arg * -1)
            if limit > 200:
                raise commands.BadArgument("Message offset cannot be larger than 200")
            elif limit < 1:
                raise commands.BadArgument("Message offest must be negitive")
            message = history[limit-1]
            return message
        except ValueError:
            pass
        except IndexError as exc:
            raise commands.BadArgument("Message offset is out of range") from exc

        raise commands.BadArgument(f"I couldn't find the message `{arg}`")

class WebhookConverter(commands.Converter):
    async def convert(self, ctx, arg):
        # Retrive a lit of existing webhooks
        webhooks = await ctx.guild.webhooks()

        # Attempt to get the webhook by name
        webhook = discord.utils.get(webhooks, name=arg)
        if webhook:
            return webhook

        webhook_id = None

        # Attempt to convert the argument into an ID
        try:
            webhook_id = int(arg)
        except ValueError:
            pass

        # Otherwise attempt to get the ID from the URL using regex
        matches = re.findall("https://(?:(?:ptb|canary)\.)?discord(?:app)?.com/api/webhooks/([0-9]+)/.+", arg)
        if matches:
            webhook_id = int(matches[0])

        # Attempt to get the webhook by ID
        webhook = discord.utils.get(webhooks, id=webhook_id)
        if webhook:
            return webhook

        raise commands.BadArgument(f"Couldn't find the webhook `{arg}`")

class EmojiConverter(commands.Converter):
    async def convert(self, ctx, arg):
        emoji = discord.utils.get(ctx.bot.emojis, name=arg)
        if not emoji:
            raise commands.errors.BadArgument(f"I couldn't find the emoji `{arg}`")
        return emoji
