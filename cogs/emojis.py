import discord
from discord.ext import commands
from discord.ext import menus

import asyncio
import re
import typing
from io import BytesIO

from .replies import Reply
from .utils.menus import Confirm
from .utils import converters

def finder(text, collection, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = ".*?".join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    def sort_key(tup):
        if key:
            return tup[0], tup[1], key(tup[2])
        return tup

    if lazy:
        return (z for _, _, z in sorted(suggestions, key=sort_key))
    else:
        return [z for _, _, z in sorted(suggestions, key=sort_key)]

class EmojiPages(menus.ListPageSource):
    def __init__(self, data):
        self.data = data
        super().__init__(data, per_page=10)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        em = discord.Embed(description="", color=discord.Color.blurple())
        for i, v in enumerate(entries, start=offset):
            em.description += f"\n{v[1]} {v[0]}"
        em.set_footer(text=f"{len(self.data)} emojis | Page {menu.current_page+1}/{int(len(self.data)/10)+1}")

        return em

class Emojis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        context = await self.bot.get_context(message)
        if (message.author.bot or not message.guild or self.bot.config.ignore) or context.valid:
            return

        message_content, found = self.replace_emojis(message.content)
        # If no emojis were found, ignore
        if len(found) == 0:
            return

        # If we don't have permissions just skip everything else and send it through the bot now
        if not (message.guild.me.guild_permissions.manage_messages and message.guild.me.guild_permissions.manage_webhooks):
            return await message.channel.send(" ".join(found))

        config = await self.bot.get_webhook_config(message.guild)
        webhook = await config.webhook()

        # If a webhook is configured, send it through the webhook
        if webhook:
            # make an HTTP request to update the channel if needed
            if webhook.channel_id != message.channel.id:
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}", webhook_id=webhook.id), json={"channel_id": message.channel.id})

            # Prepare the files, send the webhook, and delete the message
            files = [discord.File(BytesIO(await x.read()), filename=x.filename, spoiler=x.is_spoiler()) for x in message.attachments]
            reposted = await webhook.send(content=discord.utils.escape_mentions(message_content), files=files, username=message.author.display_name, avatar_url=message.author.avatar_url, wait=True)

            self.bot.reposted_messages[reposted.id] = message
            await message.delete()

        # Otherwise just send the found emojis through the bot account
        else:
            return await message.channel.send(" ".join(found))

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        original = self.bot.reposted_messages.get(reaction.message.id)

        if not original:
            return
        if original.author.id != user.id:
            return

        if reaction.emoji == "\N{CROSS MARK}" and reaction.message.guild.me.guild_permissions.manage_messages:
            self.bot.reposted_messages.pop(reaction.message.id)
            await reaction.message.delete()

        elif (reaction.emoji == "\N{MEMO}" or reaction.emoji == "\N{PENCIL}\N{VARIATION SELECTOR-16}") and reaction.message.guild.me.guild_permissions.manage_webhooks:
            await reaction.remove(user)

            await user.send("What would you like to edit your message to?")
            message = await self.bot.wait_for("message", check=lambda message: message.channel.id == user.dm_channel.id and message.author.id == user.id)
            content = message.content

            webhook = await self.bot.fetch_webhook(reaction.message.webhook_id)

            if isinstance(original, Reply):
                original.reply = content
                allowed_mentions = {"parse": ["users"] if original.mention else []}
                data = {"content": str(original), "allowed_mentions": allowed_mentions}
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}/{webhook.token}/messages/{reaction.message.id}"), json=data)
            elif isinstance(original, discord.Message):
                message_content, found = self.replace_emojis(content)
                data = {"content": discord.utils.escape_markdown(message_content)}
                await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}/{webhook.token}/messages/{reaction.message.id}"), json=data)

            await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    def replace_emojis(self, content):
        replaced = content

        # Look for 'emojis' in the message
        emojis = re.finditer("\;[^;]+\;", content)
        possible_emojis = re.finditer("\:\w+:", content)

        # Iter through the found emois name
        found = []

        # Replace emojis using ;emoji;
        for name in emojis:
            emoji = discord.utils.get(self.bot.emojis, name=name.group(0).replace(";", ""))
            if emoji and str(emoji) not in found:
                replaced = replaced.replace(name.group(0), str(emoji))
                found.append(str(emoji))

        # Replace emojis using :emoji:
        for name in possible_emojis:
            emoji = discord.utils.get(self.bot.emojis, name=name.group(0).replace(":", ""))
            span = name.span(0)
            full_emoji = re.search(".*<a?", content[:span[0]]) and re.search("\d+>.*", content[span[1]+1:])
            if emoji and str(emoji) not in found and not full_emoji:
                replaced = replaced.replace(name.group(0), str(emoji))
                found.append(str(emoji))

        return replaced, found

    @commands.command(name="edit", description="Edit a reposted message")
    @commands.bot_has_permissions(manage_webhooks=True)
    async def edit(self, ctx, message: discord.Message, *, content):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        original = self.bot.reposted_messages.get(message.id)
        webhook = await self.bot.fetch_webhook(message.webhook_id)

        if not original or not webhook:
            return await ctx.send(":x: This message is unable to be edited", delete_after=5)
        if original.author.id != ctx.author.id:
            return await ctx.send(":x: You did not post this message", delete_after=5)

        if isinstance(original, Reply):
            original.reply = content
            allowed_mentions = {"parse": ["users"] if original.mention else []}
            data = {"content": str(original), "allowed_mentions": allowed_mentions}
            await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}/{webhook.token}/messages/{message.id}"), json=data)
        elif isinstance(original, discord.Message):
            message_content, found = self.replace_emojis(content)
            data = {"content": discord.utils.escape_markdown(message_content)}
            await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}/{webhook.token}/messages/{message.id}"), json=data)
        else:
            await ctx.send(":x: This message is unable to be edited", delete_after=5)

    @commands.command(name="delete", description="Delete a reposted message")
    @commands.bot_has_permissions(manage_messages=True)
    async def delete(self, ctx, message: discord.Message):
        await ctx.message.delete()

        original = self.bot.reposted_messages.get(message.id)

        if not original:
            return await ctx.send(":x: This message is unable to be deleted", delete_after=5)
        if original.author.id != ctx.author.id:
            return await ctx.send(":x: You did not post this message", delete_after=5)

        self.bot.reposted_messages.pop(message.id)
        await message.delete()

    @commands.group(name="webhook", description="View the current webhook for the server", invoke_without_command=True)
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        webhook = await config.webhook()

        if not webhook:
            return await ctx.send("No webhook is set")

        await ctx.send(f"The webhook set is `{webhook.name}` ({webhook.id})")

    @webhook.command(name="set", description="Set the webhook")
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_set(self, ctx, *, webhook: converters.WebhookConverter):
        config = await self.bot.get_webhook_config(ctx.guild)
        if await config.webhook() and not await Confirm("A webhook is already set. Would you like to override it?").prompt(ctx):
            return await ctx.send("Aborting")

        await config.set_webhook(webhook.id)
        await ctx.send(f":white_check_mark: Webhook set to `{webhook.name}` ({webhook.id})")

    @webhook.command(name="create", description="Creates a webhook for the bot")
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_create(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        if await config.webhook() and not await Confirm("A webhook is already set. Would you like to override it?").prompt(ctx):
            return await ctx.send("Aborting")

        webhook = await ctx.channel.create_webhook(name="Stickers Hook")
        await config.set_webhook(webhook.id)
        await ctx.send(f":white_check_mark: Webhook set to `{webhook.name}` ({webhook.id})")

    @webhook.command(name="unbind", description="Unbind the webhook")
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_unbind(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        if  await config.webhook() and not await Confirm("Are you sure you want to unbind the webhook?").prompt(ctx):
            return await ctx.send("Aborting")

        await config.set_webhook(None)
        await ctx.send(":white_check_mark: Unbound webhook")

    @commands.command(name="react", descrition="React to a message with any emoji", usage="<emoji> <message>")
    async def react(self, ctx, emoji: converters.EmojiConverter, channel: typing.Optional[discord.TextChannel], *, message: converters.MessageConverter = None):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        # If no message is specified, default to the last message
        channel = channel if isinstance(channel, discord.TextChannel) else ctx.channel
        if not message:
            messages = await channel.history(limit=1, before=ctx.message).flatten()
            if not messages:
                return await ctx.send(":x: I couldn't find a message to react to", delete_after=5)
            message = messages[0]

        # Don't let users get around permissions
        if not channel.permissions_for(ctx.author).add_reactions:
            return await ctx.send(f":x: You don't have permissions to add reactions in {channel.mention}", delete_after=5)

        # Don't add extra reactions
        if discord.utils.find(lambda reaction: getattr(reaction.emoji, "id", None) == emoji.id, message.reactions):
            return await ctx.send(":x: That reaction has already been added")
 
        try:
            await message.add_reaction(emoji)
        except discord.Forbidden as exc:
            if exc.code == 30010:
                return await ctx.send(":x: The maximum number of reactions has been reached", delete_after=5)
            elif exc.code == 50013:
                return await ctx.send(f":x: I don't have permissions to add reactions in {channel.mention}", delete_after=5)
            else:
                return await ctx.send(f":x: I couldn't add that reaction for an unknown reason")

        def check(event):
            return event.user_id == ctx.author.id and event.message_id == message.id and event.emoji.id == emoji.id
        try:
            await self.bot.wait_for("raw_reaction_add", check=check, timeout=30)
        except asyncio.TimeoutError:
            pass
        finally:
            await message.remove_reaction(emoji, self.bot.user)

    @commands.group(name="emoji", description="Fetch an emoji", aliases=["emote"], invoke_without_command=True)
    async def emoji(self, ctx, emoji: converters.EmojiConverter):
        await ctx.send(emoji)

    @emoji.command(name="search", description="Search for emojis by name", aliases=["find"])
    async def emoji_search(self, ctx, search):
        results = finder(search, [(emoji.name, str(emoji)) for emoji in self.bot.emojis], key=lambda t: t[0], lazy=False)

        if len(results) == 0:
            return await ctx.send(":x: No results found")

        pages = menus.MenuPages(source=EmojiPages(results), clear_reactions_after=True)
        await pages.start(ctx)

    @emoji.command(name="list", description="List all emojis you can see")
    async def emoji_list(self, ctx):
        emojis = [(emoji.name, str(emoji)) for emoji in self.bot.emojis if ctx.author.id in [member.id for member in emoji.guild.members]]

        pages = menus.MenuPages(source=EmojiPages(sorted(emojis, key=lambda x: x[0].lower())), clear_reactions_after=True)
        await pages.start(ctx)

def setup(bot):
    bot.add_cog(Emojis(bot))
