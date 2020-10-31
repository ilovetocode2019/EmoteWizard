import discord
from discord.ext import commands

import json

class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="embed", description="Create an embed")
    async def embed(self, ctx, *, data):
        try:
            data = json.loads(data)
        except:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            return await ctx.send(":x: Make sure your using valid json syntax", delete_after=5)

        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        em = discord.Embed.from_dict(data)

        if ctx.guild.me.guild_permissions.manage_messages and webhook and webhook["webhook_id"]:
            await ctx.message.delete()
            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            try:
                await webhook.send(embed=em, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url)
            except discord.HTTPException:
                return await ctx.send(":x: Failed to send your embed. Make sure your using valid Discord objects.", delete_after=5)
        else:
            try:
                await ctx.send(embed=em)
            except discord.HTTPException:
                return await ctx.send(":x: Failed to send your embed. Make sure your using valid Discord objects.")

    @commands.command(name="reply", description="Reply to a message")
    async def reply(self, ctx, message: discord.Message, *, reply):
        query = """SELECT *
                   FROM webhooks
                   WHERE webhooks.guild_id=$1;
                """
        webhook = await self.bot.db.fetchrow(query, ctx.guild.id)

        em = discord.Embed(description=f"{message.content} \n\n[Jump to message]({message.jump_url})", color=discord.Color.blurple())
        em.set_author(name=message.author.display_name, icon_url=message.author.avatar_url)
        em.add_field(name="Reply", value=reply)

        if ctx.guild.me.guild_permissions.manage_messages and webhook and webhook["webhook_id"]:
            await ctx.message.delete()
            webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            await webhook.send(embed=em, username=ctx.author.display_name, avatar_url=ctx.author.avatar_url)
        else:
            await ctx.send(embed=em)        

def setup(bot):
    bot.add_cog(Embeds(bot))