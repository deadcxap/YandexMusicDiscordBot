import os
import logging
from aiohttp import ClientSession

import discord
from discord.ext.commands import Bot
from discord.ext import tasks

intents = discord.Intents.default()
bot = Bot(intents=intents)

cogs_list = [
    'general',
    'voice',
    'settings'
]

@bot.event
async def on_ready():
    logging.info("Bot's ready!")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/voice vibe"))

@tasks.loop(seconds=3600)
async def update_server_count():
    # Don't update server count in debug mode
    if os.getenv('DEBUG') == 'True':
        return

    async with ClientSession() as session:
        if token := os.getenv('PROMO_TOKEN_1'):
            res = await session.post(
                'https://api.server-discord.com/v2/bots/1325795708019806250/stats',
                headers={'Authorization': token},
                data={'servers': len(bot.guilds), 'shards': bot.shard_count or 1}
            )
            if not res.ok:
                logging.error(f'Failed to update server count 1: {res.status} {await res.text()}')

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    try:
        import coloredlogs
        coloredlogs.install(level=logging.DEBUG)
    except ImportError:
        pass

    if os.getenv('DEBUG') == 'True':
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('discord').setLevel(logging.INFO)
        logging.getLogger('pymongo').setLevel(logging.INFO)
        logging.getLogger('yandex_music').setLevel(logging.WARNING)
    else:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger('discord').setLevel(logging.WARNING)
        logging.getLogger('pymongo').setLevel(logging.WARNING)
        logging.getLogger('yandex_music').setLevel(logging.WARNING)

    if not os.path.exists('music'):
        os.mkdir('music')
    token = os.getenv('TOKEN')
    if not token:
        raise ValueError('You must specify the bot TOKEN in your enviroment')

    for cog in cogs_list:
        bot.load_extension(f'MusicBot.cogs.{cog}')

    bot.run(token)
