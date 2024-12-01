import discord
from discord.ext import commands

import traceback
import sys
import json
import asyncio
import datetime
import humanize

from .utils import checks, formats, menus

class Prefix(commands.Converter):
    async def convert(self, ctx, prefix):
        if discord.utils.escape_mentions(prefix) != prefix:
            raise commands.BadArgument("Prefix can't include a mention")
        return prefix

class HelpCommand(commands.MinimalHelpCommand):
    def get_command_signature(self, command):
        return "{0.clean_prefix}{1.qualified_name} {1.signature}".format(self.context, command)

class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if isinstance(error, commands.PrivateMessageOnly):
            await ctx.send("This command can only be used in DMs")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in DMs")
        elif isinstance(error, commands.errors.BotMissingPermissions):
            perms_text = "\n".join([f"- {perm.replace('_', ' ').capitalize()}" for perm in error.missing_perms])
            await ctx.send(f":x: I am missing some permissions:\n {perms_text}") 
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send(f":x: You are missing a required argument: `{error.param.name}`")
        elif isinstance(error, commands.UserInputError):
            await ctx.send(f":x: {error}")
        elif isinstance(error, commands.ArgumentParsingError):
            await ctx.send(f":x: {error}")
        elif isinstance(error, commands.errors.CommandOnCooldown):
            await ctx.send(f"You are on cooldown. Try again in {formats.plural(int(error.retry_after)):second}.")
        elif isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send(f":x: {error}")

        if isinstance(error, commands.CommandInvokeError):
            em = discord.Embed(title=":warning: Error", description=f"An unexpected error has occured: \n```py\n{error}```", color=discord.Color.gold())
            await ctx.send(embed=em)

            em = discord.Embed(title=":warning: Error", description="", color=discord.Color.gold())
            em.description += f"\nCommand: `{ctx.command}`"
            em.description += f"\nLink: [Jump]({ctx.message.jump_url})"
            em.description += f"\n\n```py\n{error}```\n"

            if self.bot.console:
                await self.bot.console.send(embed=em)

    @commands.command(name="invite", description="Get an invite link")
    async def invite(self, ctx):
        perms = discord.Permissions.none()
        perms.use_external_emojis = True
        perms.manage_webhooks = True
        perms.manage_messages = True
        invite = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        await ctx.send(f"<{invite}>")

    @commands.command(name="ping", description="Check my latency")
    async def ping(self, ctx):
        await ctx.send(f"My latency is {int(self.bot.latency*1000)}ms")

    @commands.command(name="uptime", description="Check my uptime")
    async def uptime(self, ctx):
        delta = datetime.datetime.utcnow()-self.bot.uptime
        await ctx.send(f"I started up {humanize.naturaldelta(delta)} ago")

    @commands.group(name="prefix", description="Manage custom prefixes", invoke_without_command=True)
    async def prefix(self, ctx):
        await ctx.send_help(ctx.command)

    @prefix.command(name="add", description="Add a prefix")
    @commands.has_permissions(manage_guild=True)
    async def prefix_add(self, ctx, *, prefix: Prefix):
        prefixes = self.bot.get_guild_prefixes(ctx.guild)
        if prefix in prefixes:
            return await ctx.send(":x: That prefix is already added")

        if len(prefixes) > 10:
            return await ctx.send(":x: You cannot have more than 10 custom prefixes")

        prefixes.append(prefix)
        await self.bot.prefixes.add(ctx.guild.id, prefixes)

        await ctx.send(f":white_check_mark: Added the prefix `{prefix}`")

    @prefix.command(name="remove", description="Remove a prefix")
    @commands.has_permissions(manage_guild=True)
    async def prefix_remove(self, ctx, *, prefix: Prefix):
        prefixes = self.bot.get_guild_prefixes(ctx.guild)
        if prefix not in prefixes:
            return await ctx.send(":x: That prefix is not added")

        prefixes.remove(prefix)
        await self.bot.prefixes.add(ctx.guild.id, prefixes)

        await ctx.send(f":white_check_mark: Removed the prefix `{prefix}`")

    @prefix.command(name="default", description="Set a prefix as the first prefix")
    @commands.has_permissions(manage_guild=True)
    async def prefix_default(self, ctx, *, prefix: Prefix):
        prefixes = self.bot.get_guild_prefixes(ctx.guild)
        if prefix in prefixes:
            prefixes.remove(prefix)

        if len(prefixes) >= 10:
            return await ctx.send(":x: You cannot have more than 10 prefixes")

        prefixes = [prefix] + prefixes
        await self.bot.prefixes.add(ctx.guild.id, prefixes)

        await ctx.send(f":white_check_mark: Set `{prefix}` as the default prefix")

    @prefix.command(name="clear", description="Clear all the prefixes in this server", aliases=["reset"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_clear(self, ctx):
        result = await menus.Confirm("Are you sure you want to clear all your prefixes?").prompt(ctx)
        if not result:
            return await ctx.send("Aborting")

        await self.bot.prefixes.add(ctx.guild.id, [])
        await ctx.send(f":white_check_mark: Removed all prefixes")

    @prefix.command(name="list", description="View the prefixes in this server")
    async def prefix_list(self, ctx):
        prefixes = await self.bot.get_prefix(ctx.message)
        prefixes.pop(0)

        em = discord.Embed(title="Prefixes", description="\n".join(prefixes), color=0x96c8da)
        em.set_footer(text=f"{formats.plural(len(prefixes), end='es'):prefix}")
        await ctx.send(embed=em)

    @commands.command(name="prefixes", description="View the prefixes in this server")
    async def prefixes(self, ctx):
        await ctx.invoke(self.prefix_list)

    @commands.command(name="ignore", description="Disable/enable emoji replacing")
    @commands.is_owner()
    async def ignore(self, ctx):
        if self.bot.config.ignore:
            self.bot.config.ignore = False
            await ctx.send(":white_check_mark: Enabled emoji replacing")
        else:
            self.bot.config.ignore = True
            await ctx.send(":white_check_mark: Disabled emoji replacing")

async def setup(bot):
    await bot.add_cog(Meta(bot))
