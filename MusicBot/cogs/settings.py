from typing import Literal, cast

import discord
from discord.ext.commands import Cog

from MusicBot.database import BaseUsersDatabase, BaseGuildsDatabase

def setup(bot):
    bot.add_cog(Settings(bot))

class Settings(Cog):

    settings = discord.SlashCommandGroup("settings", "Команды для изменения настроек бота.")

    def __init__(self, bot: discord.Bot):
        self.db = BaseGuildsDatabase()
        self.users_db = BaseUsersDatabase()
        self.bot = bot

    @settings.command(name="show", description="Показать текущие настройки бота.")
    async def show(self, ctx: discord.ApplicationContext) -> None:
        guild = await self.db.get_guild(ctx.guild.id, projection={
            'allow_explicit': 1, 'always_allow_menu': 1,
            'vote_next_track': 1, 'vote_add_track': 1, 'vote_add_album': 1, 'vote_add_artist': 1, 'vote_add_playlist': 1,
            'allow_connect': 1, 'allow_disconnect': 1
        })
        embed = discord.Embed(title="Настройки бота", color=0xfed42b)

        explicit = "✅ - Разрешены" if guild['allow_explicit'] else "❌ - Запрещены"
        menu = "✅ - Всегда доступно" if guild['always_allow_menu'] else "❌ - Если в канале 1 человек."
        
        vote = "✅ - Переключение" if guild['vote_next_track'] else "❌ - Переключение"
        vote += "\n✅ - Добавление треков" if guild['vote_add_track'] else "\n❌ - Добавление треков"
        vote += "\n✅ - Добавление альбомов" if guild['vote_add_album'] else "\n❌ - Добавление альбомов"
        vote += "\n✅ - Добавление артистов" if guild['vote_add_artist'] else "\n❌ - Добавление артистов"
        vote += "\n✅ - Добавление плейлистов" if guild['vote_add_playlist'] else "\n❌ - Добавление плейлистов"

        connect = "\n✅ - Разрешено всем" if guild['allow_connect'] else "\n❌ - Только для участникам с правами управления каналом"

        embed.add_field(name="__Explicit треки__", value=explicit, inline=False)
        embed.add_field(name="__Меню проигрывателя__", value=menu, inline=False)
        embed.add_field(name="__Голосование__", value=vote, inline=False)
        embed.add_field(name="__Подключение и Отключение__", value=connect, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)
    
    @settings.command(name="connect", description="Разрешить/запретить отключение/подключение бота к каналу участникам без прав управления каналом.")
    async def connect(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = await self.db.get_guild(ctx.guild.id, projection={'allow_connect': 1})
        await self.db.update(ctx.guild.id, {'allow_connect': not guild['allow_connect']})
        await ctx.respond(f"Отключение/подключение бота к каналу теперь {'✅ разрешено' if not guild['allow_connect'] else '❌ запрещено'} участникам без прав управления каналом.", delete_after=15, ephemeral=True)
    
    @settings.command(name="explicit", description="Разрешить или запретить воспроизведение Explicit треков (пока что неполноценно).")
    async def explicit(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = await self.db.get_guild(ctx.guild.id, projection={'allow_explicit': 1})
        await self.db.update(ctx.guild.id, {'allow_explicit': not guild['allow_explicit']})
        await ctx.respond(f"Треки с содержанием не для детей теперь {'✅ разрешены' if not guild['allow_explicit'] else '❌ запрещены'}.", delete_after=15, ephemeral=True)

    @settings.command(name="menu", description="Разрешить или запретить использование меню проигрывателя, если в канале больше одного человека.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = await self.db.get_guild(ctx.guild.id, projection={'always_allow_menu': 1})
        await self.db.update(ctx.guild.id, {'always_allow_menu': not guild['always_allow_menu']})
        await ctx.respond(f"Меню проигрывателя теперь {'✅ доступно' if not guild['always_allow_menu'] else '❌ недоступно'} в каналах с несколькими людьми.", delete_after=15, ephemeral=True)

    @settings.command(name="vote", description="Настроить голосование.")
    @discord.option(
        "vote_type",
        description="Тип голосования.",
        type=discord.SlashCommandOptionType.string,
        choices=['+Всё', '-Всё', 'Переключение', 'Трек', 'Альбом', 'Плейлист'],
        default='+Всё'
    )
    async def vote(self, ctx: discord.ApplicationContext, vote_type: Literal['+Всё', '-Всё', 'Переключение', 'Трек', 'Альбом', 'Плейлист']) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = await self.db.get_guild(ctx.guild.id, projection={'vote_next_track': 1, 'vote_add_track': 1, 'vote_add_album': 1, 'vote_add_artist': 1, 'vote_add_playlist': 1})
        
        if vote_type == '-Всё':
            await self.db.update(ctx.guild.id, {
                'vote_next_track': False,
                'vote_add_track': False,
                'vote_add_album': False,
                'vote_add_artist': False,
                'vote_add_playlist': False
                }
            )
            response_message = "Голосование ❌ выключено."
        elif vote_type == '+Всё':
            await self.db.update(ctx.guild.id, {
                'vote_next_track': True,
                'vote_add_track': True,
                'vote_add_album': True,
                'vote_add_artist': True,
                'vote_add_playlist': True
               }
            )
            response_message = "Голосование ✅ включено."
        elif vote_type == 'Переключение':
            await self.db.update(ctx.guild.id, {'vote_next_track': not guild['vote_next_track']})
            response_message = "Голосование за переключение трека " + ("❌ выключено." if guild['vote_next_track'] else "✅ включено.")
        elif vote_type == 'Трек':
            await self.db.update(ctx.guild.id, {'vote_add_track': not guild['vote_add_track']})
            response_message = "Голосование за добавление трека " + ("❌ выключено." if guild['vote_add_track'] else "✅ включено.")
        elif vote_type == 'Альбом':
            await self.db.update(ctx.guild.id, {'vote_add_album': not guild['vote_add_album']})
            response_message = "Голосование за добавление альбома " + ("❌ выключено." if guild['vote_add_album'] else "✅ включено.")
        elif vote_type == 'Артист':
            await self.db.update(ctx.guild.id, {'vote_add_artist': not guild['vote_add_artist']})
            response_message = "Голосование за добавление артиста " + ("❌ выключено." if guild['vote_add_artist'] else "✅ включено.")
        elif vote_type == 'Плейлист':
            await self.db.update(ctx.guild.id, {'vote_add_playlist': not guild['vote_add_playlist']})
            response_message = "Голосование за добавление плейлиста " + ("❌ выключено." if guild['vote_add_playlist'] else "✅ включено.")

        await ctx.respond(response_message, delete_after=15, ephemeral=True)
