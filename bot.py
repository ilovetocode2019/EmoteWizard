import discord
from discord.ext import commands

import logging
import aiohttp
import asyncpg
import os
import json
import datetime

import config
from cogs.utils import context, cache

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


extensions = ["cogs.meta", "cogs.admin", "cogs.replies", "cogs.emojis", "cogs.stickers"]

class GuildConfig:
    @classmethod
    def from_record(cls, record, bot):
        self = cls()
        self.bot = bot

        self.guild_id = record["guild_id"]
        self.webhook_id = record["webhook_id"]

        return self

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    async def webhook(self):
        if not self.webhook_id:
            return None

        try:
            return await self.bot.fetch_webhook(self.webhook_id)
        except discord.HTTPException:
            return None

    async def set_webhook(self, webhook_id):
        self.webhook_id = webhook_id

        query = """INSERT INTO guild_config (guild_id, webhook_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id) DO UPDATE
                   SET webhook_id=$2;
                """
        await self.bot.db.execute(query, self.guild_id, self.webhook_id)

class EmoteWizard(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.presences = False
        super().__init__(command_prefix=get_prefix, intents=intents)
        self.loop.create_task(self.prepare_bot())

        self.startup_time = datetime.datetime.utcnow()
        self.reposted_messages = {}

        self.load_extension("jishaku")
        for extension in extensions:
            self.load_extension(extension)

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
        return await super().get_context(message, cls=cls or context.Context)

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

    @cache.cache()
    async def get_webhook_config(self, guild):
        query = """SELECT *
                   FROM guild_config
                   WHERE guild_config.guild_id=$1;
                """
        record = await self.db.fetchrow(query, guild.id)

        if not record:
            record =  {
                "guild_id": guild.id,
                "webhook_id": None
            }
        return GuildConfig.from_record(dict(record), self)

    async def prepare_bot(self):
        self.session = aiohttp.ClientSession()

        async def init(conn):
            await conn.set_type_codec(
                "jsonb",
                schema="pg_catalog",
                encoder=json.dumps,
                decoder=json.loads,
                format="text",
            )
        self.db = await asyncpg.create_pool(config.sql, init=init)

        query = """CREATE TABLE IF NOT EXISTS guild_config (
                       guild_id BIGINT PRIMARY KEY,
                       webhook_id BIGINT
                   );

                   CREATE TABLE IF NOT EXISTS stickers (
                       owner_id BIGINT,
                       name TEXT,
                       content_url TEXT
                   );

                   CREATE TABLE IF NOT EXISTS avatar_emojis (
                       user_id BIGINT PRIMARY KEY,
                       emoji_id BIGINT,
                       avatar_url TEXT,
                       last_used TIMESTAMP DEFAULT (now() at time zone 'utc')
                   );
                   """
        await self.db.execute(query)

        avatar_emojis = await self.db.fetch("SELECT * FROM avatar_emojis;")
        self.avatar_emojis = {emoji["user_id"]: dict(emoji) for emoji in avatar_emojis}

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name} - {self.user.id}")
        self.channel = self.get_channel(config.channel)
        self.guild = self.get_guild(config.guild)
        self.console = bot.get_channel(config.console)

    def run(self):
        super().run(config.token)

bot = EmoteWizard()
bot.run()
