import discord
from discord.ext import commands

import logging
import aiohttp
import asyncpg

import config

logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) %(levelname)s %(message)s",
    datefmt="%m/%d/%y - %H:%M:%S %Z" 
)

extensions = ["cogs.meta", "cogs.emojis", "cogs.stickers"]

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=config.prefix)
        self.loop.create_task(self.load_extensions())
        self.loop.create_task(self.prepare_bot())

    async def load_extensions(self):
        self.load_extension("jishaku")
        self.get_command("jishaku").hidden = True

        for extension in extensions:
            self.load_extension(extension)

    async def prepare_bot(self):
        self.session = aiohttp.ClientSession()
        self.db = await asyncpg.create_pool(config.sql)

        query = """CREATE TABLE IF NOT EXISTS
                   webhooks (guild_id bigint, webhook_id bigint);
                   """
        await self.db.execute(query)

        query = """CREATE TABLE IF NOT EXISTS
                   stickers (owner_id bigint, name text, content_url text);
                   """
        await self.db.execute(query)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name} - {self.user.id}")

    def run(self):
        super().run(config.token)

bot = Bot()
bot.run()
