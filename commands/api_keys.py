import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import secrets
import os
from datetime import datetime, timedelta

from utility.config import database


class APIKeysCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Generate API key
    #================================================================================================

    @app_commands.command(name="generate", description="Generates a new API key and sends it to your DM.")
    async def generate(self, Interaction: discord.Interaction):
        if Interaction.guild is None:
            await Interaction.response.send_message("This command can only be used in a server.")
            return

        user_id = str(Interaction.user.id)

        while True:
            api_key = secrets.token_urlsafe(20)[:20]
            conn = sqlite3.connect(database)
            c = conn.cursor()
            c.execute('SELECT 1 FROM USERS WHERE APIKey = ?', (api_key,))
            if not c.fetchone():
                break
            conn.close()

        c.execute('INSERT OR REPLACE INTO USERS (DiscordUser, APIKey) VALUES (?, ?)', (user_id, api_key))
        conn.commit()
        conn.close()

        bot_url = os.getenv('BOT_URL')
        ini_content = f"BotURL={bot_url}\nAPIKey={api_key}\n"
        with open('DiscordLeaderboard.ini', 'w') as ini_file:
            ini_file.write(ini_content)

        await Interaction.user.send(
            f"""This is your new API key. DO NOT SHARE IT! If you had a key previously, the old one will no longer work.
        \nAPI Key: `{api_key}`
        \nCompleted ini file has been attached for your convenience. Please copy it into your profile folder.
        \nAlso note that your scores will be sent to all servers where both you and the bot are present.
        """,
            file=discord.File('DiscordLeaderboard.ini')
        )
        await Interaction.response.send_message(f'Your key has been sent to your DM. Expect a message shortly.', ephemeral=True)

    #================================================================================================
    # Disable submitting scores
    #================================================================================================

    @app_commands.command(name="disable", description="Disables submitting scores. Without parameter will disable indefinitely.")
    async def disable(self, interaction: discord.Interaction, mins: int = 0, hours: int = 0, days: int = 0):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.")
            return

        user_id = str(interaction.user.id)

        if mins == 0 and hours == 0 and days == 0:
            disabled_until = "disabled"
        else:
            current_time = datetime.now()
            disabled_until = current_time + timedelta(minutes=mins, hours=hours, days=days)
            disabled_until = disabled_until.strftime(os.getenv('DATE_FORMAT'))

        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', (disabled_until, user_id))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"Submitting scores has been disabled until {disabled_until}", ephemeral=True)

    #================================================================================================
    # Enable submitting scores
    #================================================================================================

    @app_commands.command(name="enable", description="Enables submitting scores.")
    async def enable(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.")
            return

        user_id = str(interaction.user.id)

        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', ('enabled', user_id))
        conn.commit()
        conn.close()

        await interaction.response.send_message("Submitting scores has been enabled.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(APIKeysCog(bot))
