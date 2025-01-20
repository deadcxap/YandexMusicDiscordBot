import os
import logging

import discord
from discord.ext.commands import Bot

try:
    import coloredlogs
    coloredlogs.install()
except ImportError:
    pass

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
    
    if not os.path.exists('music'):
        os.mkdir('music')
    token = os.getenv('TOKEN')
    if not token:
        raise ValueError('You must specify the bot TOKEN in your enviroment')
    
    for cog in cogs_list:
        bot.load_extension(f'MusicBot.cogs.{cog}')
    
    logging.basicConfig(format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    logging.getLogger('discord').setLevel(logging.INFO)
    
    bot.run(token)
