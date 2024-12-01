import discord

class FakedMessage:
    """Represents a user sent message that has been replace by a webhook."""

    def __init__(self, *, original, replacement, reply=None, is_sticker=False):
        self.original = original
        self.replacement = replacement
        self.reply = reply
        self.is_sticker = is_sticker

class Reply:
    """Represents a reply to another message."""

    def __init__(self, *, bot, quote, emoji, mention):
        self.bot = bot
        self.quote = quote
        self.emoji = emoji
        self.mention = mention

    def format_with(self, content):
        formatted_content = self.bot.replace_emojis(discord.utils.escape_mentions(content))[0]

        author = f"> {self.emoji} {self.quote.author.mention}{f'<:bottag:779737977856720906>' if self.quote.author.bot else ''}"
        reply = f"> [Jump to message](<{self.quote.jump_url}>) \n{formatted_content}"

        if self.quote.content:
            content = "\n".join([f"> {discord.utils.escape_mentions(line)}" for line in self.quote.content.split("\n")])
        else:
            items = []
            if self.quote.embeds:
                items.append("embed")
            if self.quote.attachments:
                items.append("attachment")
            if self.quote.stickers:
                items.append("sticker")

            content = f"> Jump to view {formats.join(items, last='and')} <:imageicon:779737947121123349>"

        return f"{author} \n{content} \n{reply}"

    @property
    def allowed_mentions(self):
        return discord.AllowedMentions(users=True)
