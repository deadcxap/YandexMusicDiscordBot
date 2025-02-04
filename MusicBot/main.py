import os
import logging

import discord
from discord.ext.commands import Bot

intents = discord.Intents.default()
intents.message_content = True
bot = Bot(intents=intents)

cogs_list = [
    'general',
    'voice',
    'settings'
]

@bot.event
async def on_ready():
    logging.info("Bot's ready!")

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
