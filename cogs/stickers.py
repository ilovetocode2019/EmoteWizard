import discord
from discord import app_commands
from discord.ext import commands

import asyncpg
import os

from .utils import faked

class Stickers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="sticker", description="Use a sticker", fallback="get", invoke_without_command=True)
    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def sticker(self, ctx, name):
        query = """SELECT *
                   FROM stickers
                   WHERE stickers.name=$1;
                """
        sticker = await self.bot.db.fetchrow(query, name)
        if not sticker:
            return await ctx.send(":x: No sticker with that name")

        if ctx.interaction or isinstance(ctx.channel, discord.DMChannel) or not (ctx.me.guild_permissions.manage_messages and ctx.me.guild_permissions.manage_webhooks):
            return await ctx.send(file=discord.File(sticker["content_path"]))

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
            await ctx.send(file=discord.File(sticker["content_path"]))

    @sticker.command(name="create", description="Create a sticker", aliases=["add", "new"])
    async def sticker_create(self, ctx, name, attachment: discord.Attachment):
        if not attachment.content_type.startswith("image/"):
            return await ctx.send(":x: The sticker must only be an image (both static and animated allowed)")

        query = """SELECT COUNT(*)
                   FROM stickers
                   WHERE stickers.name = $1;
                """
        result = await self.bot.db.fetchrow(query, name)

        if result["count"] > 0:
            return await ctx.send(f":x: The name `{name}` is already in use")

        path = f"stickers/{ctx.message.id}_{attachment.filename}"
        await attachment.save(path)

        query = """INSERT INTO stickers (owner_id, name, content_path)
                    VALUES($1, $2, $3);
                """
        await self.bot.db.execute(query, ctx.author.id, name, path)

        await ctx.send(f":white_check_mark: Created the sticker `{name}`")

    @sticker.command(name="delete", description="Delete a sticker", aliases=["remove"])
    async def sticker_delete(self, ctx, name):
        query = """SELECT *
                   FROM stickers
                   WHERE stickers.owner_id = $1 AND stickers.name = $2;
                """
        result = await self.bot.db.fetchrow(query, ctx.author.id, name)

        if not result:
            return await ctx.send(f":x: You don't own any stickers by the name `{name}`")

        query = """DELETE FROM stickers
                   WHERE stickers.owner_id = $1 AND stickers.name = $2;
                """
        await self.bot.db.execute(query, ctx.author.id, name)

        os.remove(result["content_path"])
        await ctx.send(f":white_check_mark: Deleted the sticker `{name}`")

    @sticker.autocomplete("name")
    @sticker_delete.autocomplete("name")
    async def sticker_autocomplete(self, interaction, current):
        query = """SELECT *
                   FROM stickers
                   WHERE stickers.name % $1
                   ORDER BY similarity(stickers.name, $1) DESC
                   LIMIT 5;
                """
        stickers = await self.bot.db.fetch(query, current)

        return [
            app_commands.Choice(name=sticker["name"], value=sticker["name"])
            for sticker in stickers
        ]

async def setup(bot):
    await bot.add_cog(Stickers(bot))
