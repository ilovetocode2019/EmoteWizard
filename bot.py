import discord
from discord.ext import commands

import logging
import aiohttp
import asyncpg
import os
import json

import config
from cogs.utils.context import Context

logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) %(levelname)s %(message)s",
    datefmt="%m/%d/%y - %H:%M:%S %Z",
)


def get_prefix(bot, message):

    prefixes = [config.default_prefix]

    # Get prefixes from prefixes.json if the message is in a guild
    if not isinstance(message.channel, discord.DMChannel) and message.guild:
        if str(message.guild.id) in bot._guild_prefixes.keys():
            prefixes = bot._guild_prefixes[str(message.guild.id)]

    return commands.when_mentioned_or(*prefixes)(bot, message)


extensions = ["cogs.meta", "cogs.emojis", "cogs.stickers", "cogs.embeds"]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.presences = False

        super().__init__(command_prefix=get_prefix, intents=intents)
        self.loop.create_task(self.load_extensions())
        self.loop.create_task(self.prepare_bot())

        self.config = config
        if not hasattr(config, "default_prefix"):
            config.default_prefix = "s."

        if not os.path.isfile("prefixes.json"):
            logging.info("prefixes.json not found, creating...")
            with open("prefixes.json", "w") as f:
                json.dump({}, f)

        with open("prefixes.json", "r") as f:
            self._guild_prefixes = json.load(f)

    async def get_context(self, message, *, cls=None):
        return await super().get_context(message, cls=cls or Context)

    def guild_prefix(self, guild):
        """Get the default prefix for a guild"""
        if not guild or str(guild.id) not in self._guild_prefixes:
            return self.config.default_prefix

        return self._guild_prefixes[str(guild.id)][0]

    def guild_prefixes(self, guild):
        """Get all the prefixes for a guild"""
        if not guild or str(guild.id) not in self._guild_prefixes:
            return [self.config.default_prefix]

        return self._guild_prefixes[str(guild.id)]

    async def load_extensions(self):
        self.load_extension("jishaku")
        self.get_command("jishaku").hidden = True

        for extension in extensions:
            self.load_extension(extension)

    async def prepare_bot(self):
        self.session = aiohttp.ClientSession()
        self.db = await asyncpg.create_pool(config.sql)

        query = """CREATE TABLE IF NOT EXISTS
                   webhooks (guild_id BIGINT, webhook_id BIGINT, PRIMARY KEY (guild_id));
                   """
        await self.db.execute(query)

        query = """CREATE TABLE IF NOT EXISTS
                   stickers (owner_id BIGINT, name TEXT, content_url TEXT);
                   """
        await self.db.execute(query)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name} - {self.user.id}")

    def run(self):
        super().run(config.token)


bot = Bot()
bot.run()
