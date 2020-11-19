import discord
from discord.ext import commands
from discord.ext import menus

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
        # Attempt to convert the argument into an ID
        try:
            arg = int(arg)
        # Otherwise attempt to get the ID from the URL using regex
        except:
            arg = re.findall("https://(?:(?:ptb|canary)\.)?discord(?:app)?.com/api/webhooks/([0-9]+)/.+", arg)
            if arg:
                arg = int(arg[0])

        if not type(arg) is int:
            raise commands.errors.BadArgument("That is not a webhook URL or ID")
        return arg

class GuildConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            int_arg = int(arg)
            guild = ctx.bot.get_guild(int_arg)
            if guild:
                return guild
        except ValueError:
            pass

        guild = discord.utils.get(ctx.bot.guilds, name=arg)
        if not guild:
            raise commands.BadArgument(f"Guild '{arg}' not found")
        return guild

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

def finder(text, collection, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
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

class Emojis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        context = await self.bot.get_context(message)
        if message.author.bot or not message.guild or self.bot.config.ignore or (context.valid and context.command.name == "edit"):
            return

        message_content, found = self.replace_emojis(message.content)
        # If no emojis were found, ignore
        if len(found) == 0:
            return

        webhook_config = await self.get_webhook_config(message.guild)

        # If a webhook config and the bot has permissions to delete messages, continue
        if message.guild.me.guild_permissions.manage_messages and webhook_config["webhook_id"]:
            # Fetch the webhook and if make an HTTP request to update the channel if needed
            webhook = await self.bot.fetch_webhook(webhook_config["webhook_id"])
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

    @commands.Cog.listener("on_reaction_add")
    async def on_reaction_add(self, reaction, user):
        if reaction.emoji != "\N{CROSS MARK}":
            return

        original = self.bot.reposted_messages.get(reaction.message.id)

        self.bot.reposted_messages.pop(reaction.message.id)
        await reaction.message.delete()

    def replace_emojis(self, content):
        # Look for 'emojis' in the message
        emojis = re.finditer("\;[^;]+\;", content)

        # Iter through the found emois name
        found = []
        for name in emojis:
            emoji = discord.utils.get(self.bot.emojis, name=name.group(0).replace(";", ""))
            if emoji:
                content = content.replace(name.group(0), str(emoji))
                found.append(str(emoji))

        return content, found

    async def get_webhook_config(self, guild):
        select_query = """SELECT *
                    FROM webhooks
                    WHERE webhooks.guild_id=$1;
                """
        webhook_config = await self.bot.db.fetchrow(select_query, guild.id)

        if not webhook_config:
            insert_query = """INSERT INTO webhooks (guild_id, webhook_id)
                              VALUES ($1, $2);"""
            await self.bot.db.execute(insert_query, guild.id, None)
            webhook_config = await self.bot.db.fetchrow(select_query, guild.id)

        return webhook_config

    @commands.command(name="delete", description="Delete a reposted message")
    async def delete(self, ctx, message: discord.Message):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        original = self.bot.reposted_messages.get(message.id)

        if not original:
            return await ctx.send(":x: This message is unable to be deleted", delete_after=5)
        if original.author.id != ctx.author.id:
            return await ctx.send(":x: You did not post this message", delete_after=5)

        self.bot.reposted_messages.pop(message.id)
        await message.delete()

    @commands.command(name="edit", description="Edit a reposted message")
    async def edit(self, ctx, message: discord.Message, *, content):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        config = await self.get_webhook_config(ctx.guild)
        original = self.bot.reposted_messages.get(message.id)

        if not original:
            return await ctx.send(":x: This message is unable to be edited", delete_after=5)
        if original.author.id != ctx.author.id:
            return await ctx.send(":x: You did not post this message", delete_after=5)

        webhook = await self.bot.fetch_webhook(message.webhook_id)

        message_content, found = self.replace_emojis(content)

        await self.bot.http.request(discord.http.Route("PATCH", f"/webhooks/{webhook.id}/{webhook.token}/messages/{message.id}"), json={"content": discord.utils.escape_markdown(message_content)})

    @commands.group(name="webhook", description="View the current webhook for the server", invoke_without_command=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook(self, ctx):
        webhook_config = await self.get_webhook_config(ctx.guild)

        if not webhook_config["webhook_id"]:
            return await ctx.send(":x: No webhook set")

        webhook = await self.bot.fetch_webhook(webhook_config["webhook_id"])
        await ctx.send(f"The webhook set is `{webhook.name}` ({webhook.id})")

    @webhook.command(name="set", description="Set the webhook")
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_set(self, ctx, webhook: WebhookConverter):
        try:
            webhook = await self.bot.fetch_webhook(webhook)
        except discord.NotFound:
            return await ctx.send(":x: That webhook does not exist")

        if webhook.guild_id != ctx.guild.id:
            return await ctx.send(":x: That webhook does not exist")

        query = """INSERT INTO webhooks (guild_id, webhook_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET webhook_id=$2;
                """
        await self.bot.db.execute(query, ctx.guild.id, webhook.id)
        await ctx.send(":white_check_mark: Webhook set")

    @webhook.command(name="create", description="Creates a webhook for the bot")
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_create(self, ctx):
        webhook = await ctx.channel.create_webhook(name="Stickers Hook")

        query = """INSERT INTO webhooks (guild_id, webhook_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET webhook_id=$2;
                """
        await self.bot.db.execute(query, ctx.guild.id, webhook.id)
        await ctx.send(":white_check_mark: Webhook ceated")

    @webhook.command(name="unbind", description="Unbund the webhook")
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_unbind(self, ctx):
        query = """DELETE FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        await self.bot.db.execute(query, ctx.guild.id)
        await ctx.send(":white_check_mark: Unbound webhook")

    @commands.command(name="react", descrition="React to a message with any emoji", usage="<emoji> <message>")
    async def react(self, ctx, emoji_name, message = None):
        # Attempt to delete the user's message
        try:
            await ctx.message.delete()
            deleted = True
        except:
            deleted = False

        # Get the emoji
        emoji = discord.utils.get(self.bot.emojis, name=emoji_name)
        if not emoji:
            return await ctx.send(f":x: Couldn't find an emoji named `{emoji_name}`", delete_after=5)

        # Convert message to an int
        if not message:
            message = -1
        try:
            message = int(message)
        except:
            return await ctx.send(f":x: `{message}` is not a integer", delete_after=5)

        # If the message is less than 0 it is a message index so we need to fetch that amount of history
        if message < 0:
            try:
                limit = message * -1
                if not deleted:
                    limit += 1
                history = await ctx.channel.history(limit=limit).flatten()
                message = history[limit-1]
            except (discord.HTTPException, IndexError):
                return await ctx.send(":x: Could not fetch message from history", delete_after=5)

        # Otherwise just fetch the message
        else:
            try:
                message = await ctx.channel.fetch_message(message)
            except discord.HTTPException:
                return await ctx.send(":x: Could not fetch message", delete_after=5)

        await message.add_reaction(emoji)

        # Wait for the use to add a reaction, then we can remove our reaction to make it look like the user used the emoji
        def check(event):
            return event.user_id == ctx.author.id and event.message_id == message.id and event.emoji.id == emoji.id
        await self.bot.wait_for("raw_reaction_add", check=check)
        await message.remove_reaction(emoji, self.bot.user)

    @commands.group(name="emoji", description="Fetch an emoji", aliases=["emote"], invoke_without_command=True)
    async def emoji(self, ctx, emoji: EmojiConverter):
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

    @emoji.command(name="server", description="List all emojis for a server", aliases=["guild"], usage="<server>")
    async def emoji_server(self, ctx, *, guild: GuildConverter):
        if ctx.author.id != self.bot.owner_id and ctx.author.id not in [member.id for member in guild.members]:
            return await ctx.send(":x: You are not in this server")
        if len(guild.emojis) == 0:
            return await ctx.send(":x: This server has no emojis")

        emojis = [(emoji.name, str(emoji)) for emoji in guild.emojis]

        pages = menus.MenuPages(source=EmojiPages(sorted(emojis, key=lambda x: x[0].lower())), clear_reactions_after=True)
        await pages.start(ctx)

def setup(bot):
    bot.add_cog(Emojis(bot))
