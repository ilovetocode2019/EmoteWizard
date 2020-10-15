import discord
from discord.ext import commands

import traceback
import sys
import json
import asyncio

from .utils import checks


class HelpCommand(commands.MinimalHelpCommand):
    def get_command_signature(self, command):
        return "{0.clean_prefix}{1.qualified_name} {1.signature}".format(self, command)


class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.Cog.listener("on_command_error")
    async def on_command_error(self, ctx, error):
        print("Ignoring exception in command {}:".format(ctx.command), file=sys.stderr)
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr
        )

        if isinstance(error, discord.ext.commands.errors.BotMissingPermissions):
            perms_text = "\n".join(
                [
                    f"- {perm.replace('_', ' ').capitalize()}"
                    for perm in error.missing_perms
                ]
            )
            return await ctx.send(f":x: Missing Permissions:\n {perms_text}")
        elif isinstance(error, discord.ext.commands.errors.BadArgument):
            return await ctx.send(f":x: {error}")
        elif isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
            return await ctx.send(f":x: {error}")
        elif isinstance(error, discord.ext.commands.errors.CommandNotFound):
            return
        elif isinstance(error, discord.ext.commands.errors.CheckFailure):
            return

        await ctx.send(f"```py\n{error}\n```")

    @commands.command(name="invite", description="Get an invite link")
    async def invite(self, ctx):
        perms = discord.Permissions.none()
        perms.use_external_emojis = True
        perms.manage_webhooks = True
        perms.manage_messages = True
        invite = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        await ctx.send(f"<{invite}>")

    @commands.group(
        description="View your prefixes",
        invoke_without_command=True,
        aliases=["prefixes"],
    )
    @commands.guild_only()
    async def prefix(self, ctx):
        prefixes = [self.bot.user.mention]
        prefixes.extend(self.bot.guild_prefixes(ctx.guild))

        em = discord.Embed(
            name="Prefixes",
            description="\n".join(prefixes),
            color=discord.Color.blurple(),
        )

        await ctx.send(embed=em)

    def update_prefixes(self, guild, prefixes):
        """Update the prefixes for a guild"""
        if not prefixes:
            self.bot._guild_prefixes.pop(str(guild.id))

        else:
            self.bot._guild_prefixes[str(guild.id)] = prefixes

        with open("prefixes.json", "w") as f:
            json.dump(
                self.bot._guild_prefixes,
                f,
                sort_keys=True,
                indent=2,
            )

    @prefix.command(name="add", description="Add a prefix")
    @commands.guild_only()
    @checks.has_permissions(manage_guild=True)
    async def _add_prefix(self, ctx, prefix):
        prefixes = self.bot.guild_prefixes(ctx.guild)

        if prefix in prefixes:
            return await ctx.send("You already have that prefix registered.")

        prefixes.append(prefix)
        self.update_prefixes(ctx.guild, prefixes)

        await ctx.send(f"Added prefix  `{prefix}`")

    @prefix.command(name="remove", description="Remove a prefix")
    @commands.guild_only()
    @checks.has_permissions(manage_guild=True)
    async def _remove_prefix(self, ctx, prefix):
        prefixes = self.bot.guild_prefixes(ctx.guild)

        bot_id = self.bot.user.id
        if prefix in [f"<@{bot_id}", f"<@!{bot_id}>"]:
            return await ctx.send("You cannot remove that prefix.")

        if prefix not in prefixes:
            return await ctx.send(
                "You don't have that prefix registered."
            )

        prefixes.remove(prefix)
        self.update_prefixes(ctx.guild, prefixes)

        await ctx.send(f"Removed prefix `{prefix}`")

    @prefix.command(name="default", description="Set the default prefix")
    @commands.guild_only()
    @checks.has_permissions(manage_guild=True)
    async def _default_prefix(self, ctx, prefix):
        prefixes = self.bot.guild_prefixes(ctx.guild)

        if prefix in prefixes:
            prefixes.remove(prefix)

        prefixes.insert(0, prefix)
        self.update_prefixes(ctx.guild, prefixes)

        await ctx.send(f"Set default prefix to `{prefix}`")

    @prefix.command(name="reset", description="Reset the prefixes to default")
    @commands.guild_only()
    @checks.has_permissions(manage_guild=True)
    async def _reset_prefix(self, ctx):
        prefixes = self.bot.guild_prefixes(ctx.guild)

        if prefixes == [self.bot.config.default_prefix]:
            return await ctx.send("This server is already using the default prefixes.")

        result = await ctx.confirm("Are you sure you want to reset this server's prefixes?")

        if not result:
            return await ctx.send("Aborted.")

        self.update_prefixes(ctx.guild, None)

        await ctx.send("Reset prefixes")


def setup(bot):
    bot.add_cog(Meta(bot))
