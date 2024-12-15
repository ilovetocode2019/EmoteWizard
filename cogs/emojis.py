import discord
from discord.ext import commands
from discord.ext import menus

import asyncio
import re
import typing
from io import BytesIO

from .utils.menus import Confirm
from .utils import checks, converters, faked

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

        if message.author.bot or self.bot.config.ignore or context.valid:
            return

        replaced_content, found = self.bot.replace_emojis(message.content)

        if len(found) == 0:
            return

        # If we don't have permissions just skip everything else and send it through the bot now
        if isinstance(message.channel, discord.DMChannel) or not (message.guild.me.guild_permissions.manage_messages and message.guild.me.guild_permissions.manage_webhooks):
            return await message.channel.send(" ".join(found))

        config = await self.bot.get_webhook_config(message.guild)
        webhook = await config.webhook()

        # If a webhook is configured, send it through the webhook
        if webhook:
            if webhook.channel != message.channel:
                await webhook.edit(channel=message.channel)

            files = [
                discord.File(
                    BytesIO(await x.read()),
                    filename=x.filename,
                    spoiler=x.is_spoiler()
                )
            for x in message.attachments]

            replacement = await webhook.send(
                content=discord.utils.escape_mentions(replaced_content),
                files=files,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                wait=True
            )

            self.bot.faked_messages[replacement.id] = faked.FakedMessage(
                original=message,
                replacement=replacement
            )

            await message.delete()

        # Otherwise just send the found emojis through the bot account
        else:
            return await message.channel.send(" ".join(found))

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        faked = self.bot.faked_messages.get(reaction.message.id)

        if not faked or faked.original.author != user:
            return

        if reaction.emoji == "\N{CROSS MARK}" and reaction.message.guild.me.guild_permissions.manage_messages:
            await faked.replacement.delete()
            self.bot.faked_messages.pop(reaction.message.id)

        elif (reaction.emoji == "\N{MEMO}" or reaction.emoji == "\N{PENCIL}\N{VARIATION SELECTOR-16}") and reaction.message.guild.me.guild_permissions.manage_webhooks:
            await reaction.remove(user)

            await user.send("What would you like to edit your message to?")
            message = await self.bot.wait_for("message", check=lambda message: message.channel == user.dm_channel and message.author == user)
            content = message.content

            if faked.reply:
                await faked.replacement.edit(
                    content=faked.reply.format_with(content),
                    allowed_mentions=faked.reply.allowed_mentions
                )
            elif not faked.is_sticker:
                formatted_content, _ = self.bot.replace_emojis(content)
                await faked.replacement.edit(content=formatted_content)

            await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

    @commands.hybrid_command(name="edit", description="Edit a reposted message")
    @commands.guild_only()
    async def edit(self, ctx, message: discord.Message, *, content):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        faked = self.bot.faked_messages.get(message.id)

        if not faked:
            return await ctx.send(":x: This message cannot be edited", delete_after=5)
        elif faked.original.author != ctx.author:
            return await ctx.send(":x: You are not the author of this message", delete_after=5)

        if faked.reply:
            await faked.replacement.edit(
                content=faked.reply.format_with(content),
                allowed_mentions=faked.reply.allowed_mentions
            )
        elif faked.is_sticker:
            return await ctx.send(":x: Stickers cannot be edited", delete_after=5)
        else:
            formatted_content, _ = self.bot.replace_emojis(content)
            await faked.replacement.edit(content=formatted_content)

    @commands.hybrid_command(name="delete", description="Delete a reposted message")
    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    async def delete(self, ctx, message: discord.Message):
        await ctx.message.delete()

        faked = self.bot.faked_messages.get(message.id)

        if not faked:
            return await ctx.send(":x: This message cannot be deleted", delete_after=5)
        if faked.original.author != ctx.author:
            return await ctx.send(":x: You are not the author of this message", delete_after=5)

        await faked.replacement.delete()
        self.bot.faked_messages.pop(message.id)

    @commands.hybrid_group(name="webhook", description="View the current webhook for the server", invoke_without_command=True, fallback="show")
    @commands.guild_only()
    @checks.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        webhook = await config.webhook()

        if not webhook:
            return await ctx.send("No webhook is set")

        await ctx.send(f"The webhook set is `{webhook.name}` ({webhook.id})")

    @webhook.command(name="set", description="Set the webhook")
    @commands.guild_only()
    @checks.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_set(self, ctx, *, webhook: converters.WebhookConverter):
        config = await self.bot.get_webhook_config(ctx.guild)
        if await config.webhook() and not await Confirm("A webhook is already set. Would you like to override it?").prompt(ctx):
            return await ctx.send("Aborting")

        await config.set_webhook(webhook)
        await ctx.send(f":white_check_mark: Webhook set to `{webhook.name}` ({webhook.id})")

    @webhook.command(name="create", description="Creates a webhook for the bot")
    @commands.guild_only()
    @checks.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_create(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        if await config.webhook() and not await Confirm("A webhook is already set. Would you like to override it?").prompt(ctx):
            return await ctx.send("Aborting")

        try:
            webhook = await ctx.channel.create_webhook(name="Emote Hook")
        except discord.HTTPException as exc:
            if exc.code == 30007:
                return await ctx.send(f":x: The maximum number of webhooks has been reached")
            else:
                return await ctx.send(f":x: I couldn't create a webhook for an unknown reason (error code {exc.code})")

        await config.set_webhook(webhook)
        await ctx.send(f":white_check_mark: Webhook set to `{webhook.name}` ({webhook.id})")

    @webhook.command(name="unbind", description="Unbind the webhook")
    @commands.guild_only()
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_unbind(self, ctx):
        config = await self.bot.get_webhook_config(ctx.guild)
        if  await config.webhook() and not await Confirm("Are you sure you want to unbind the webhook?").prompt(ctx):
            return await ctx.send("Aborting")

        await config.set_webhook(None)
        await ctx.send(":white_check_mark: Unbound webhook")

    @commands.hybrid_command(name="react", descrition="React to a message with any emoji")
    @commands.guild_only()
    async def react(self, ctx, emoji: converters.CustomEmojiConverter, message: converters.MessageConverter):
        if not ctx.interaction and ctx.channel.permissions_for(guild.me).manage_messages:
            await ctx.message.delete()

        if emoji in [reaction.emoji for reaction in message.reactions if reaction.emoji]:
            return await ctx.send(":x: That reaction has already been added", delete_after=5, ephemeral=True)
        elif len(message.reactions) > 20:
            return await ctx.send(":x: There are already too many reactions on this message", delete_after=5, ephemeral=True)
        elif not message.channel.permissions_for(guild.me).add_reactions:
            return await ctx.send(":x: I am not allowed to this message", delete_after=5, ephemeral=True)
        elif not message.channel.permissions_for(ctx.author).add_reactions:
            return await ctx.send(":x: You aren't allowed to add reactions to this message", delete_after=5, ephemeral=True)

        await message.add_reaction(emoji)

        try:
            await self.bot.wait_for(
                "raw_reaction_add",
                check=lambda event: event.user_id == ctx.author.id and event.message_id == message.id and event.emoji == emoji,
                timeout=30
            )
        except asyncio.TimeoutError:
            pass
        finally:
            await message.remove_reaction(emoji, self.bot.user)

    @commands.hybrid_group(
        name="emoji",
        description="Show a specific emoji",
        fallback="show",
        invoke_without_command=True
    )
    async def emoji(self, ctx, emoji: discord.Emoji):
        await ctx.send(emoji)

    @emoji.command(name="search", description="Search for emojis by name", aliases=["find"])
    async def emoji_search(self, ctx, search):
        results = finder(
            search,
            [(emoji.name, str(emoji)) for emoji in self.bot.emojis],
            key=lambda t: t[0],
            lazy=False
        )

        if len(results) == 0:
            return await ctx.send(":x: No results found")

        pages = menus.MenuPages(source=EmojiPages(results), clear_reactions_after=True)
        await pages.start(ctx)

async def setup(bot):
    await bot.add_cog(Emojis(bot))
