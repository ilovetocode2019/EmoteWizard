import discord
from discord import app_commands
from discord.ext import commands

def has_permissions(**perms):
    def inner(func):
        commands.has_permissions(**perms)(func)
        app_commands.default_permissions(**perms)(func)
        return func

    return inner
