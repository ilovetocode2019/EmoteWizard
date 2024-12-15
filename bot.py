import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
import asyncpg
import datetime
import json
import logging
import os
import re
import sys
import traceback

from cogs.utils import cache, config

logging.basicConfig(level=logging.INFO, format="(%(asctime)s) %(levelname)s %(message)s", datefmt="%m/%d/%y - %H:%M:%S %Z",)

def get_prefix(bot, message):
    prefixes = [f"<@!{bot.user.id}> ", f"<@{bot.user.id}> "]
    if message.guild:
        prefixes.extend(bot.prefixes.get(message.guild.id, ["e!", "e."]))
    else:
        prefixes.extend(["e!", "e.", "!"])
    return prefixes

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

    async def set_webhook(self, webhook):
        self.webhook_id = webhook.id if webhook else None

        query = """INSERT INTO guild_config (guild_id, webhook_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id) DO UPDATE
                   SET webhook_id=$2;
                """
        await self.bot.db.execute(query, self.guild_id, self.webhook_id)

class EmoteWizard(commands.Bot):
    def __init__(self):
        intents = discord.Intents(
            guilds=True,
            emojis=True,
            messages=True,
            message_content=True,
            reactions=True,
            webhooks=True
        )

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            allowed_installs=app_commands.AppInstallationType(guild=True, user=False)
        )

    async def setup_hook(self):
        self.uptime = datetime.datetime.utcnow()
        self.prefixes = config.Config("prefixes.json")
        self.faked_messages = {}

        if not os.path.exists("stickers"):
            os.mkdir("stickers")

        self.session = aiohttp.ClientSession()

        async def init(conn):
            await conn.set_type_codec(
                "jsonb",
                schema="pg_catalog",
                encoder=json.dumps,
                decoder=json.loads,
                format="text"
            )
        self.db = await asyncpg.create_pool(self.config.sql, init=init)

        query = """CREATE TABLE IF NOT EXISTS guild_config (
                   guild_id BIGINT PRIMARY KEY,
                   webhook_id BIGINT
                   );

                   CREATE TABLE IF NOT EXISTS stickers (
                   owner_id BIGINT,
                   name TEXT UNIQUE,
                   content_path TEXT
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

        await self.load_extension("jishaku")

        for cog in extensions:
            try:
                await self.load_extension(cog)
            except Exception as exc:
                logging.info(f"Couldn't load {cog}")
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)

    @cache.cache()
    async def get_webhook_config(self, guild):
        query = """SELECT *
                   FROM guild_config
                   WHERE guild_config.guild_id=$1;
                """
        record = await self.db.fetchrow(query, guild.id)

        if not record:
            record =  {"guild_id": guild.id, "webhook_id": None}

        return GuildConfig.from_record(dict(record), self)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name} - {self.user.id}")
        self.guild = self.get_guild(self.config.guild)
        self.console = bot.get_channel(self.config.console)

    def get_guild_prefix(self, guild):
        return self.prefixes.get(guild.id, [self.user.mention])[0]

    def get_guild_prefixes(self, guild):
        return self.prefixes.get(guild.id, ["e!", "e."])

    def replace_emojis(self, content):
        replaced = content

        # Look for 'emojis' in the message
        emojis = re.finditer("\;[^;]+\;", content)
        possible_emojis = re.finditer("\:\w+:", content)

        # Iter through the found emois name
        found = []

        # Replace emojis using ;emoji;
        for name in emojis:
            emoji = discord.utils.get(self.emojis, name=name.group(0).replace(";", ""))
            if emoji and str(emoji) not in found:
                replaced = replaced.replace(name.group(0), str(emoji))
                found.append(str(emoji))

        # Replace emojis using :emoji:
        for name in possible_emojis:
            emoji = discord.utils.get(self.emojis, name=name.group(0).replace(":", ""))
            span = name.span(0)
            full_emoji = re.search(".*<a?", content[:span[0]]) and re.search("\d+>.*", content[span[1]+1:])
            if emoji and str(emoji) not in found and not full_emoji:
                replaced = replaced.replace(name.group(0), str(emoji))
                found.append(str(emoji))

        return replaced, found

    def run(self):
        super().run(self.config.token)

    async def logout(self):
        await self.db.close()
        await self.session.close()
        await super().logout()

    @discord.utils.cached_property
    def config(self):
        return __import__("config")

EmoteWizard().run()
