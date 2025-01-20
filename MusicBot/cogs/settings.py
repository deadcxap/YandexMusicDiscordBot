from typing import Literal, cast

import discord
from discord.ext.commands import Cog

from MusicBot.database import BaseUsersDatabase, BaseGuildsDatabase

def setup(bot):
    bot.add_cog(Settings(bot))

class Settings(Cog):

    settings = discord.SlashCommandGroup("settings", "Команды для изменения настроек бота.", guild_ids=[1247100229535141899])

    def __init__(self, bot: discord.Bot):
        self.db = BaseGuildsDatabase()
        self.users_db = BaseUsersDatabase()
        self.bot = bot

    @settings.command(name="show", description="Показать текущие настройки бота.")
    async def show(self, ctx: discord.ApplicationContext) -> None:
        guild = self.db.get_guild(ctx.guild.id)
        embed = discord.Embed(title="Настройки бота", color=0xfed42b)
        
        explicit = "✅ - Разрешены" if guild['allow_explicit'] else "❌ - Запрещены"
        menu = "✅ - Всегда доступно" if guild['always_allow_menu'] else "❌ - Если в канале 1 пользователь."
        
        vote = "✅ - Переключение" if guild['vote_next_track'] else "❌ - Переключение"
        vote += "\n✅ - Добавление треков" if guild['vote_add_track'] else "\n❌ - Добавление треков"
        vote += "\n✅ - Добавление альбомов" if guild['vote_add_album'] else "\n❌ - Добавление альбомов"
        vote += "\n✅ - Добавление артистов" if guild['vote_add_artist'] else "\n❌ - Добавление артистов"
        vote += "\n✅ - Добавление плейлистов" if guild['vote_add_playlist'] else "\n❌ - Добавление плейлистов"
        
        embed.add_field(name="__Explicit треки__", value=explicit, inline=False)
        embed.add_field(name="__Проигрыватель__", value=menu, inline=False)
        embed.add_field(name="__Голосование__", value=vote, inline=False)
        
        await ctx.respond(embed=embed, ephemeral=True)
    
    @settings.command(name="explicit", description="Разрешить или запретить воспроизведение Explicit треков.")
    async def explicit(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = self.db.get_guild(ctx.guild.id)
        self.db.update(ctx.guild.id, {'allow_explicit': not guild['allow_explicit']})
        await ctx.respond(f"Треки с содержанием не для детей теперь {'разрешены' if not guild['allow_explicit'] else 'запрещены'}.", delete_after=15, ephemeral=True)

    @settings.command(name="menu", description="Разрешить или запретить создание меню проигрывателя, даже если в канале больше одного человека.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = self.db.get_guild(ctx.guild.id)
        self.db.update(ctx.guild.id, {'always_allow_menu': not guild['always_allow_menu']})
        await ctx.respond(f"Меню проигрывателя теперь {'можно' if not guild['always_allow_menu'] else 'нельзя'} создавать в каналах с несколькими людьми.", delete_after=15, ephemeral=True)

    @settings.command(name="vote", description="Настроить голосование.")
    @discord.option(
        "vote_type",
        description="Тип голосования.",
        type=discord.SlashCommandOptionType.string,
        choices=['+Всё', '-Всё', 'Переключение', '+Трек', '+Альбом', '+Плейлист'],
        default='Всё'
    )
    async def vote(self, ctx: discord.ApplicationContext, vote_type: Literal['+Всё', '-Всё', 'Переключение', 'Трек', 'Альбом', 'Плейлист']) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return

        guild = self.db.get_guild(ctx.guild.id)
        
        if vote_type == '-Всё':
            self.db.update(ctx.guild.id, {
                'vote_next_track': False,
                'vote_add_track': False,
                'vote_add_album': False,
                'vote_add_artist': False,
                'vote_add_playlist': False
                }
            )
            response_message = "Голосование выключено."
        elif vote_type == '+Всё':
            self.db.update(ctx.guild.id, {
                'vote_next_track': True,
                'vote_add_track': True,
                'vote_add_album': True,
                'vote_add_artist': True,
                'vote_add_playlist': True
               }
            )
            response_message = "Голосование включено."
        elif vote_type == 'Переключение':
            self.db.update(ctx.guild.id, {'vote_next_track': not guild['vote_next_track']})
            response_message = "Голосование за переключение трека " + ("включено." if guild['vote_next_track'] else "выключено.")
        elif vote_type == 'Трек':
            self.db.update(ctx.guild.id, {'vote_add_track': not guild['vote_add_track']})
            response_message = "Голосование за добавление трека " + ("включено." if guild['vote_add_track'] else "выключено.")
        elif vote_type == 'Альбом':
            self.db.update(ctx.guild.id, {'vote_add_album': not guild['vote_add_album']})
            response_message = "Голосование за добавление альбома " + ("включено." if guild['vote_add_album'] else "выключено.")
        elif vote_type == 'Артист':
            self.db.update(ctx.guild.id, {'vote_add_artist': not guild['vote_add_artist']})
            response_message = "Голосование за добавление артиста " + ("включено." if guild['vote_add_artist'] else "выключено.")
        elif vote_type == 'Плейлист':
            self.db.update(ctx.guild.id, {'vote_add_playlist': not guild['vote_add_playlist']})
            response_message = "Голосование за добавление плейлиста " + ("включено." if guild['vote_add_playlist'] else "выключено.")
        
        await ctx.respond(response_message, delete_after=15, ephemeral=True)
