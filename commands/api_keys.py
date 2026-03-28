import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import secrets
import os
import io
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from utility.config import database
from utility.version import APP_VERSION
from utility.library import extract_domain

bot_url = os.getenv('BOT_URL')
bare_url = extract_domain(bot_url)


registration_message = f"""
In the attached zip file you will find a configured `ini` file and the latest version of the module file.

**The `ini` file should be placed in your profile folder (same place as the `GrooveStats.ini`)**
On Windows this will typically be in `C:\\Users\\<YourUsername>\\AppData\\Roaming\\ITGmania\\Save\\LocalProfiles`
On Linux it will typically be in `~/.itgmania/Save/LocalProfiles`

**The module file should be placed in `Modules` folder of the Simply Love Theme.**
On Windows this will typically be in `C:\\Games\\ITGmania\\Themes\\Simply Love\\Modules`
or `C:\\Users\\<YourUsername>\\AppData\\Roaming\\ITGmania\\Themes\\Simply Love\\Modules`

On Linux this will typically be in the installed directory (by default /opt/itgmania/Themes/Simply Love/Modules)
or `~/.itgmania/Themes/Simply Love/Modules`

(In case you are using a different fork of Simply Love, like ZMOD, it should go to its `Modules` folder.)

**You also must add the `{bare_url}` to `Preferences.ini` `HttpAllowHosts=*.groovestats.com,*.itgmania.com,{bare_url}`**
It is IMPORTANT that there are no spaces between the entries!

On Windows this file is typically located in `C:\\Users\\<YourUsername>\\AppData\\Roaming\\ITGmania\\Save\\Preferences.ini`
On Linux it is typically located in `~/.itgmania/Save/Preferences.ini`

"""


def _lua_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def file_pack(api_key: str, bot_url: str) -> discord.File:
    package_version = APP_VERSION

    ini_content = f"[DiscordLeaderboard]\nAPIKey={api_key}\n"

    lua_path = Path(__file__).resolve().parents[1] / 'ResultScraper' / 'ResultScraper.lua'
    lua_content = lua_path.read_text(encoding='utf-8')

    version_line = _lua_quote(package_version)
    if re.search(r'^\s*local\s+version\s*=.*$', lua_content, re.MULTILINE):
        patched_lua = re.sub(
            r'^\s*local\s+version\s*=.*$',
            f'local version = {version_line}',
            lua_content,
            count=1,
            flags=re.MULTILINE
        )
    else:
        patched_lua = f'local version = {version_line}\n' + lua_content

    bot_line = f"local botURL = {_lua_quote(bot_url)}"
    if re.search(r'^\s*local\s+botURL\s*=.*$', patched_lua, re.MULTILINE):
        patched_lua = re.sub(
            r'^\s*local\s+botURL\s*=.*$',
            bot_line,
            patched_lua,
            count=1,
            flags=re.MULTILINE
        )
    else:
        patched_lua = bot_line + "\n" + patched_lua

    lua_output_name = f"ResultScraper_{package_version}.lua"
    zip_output_name = f"DiscordLeaderboard_{package_version}.zip"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('DiscordLeaderboard.ini', ini_content)
        archive.writestr(lua_output_name, patched_lua)

    zip_buffer.seek(0)
    return discord.File(fp=zip_buffer, filename=zip_output_name)

def generate_and_store_api_key(user_id):
    while True:
        api_key = secrets.token_urlsafe(20)[:20]
        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('SELECT 1 FROM USERS WHERE APIKey = ?', (api_key,))
        if not c.fetchone():
            conn.close()
            break
        conn.close()

    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO USERS (DiscordUser, APIKey) VALUES (?, ?)', (user_id, api_key))
    conn.commit()
    conn.close()

    return api_key
    


class APIKeysCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Register player by generating API key
    #================================================================================================

    @app_commands.command(name="register", description="Initial registration. reset_key = True - Resets key if you already had one.")
    async def register(self, Interaction: discord.Interaction, reset_key: bool = False):
        if Interaction.guild is None:
            await Interaction.response.send_message("This command can only be used in a server.")
            return


        
        if not bot_url:
            await Interaction.response.send_message('BOT_URL is not configured on the server. Let your server administrator know!', ephemeral=True)
            return

        user_id = str(Interaction.user.id)
        
        if reset_key:
            api_key = generate_and_store_api_key(user_id)
            pack_file = file_pack(api_key, bot_url)
            await Interaction.response.send_message('Your API Key has been reset. Check your DM for the files and instructions.', ephemeral=True)

            await Interaction.user.send(registration_message + f"\nYour new API Key: `{api_key}`", file=pack_file)

        else:
            conn = sqlite3.connect(database)
            c = conn.cursor()
            c.execute('SELECT APIKey FROM USERS WHERE DiscordUser = ?', (user_id,))
            row = c.fetchone()
            conn.close()

            if row and row[0]:
                await Interaction.response.send_message('You are already registered. Use the command with reset_key = True to reset your API Key.', ephemeral=True)
                return

            api_key = generate_and_store_api_key(user_id)
            pack_file = file_pack(api_key, bot_url)

            await Interaction.user.send(registration_message + f"\nYour API Key: `{api_key}`", file=pack_file)

            await Interaction.response.send_message('Registration successful! Check your DM for the files and instructions.', ephemeral=True)

                
    #================================================================================================
    # Send latest files to player without resetting API key
    #================================================================================================
    @app_commands.command(name="update", description="Sends you the latest module and ini file.")
    async def update(self, Interaction: discord.Interaction):
        if Interaction.guild is None:
            await Interaction.response.send_message("This command can only be used in a server.")
            return

        user_id = str(Interaction.user.id)

        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('SELECT APIKey FROM USERS WHERE DiscordUser = ?', (user_id,))
        row = c.fetchone()
        conn.close()

        if not row or not row[0]:
            await Interaction.response.send_message('You are not registered yet. Use the /register command first.', ephemeral=True)
            return

        api_key = row[0]
        bot_url = os.getenv('BOT_URL')
        if not bot_url:
            await Interaction.response.send_message('BOT_URL is not configured on the server. Let your server administrator know!', ephemeral=True)
            return

        pack_file = file_pack(api_key, bot_url)

        await Interaction.user.send(registration_message + f"\nYour API Key: `{api_key}`", file=pack_file)

        await Interaction.response.send_message('Check your DM for the latest files and instructions.', ephemeral=True)



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

    #================================================================================================
    # Toggle Update Notifications
    #================================================================================================

    @app_commands.command(name="updatenotifications", description="Toggles receiving update notifications in DM.")
    async def update_notifications(self, interaction: discord.Interaction):
        # if interaction.guild is None:
        #     await interaction.response.send_message("This command can only be used in a server.")
        #     return

        user_id = str(interaction.user.id)

        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('SELECT updateNotification FROM USERS WHERE DiscordUser = ?', (user_id,))
        row = c.fetchone()

        if not row:
            await interaction.response.send_message('You are not registered yet. Use the /register command first.', ephemeral=True)
            return

        current_setting = row[0]
        new_setting = not current_setting

        c.execute('UPDATE USERS SET updateNotification = ? WHERE DiscordUser = ?', (new_setting, user_id))
        conn.commit()
        conn.close()

        status = "enabled" if new_setting else "disabled"
        await interaction.response.send_message(f"Update notifications have been {status}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(APIKeysCog(bot))
