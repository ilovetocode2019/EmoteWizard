import discord
from discord.ext import commands


def has_permissions(**perms):
    async def predicate(ctx):
        try:
            await commands.has_permissions(**perms).predicate(ctx)
            return True
        except commands.MissingPermissions:
            if ctx.author.id == ctx.bot.owner_id:
                return True
            else:
                raise

    return commands.check(predicate)
