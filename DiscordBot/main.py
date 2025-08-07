from datetime import datetime, timedelta
import discord
from discord.ext import commands
from discord import app_commands
from discord.utils import escape_mentions
from discord.ui import Button, View
import sqlite3
import secrets
from flask import Flask, request, jsonify
import threading
import asyncio
import numpy as np
import os
import sys
import logging
from dotenv import load_dotenv

from library import *
from plot import *
import json


version = "1.3.0"

load_dotenv()

# Configure logging for Docker visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Force stdout to be unbuffered for Docker
sys.stdout.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)


#================================================================================================
# Set up the Discord bot and Flask app
#================================================================================================

# Initialize Flask app
app = Flask(__name__) #TODO: Change this to your app name

# Configure Flask logging
app.logger.setLevel(logging.INFO)
app.logger.addHandler(logging.StreamHandler(sys.stdout))

# Initialize Discord bot
intents = discord.Intents.default()
intents.members = True  # Enable the members intent
intents.message_content = True  # Enable the message content intent
client = commands.Bot(command_prefix='!', intents=intents)

db_folder = os.path.join(os.path.dirname(__file__), 'dbdata')
os.makedirs(db_folder, exist_ok=True)
database = os.path.join(db_folder, 'database.db')


#================================================================================================
# Sync commands on bot startup
#================================================================================================
#================================================================================================
@client.event
async def on_ready():
    print('Bot is ready.')
    try:
        sync = await client.tree.sync()
        print(f"Synced {len(sync)} commands.")
    except Exception as e:
        print(f"An error occurred while syncing commands: {e}")


#================================================================================================
# Commands
#================================================================================================
# Help command
#================================================================================================

@client.tree.command(name="help", description="Shows the available commands.")
async def help(Interaction: discord.Interaction):
    message: str = """
    **Here are the available commands:**
    `/help - Shows the available commands.`
    `/generate - Generates a new API key and sends it to your DM.`
    `/disable - Disables submitting scores for a specified amount of time or till re-enabled.`
    `/enable - Enables submitting scores.`
    `/score - Recall score result from database.`
    `/breakdown - More in depth breakdown of a score.`
    `/compare - Compare two users' scores.`
    `/usethischannel - (Un)Sets the current channel as the results channel. You may use it in multiple channels. (Admin only).`
    """

    await Interaction.response.send_message(message, ephemeral=True)


#================================================================================================
# Command to set or unset the results channel
#================================================================================================

@client.tree.command(name="usethischannel", description="(Un)Set the current channel as the results channel. (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def usethischannel(Interaction: discord.Interaction):
    if Interaction.guild is None:
        await Interaction.response.send_message("This command can only be used in a server.")
        return
    
    server_id = str(Interaction.guild.id)
    channel_id = str(Interaction.channel.id)

    try:
        conn = sqlite3.connect(database)
        c = conn.cursor()
        c.execute('SELECT 1 FROM CHANNELS WHERE serverID = ? AND channelID = ?', (server_id, channel_id))
        if c.fetchone():
            c.execute('DELETE FROM CHANNELS WHERE serverID = ? AND channelID = ?', (server_id, channel_id))
            await Interaction.response.send_message(f'This channel has been unset as the results channel.', ephemeral=True)
        else:
            c.execute('INSERT INTO CHANNELS (serverID, channelID) VALUES (?, ?)', (server_id, channel_id))
            await Interaction.response.send_message(f'This channel has been set as the results channel.', ephemeral=True)
        conn.commit()
        conn.close()
        #await Interaction.response.send_message(f'This channel has been set as the results channel.', ephemeral=True)
    except Exception as e:
        await Interaction.response.send_message(f"An error occurred: {e}")

@usethischannel.error
async def usethischannel_error(Interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await Interaction.response.send_message("You do not have the required permissions to use this command.", ephemeral=True)
    else:
        await Interaction.response.send_message("An error occurred while trying to run this command.", ephemeral=True)

#================================================================================================
# ADMIN COMMAND: Delete score - EXPERIMENTAL
#================================================================================================

@client.tree.command(name="deletescore", description="Delete a score from the database. (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def deletescore(Interaction: discord.Interaction, song: str, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if Interaction.guild is None:
        await Interaction.response.send_message("This command can only be used in a server.")
        return

    tableType = ''
    if iscourse:
        tableType = 'COURSES'
    if isdouble:
        tableType += 'DOUBLES'
    else:
        tableType += 'SINGLES'
    if ispump:
        tableType += '_PUMP'

    query = 'SELECT * FROM ' + tableType + ' WHERE 1=1'

    params = []

    # Use correct column name for song/course
    name_column = "courseName" if iscourse else "songName"
    if song:
        query += f" AND {name_column} LIKE ?"
        params.append(f"%{song}%")
    if user:
        query += " AND userID = ?"
        params.append(str(user.id))
    if user is None:
        query += " AND userID = ?"
        params.append(str(Interaction.user.id))
        user = Interaction.user
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack LIKE ?"
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute(query, params)
    results = c.fetchall()
    conn.close()

    if not results:
        await Interaction.response.send_message("No scores found matching the criteria.", ephemeral=True)
        return

    if len(results) > 1:
        # Check if there are too many results
        if len(results) > 25:
            await Interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
            return
            
        # Prepare select options using correct columns for course/song
        options = []
        for index, row in enumerate(results):
            if iscourse:
                label = f"{row[1]} - {row[4]} [{row[5]}]"
                description = f" EX Score: {row[8]}%, Pack: {row[2]}"
            else:
                label = f"{row[1]} - {row[2]} [{row[4]}]"
                description = f" EX Score: {row[6]}%, Pack: {row[3]}"
            options.append(discord.SelectOption(label=label, description=description, value=str(index)))

        class DeleteScoreSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose a score to delete...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_index = int(self.values[0])
                selected_row = results[selected_index]
                if iscourse:
                    data = extract_course_data_from_row(selected_row)
                else:
                    data = extract_data_from_row(selected_row)
                hash_index = 10

                embed, file = embedded_score(data, str(user.id), "Selected Score to Delete", discord.Color.red())
                class ConfirmDeleteButton(discord.ui.Button):
                    def __init__(self):
                        super().__init__(label="Delete", style=discord.ButtonStyle.danger)

                    
                    async def callback(self, button_interaction: discord.Interaction):
                        # Actually delete the selected score
                        conn = sqlite3.connect(database)
                        c = conn.cursor()
                        c.execute(f"DELETE FROM {tableType} WHERE hash = ? AND userID = ?", (selected_row[hash_index], str(user.id)))
                        deleted_rows = c.rowcount
                        conn.commit()
                        conn.close()
                        if deleted_rows > 0:
                            await button_interaction.response.send_message(f"Successfully deleted the selected score.", ephemeral=True)
                        else:
                            await button_interaction.response.send_message("Failed to delete the score.", ephemeral=True)

                class DoNothingButton(discord.ui.Button):
                    def __init__(self):
                        super().__init__(label="Do Nothing", style=discord.ButtonStyle.secondary)

                    async def callback(self, button_interaction: discord.Interaction):
                        await button_interaction.response.send_message("No action taken.", ephemeral=True)

                view = discord.ui.View()
                view.add_item(ConfirmDeleteButton())
                view.add_item(DoNothingButton())

                await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=True, view=view)

        view = discord.ui.View()
        view.add_item(DeleteScoreSelect())
        await Interaction.response.send_message("Multiple scores found. Please select one to delete:", view=view, ephemeral=True)
    else:
        selected_row = results[0]
        if iscourse:
            data = extract_course_data_from_row(selected_row)
            hash_index = 10
        else:
            data = extract_data_from_row(selected_row)
            hash_index = 10
        embed, file = embedded_score(data, str(user.id), "Selected Score to Delete", discord.Color.red())

        class ConfirmDeleteButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="Delete", style=discord.ButtonStyle.danger)

            async def callback(self, button_interaction: discord.Interaction):
                conn = sqlite3.connect(database)
                c = conn.cursor()
                c.execute(f"DELETE FROM {tableType} WHERE hash = ? AND userID = ?", (selected_row[hash_index], str(user.id)))
                deleted_rows = c.rowcount
                conn.commit()
                conn.close()
                if deleted_rows > 0:
                    await button_interaction.response.send_message(f"Successfully deleted the selected score.", ephemeral=True)
                else:
                    await button_interaction.response.send_message("Failed to delete the score.", ephemeral=True)

        class DoNothingButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="Do Nothing", style=discord.ButtonStyle.secondary)

            async def callback(self, button_interaction: discord.Interaction):
                await button_interaction.response.send_message("No action taken.", ephemeral=True)

        view = discord.ui.View()
        view.add_item(ConfirmDeleteButton())
        view.add_item(DoNothingButton())

        await Interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=True, view=view)


#================================================================================================
# Generate API key
#================================================================================================

@client.tree.command(name="generate", description="Generates a new API key and sends it to your DM.")
async def generate(Interaction: discord.Interaction):
    if Interaction.guild is None:
        await Interaction.response.send_message("This command can only be used in a server.")
        return
    
    user_id = str(Interaction.user.id)

    # Generate a unique 20-character long key
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


    # Create the .ini file
    bot_url = os.getenv('BOT_URL')
    ini_content = f"BotURL={bot_url}\nAPIKey={api_key}\n"
    with open('DiscordLeaderboard.ini', 'w') as ini_file:
        ini_file.write(ini_content)

    # Send the .ini file as an attachment
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

@client.tree.command(name="disable", description="Disables submitting scores. Without parameter will disable indefinitely.")
async def disable(interaction: discord.Interaction, mins: int = 0, hours: int = 0, days: int = 0):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    user_id = str(interaction.user.id)

    # Calculate the future date and time based on the provided parameters
    if mins == 0 and hours == 0 and days == 0:
        disabled_until = "disabled"
    else:
        current_time = datetime.now()
        disabled_until = current_time + timedelta(minutes=mins, hours=hours, days=days)
        disabled_until = disabled_until.strftime(os.getenv('DATE_FORMAT'))

    # Database operations
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', (disabled_until, user_id))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"Submitting scores has been disabled until {disabled_until}", ephemeral=True)


#================================================================================================
# Enable submitting scores
#================================================================================================

@client.tree.command(name="enable", description="Enables submitting scores.")
async def enable(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    user_id = str(interaction.user.id)

    # Database operations
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', ('enabled', user_id))
    conn.commit()
    conn.close()

    await interaction.response.send_message("Submitting scores has been enabled.", ephemeral=True)


#================================================================================================
# Recall score result
#================================================================================================

@client.tree.command(name="score", description="Recall score result from database.")
async def score(interaction: discord.Interaction, song: str, isdouble: bool = False, ispump: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    tableType = ''
    if isdouble:
        tableType += 'DOUBLES'
    else:
        tableType += 'SINGLES'
    if failed:
        tableType += 'FAILS'
    if ispump:
        tableType += '_PUMP'
    
    query = 'SELECT * FROM ' + tableType + ' WHERE 1=1'

    params = []

    if song:
        query += " AND songName LIKE ?"
        params.append(f"%{song}%")
    if user:
        query += " AND userID = ?"
        params.append(str(user.id))
    if user is None:
        query += " AND userID = ?"
        params.append(str(interaction.user.id))
        user = interaction.user
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack LIKE ?"
        params.append(f"%{pack}%")

    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute(query, params)
    results = c.fetchall()
    conn.close()

    if not results:
        await interaction.response.send_message("No scores found matching the criteria.", ephemeral=private)
        return

    if len(results) > 1:
        # Check if there are too many results
        if len(results) > 25:
            await interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
            return
        options = [
            discord.SelectOption(
                label=f"{row[1]} - {row[2]} [{row[4]}]",
                description=f" EX Score: {row[6]}%, Pack: {row[3]}",
                value=str(index)
            )
            for index, row in enumerate(results)
        ]

        class ScoreSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose a score...", options=options)

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=private)
                
                selected_index = int(self.values[0])
                selected_row = results[selected_index]
                data = extract_data_from_row(selected_row)

                if isdouble:
                    data['style'] = 'double'
                data['gameMode'] = 'pump' if ispump else 'itg'

                embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
                embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

                # Add the breakdown button
                view = View()
                view.add_item(BreakdownButton(interaction, data['songName'], user, isdouble, ispump, failed, difficulty, pack, private))

                await interaction.followup.send(content=None, embed=embed, file=file, ephemeral=private, view=view)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=True)
    else:
        await interaction.response.defer(ephemeral=private)
        
        selected_row = results[0]
        data = extract_data_from_row(selected_row)

        if isdouble:
            data['style'] = 'double'
        embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

        # Add the breakdown button
        view = View()
        view.add_item(BreakdownButton(interaction, data['songName'], user, isdouble, ispump, failed, difficulty, pack, private))

        await interaction.followup.send(content=None, embed=embed, file=file, ephemeral=private, view=view)

#================================================================================================
# Recall course result
#================================================================================================

@client.tree.command(name="course", description="Recall course result from database.")
async def course(interaction: discord.Interaction, name: str, isdouble: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    


    tableType = 'COURSES'
    if isdouble:
        tableType += 'DOUBLES'
    else:
        tableType += 'SINGLES'
    if failed:
        tableType += 'FAILS'
    
    query = 'SELECT * FROM ' + tableType + ' WHERE 1=1'

    params = []

    if name:
        query += " AND courseName LIKE ?"
        params.append(f"%{name}%")
    if user:
        query += " AND userID = ?"
        params.append(str(user.id))
    if user is None:
        query += " AND userID = ?"
        params.append(str(interaction.user.id))
        user = interaction.user
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack LIKE ?"
        params.append(f"%{pack}%")

    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute(query, params)
    results = c.fetchall()
    conn.close()

    if not results:
        await interaction.response.send_message("No scores found matching the criteria.", ephemeral=private)
        return

    if len(results) > 1:
        # Check if there are too many results
        if len(results) > 25:
            await interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
            return
            
        options = [
            discord.SelectOption(
                label=f"{row[1]} - {row[2]} [{row[4]}]",
                description=f" EX Score: {row[6]}%, Pack: {row[3]}",
                value=str(index)
            )
            for index, row in enumerate(results)
        ]

        class ScoreSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose a score...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_index = int(self.values[0])
                selected_row = results[selected_index]
                data = extract_course_data_from_row(selected_row)

                if isdouble:
                    data['style'] = 'double'

                #print(data)
                embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
                embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)
                
                await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=True)
    else:
        selected_row = results[0]
        data = extract_course_data_from_row(selected_row)
        if isdouble:
            data['style'] = 'double'
        embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

        await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)



# Quick access to the score command from score that was submitted or recalled
class ScoreButton(discord.ui.Button):
    def __init__(self, interaction: discord.Interaction, song: str, user: discord.User, isdouble: bool, ispump: bool, failed: bool, difficulty: int, pack: str, private: bool):
        super().__init__(label="View Score", style=discord.ButtonStyle.primary)
        self.interaction = interaction
        self.song = song
        self.user = user
        self.isdouble = isdouble
        self.ispump = ispump
        self.failed = failed
        self.difficulty = difficulty
        self.pack = pack
        self.private = private

    async def callback(self, interaction: discord.Interaction):
        # Retrieve the breakdown command
        score_command = interaction.client.tree.get_command("score")
        if score_command is None:
            await interaction.response.send_message("The score command could not be found.", ephemeral=True)
            return

        # Create a namespace for the command arguments
        class Namespace:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        # Prepare the arguments for the breakdown command
        args = Namespace(
            interaction=interaction,
            song=self.song,
            user=self.user,
            isdouble=self.isdouble,
            ispump=self.ispump,
            iscourse=False,
            failed=self.failed,
            difficulty=self.difficulty,
            pack=self.pack,
            private=self.private
        )

        # Invoke the breakdown command
        await score_command._invoke_with_namespace(interaction, args)

#================================================================================================
# compare two users
#================================================================================================

@client.tree.command(name="compare", description="Compare two users' scores. If only one user is provided, it will compare their scores with yours.")
@app_commands.describe(user_one="The first user to compare", user_two="The second user to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha, _diff")
async def compare(interaction: discord.Interaction, user_two: discord.User, user_one: discord.User = None, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_ex", private: bool = True, pack: str = "", difficulty: int = 0, song_name: str = ""):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return    
    if user_one is None:
        user_one = interaction.user

    user_one_id = str(user_one.id)
    user_two_id = str(user_two.id)
    # Check not needed, Discord won't let you interact with users not on the server


    conn = sqlite3.connect(database)
    c = conn.cursor()


    if order == "asc_ex":
        order_by = "s1.exScore ASC"
    elif order == "desc_ex":
        order_by = "s1.exScore DESC"
    elif order == "asc_alpha":
        order_by = "s1.songName ASC"
    elif order == "desc_alpha":
        order_by = "s1.songName DESC"
    elif order == "asc_diff":
        order_by = "s1.exScore - s2.exScore ASC"
    elif order == "desc_diff":
        order_by = "s1.exScore - s2.exScore DESC"
    else:
        order_by = "s1.exScore DESC"  # Default order

    tableType = ''
    if iscourse:
        tableType = 'COURSES'
    if isdouble:
        tableType = 'DOUBLES'
    else:
        tableType = 'SINGLES'
    if ispump:
        tableType += '_PUMP'

    
    # Build the query with optional filters for difficulty and pack
    query = 'SELECT s1.songName, s1.artist, s1.pack, s1.difficulty, s1.exScore, s2.exScore FROM ' + tableType + ' s1 JOIN ' + tableType + ' s2 ON s1.hash = s2.hash WHERE s1.userID = ? AND s2.userID = ?'
    
    params = [user_one_id, user_two_id]

    if difficulty:
        query += " AND s1.difficulty = ? AND s2.difficulty = ?"
        params.extend([str(difficulty), str(difficulty)])
    if pack:
        query += " AND s1.pack LIKE ? AND s2.pack LIKE ?"
        params.extend([f"%{pack}%", f"%{pack}%"])
    if song_name:
        query += " AND s1.songName LIKE ? AND s2.songName LIKE ?"
        params.extend([f"%{song_name}%", f"%{song_name}%"])

    query += f" ORDER BY {order_by}"

    #print("Final Query:", query)
    #print("Parameters:", params)

    c.execute(query, params)
    common_scores = c.fetchall()
    conn.close()

    if not common_scores:
        await interaction.response.send_message("No common scores found between the two users.", ephemeral=private)
        return

    results = []
    for song_name, artist, pack, difficulty, user_one_ex_score, user_two_ex_score in common_scores:
        difference = round(float(user_one_ex_score) - float(user_two_ex_score), 2)
        results.append({
            "song_name": song_name,
            "artist": artist,
            "pack": pack,
            "difficulty": difficulty,
            "user_one_ex_score": user_one_ex_score,
            "user_two_ex_score": user_two_ex_score,
            "difference": difference
        })

    await compare_logic(interaction, page, order, private, results, user_one_id, user_two_id)


async def compare_logic(interaction: discord.Interaction, page: int, order, private, results, user_one_id, user_two_id):
    
    order_mapping = {
        "asc_ex": "Ascending EX Score",
        "desc_ex": "Descending EX Score",
        "asc_alpha": "Ascending Alphabetical Order",
        "desc_alpha": "Descending Alphabetical Order",
        "asc_diff": "Ascending Difference",
        "desc_diff": "Descending Difference"
    }
    
    embed=discord.Embed(title=f"Score Comparison - Order: {order_mapping[order]}", color=discord.Color.blue())
    embed.set_footer(text=f"Page {page}")
    #embed.set_author(name="Compare All")
    embed.add_field(name="Player One", value=f"<@!{user_one_id}>", inline=True)
    embed.add_field(name="Player Two", value=f"<@!{user_two_id}>", inline=True)
    embed.add_field(name="Difference", value="", inline=True)
    
    for i in range((page - 1) * 5, min(page * 5, len(results))):
        result = results[i]
        embed.add_field(
            name=f"{result['song_name']} - {result['artist']} [{result['difficulty']}]",
            value=f"Pack: {result['pack']}",
            inline=False
        )
        embed.add_field(name="", value=f"{result['user_one_ex_score']}%", inline=True)
        embed.add_field(name="", value=f"{result['user_two_ex_score']}%", inline=True)
        embed.add_field(name="", value=f"{result['difference']}%", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=private)

    class NextPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Next Page", style=discord.ButtonStyle.primary)

        async def callback(self, button_interaction: discord.Interaction):
            await compare_logic(button_interaction, page=page + 1, order=order, private=private, results=results, user_one_id=user_one_id, user_two_id=user_two_id)

    class PreviousPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Previous Page", style=discord.ButtonStyle.primary)

        async def callback(self, button_interaction: discord.Interaction):
            await compare_logic(button_interaction, page=page - 1, order=order, private=private, results=results, user_one_id=user_one_id, user_two_id=user_two_id)

    view = discord.ui.View()
    if page > 1:
        view.add_item(PreviousPageButton())
    view.add_item(NextPageButton())
    await interaction.edit_original_response(view=view)


#================================================================================================
# Unplayed songs
#================================================================================================

@client.tree.command(name="unplayed", description="Returns a list of songs that you have not played.")
@app_commands.describe(user_two="User to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha")
async def unplayed(interaction: discord.Interaction, user_two: discord.User = None, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_alpha", private: bool = True, pack: str = "", difficulty: int = 0):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return    

    conn = sqlite3.connect(database)
    c = conn.cursor()

    user_one_id = str(interaction.user.id)
    user_two_id = str(user_two.id) if user_two else None

    if order == "asc_alpha":
        order_by = "s1.songName ASC"
    elif order == "desc_alpha":
        order_by = "s1.songName DESC"
    else:
        order_by = "s1.songName DESC"  # Default order

    tableType = ''
    if iscourse:
        tableType = 'COURSES'
    if isdouble:
        tableType = 'DOUBLES'
    else:
        tableType = 'SINGLES'
    if ispump:
        tableType += '_PUMP'


    # Build the query with optional filters for difficulty and pack
    if user_two_id:
        query = 'SELECT DISTINCT s2.songName, s2.artist, s2.pack, s2.difficulty FROM ' + tableType + ' s2 LEFT JOIN '+ tableType + ' s1 ON s2.hash = s1.hash AND s1.userID = ? WHERE s1.userID IS NULL AND s2.userID = ?'
        params = [user_one_id, user_two_id]
        if difficulty:
            query += " AND s2.difficulty = ?"
            params.append(str(difficulty))
        if pack:
            query += " AND s2.pack LIKE ?"
            params.append(f"%{pack}%")

    else:
        query = 'SELECT DISTINCT s1.songName, s1.artist, s1.pack, s1.difficulty FROM ' + tableType + ' s1 LEFT JOIN ' + tableType + ' s2 ON s1.hash = s2.hash AND s2.userID = ? WHERE s2.userID IS NULL AND s1.userID != ?'
        params = [user_one_id, user_one_id]
        if difficulty:
            query += " AND s1.difficulty = ?"
            params.append(str(difficulty))
        if pack:
            query += " AND s1.pack LIKE ?"
            params.append(f"%{pack}%")



    query += f" ORDER BY {order_by}"

    c.execute(query, params)
    common_scores = c.fetchall()
    conn.close()

    if not common_scores:
        await interaction.response.send_message("No unplayed scores were found based on the criteria.", ephemeral=private)
        return

    results = []
    for song_name, artist, pack, difficulty in common_scores:
        results.append({
            "song_name": song_name,
            "artist": artist,
            "pack": pack,
            "difficulty": difficulty
        })
    await unplayed_logic(interaction, page, order, private, results, user_two_id)



async def unplayed_logic(interaction: discord.Interaction, page: int, order, private, results, user_two_id):
    
    order_mapping = {
        "asc_alpha": "Ascending Alphabetical Order",
        "desc_alpha": "Descending Alphabetical Order"
    }
    
    embed=discord.Embed(title=f"Unplayed charts - Order: {order_mapping[order]}", color=discord.Color.blue())
    embed.set_footer(text=f"Page {page}")
    if user_two_id:
        embed.add_field(name=f"Compared to user", value=f"<@!{user_two_id}>", inline=True)
    else:
        embed.add_field(name=f"Compared to all other players", value="", inline=True)
    # embed.add_field(name="Difference", value="", inline=True)
    
    for i in range((page - 1) * 5, min(page * 5, len(results))):
        result = results[i]
        embed.add_field(
            name=f"{result['song_name']} - {result['artist']} [{result['difficulty']}]",
            value=f"Pack: {result['pack']}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=private)

    class NextPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Next Page", style=discord.ButtonStyle.primary)

        async def callback(self, button_interaction: discord.Interaction):
            await unplayed_logic(button_interaction, page=page + 1, order=order, private=private, results=results, user_two_id=user_two_id)

    class PreviousPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Previous Page", style=discord.ButtonStyle.primary)

        async def callback(self, button_interaction: discord.Interaction):
            await unplayed_logic(button_interaction, page=page - 1, order=order, private=private, results=results, user_two_id=user_two_id)

    view = discord.ui.View()
    if page > 1:
        view.add_item(PreviousPageButton())
    view.add_item(NextPageButton())
    await interaction.edit_original_response(view=view)


#================================================================================================
# Breakdown of score
#================================================================================================

@client.tree.command(name="breakdown", description="More in depth breakdown of a score.")
async def breakdown(interaction: discord.Interaction, song: str, user: discord.User = None, isdouble: bool = False, ispump: bool = False, iscourse: bool = False,  failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    tableType = ''
    if iscourse:
        tableType += 'COURSES'
    if isdouble:
        tableType += 'DOUBLES'
    else:
        tableType += 'SINGLES'
    if failed:
        tableType += 'FAILS'
    if ispump:
        tableType += '_PUMP'

    
    query = 'SELECT * FROM ' + tableType + ' WHERE 1=1'
    
    params = []

    name_column = "courseName" if iscourse else "songName"
    if song:
        query += f" AND {name_column} LIKE ?"
        params.append(f"%{song}%")
    if user:
        query += " AND userID = ?"
        params.append(str(user.id))
    if user is None:
        query += " AND userID = ?"
        params.append(str(interaction.user.id))
        user = interaction.user
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack LIKE ?"
        params.append(f"%{pack}%")


    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute(query, params)
    results = c.fetchall()
    conn.close()

    if not results:
        await interaction.response.send_message("No scores found matching the criteria.", ephemeral=private)
        return

    if len(results) > 1:
        # Check if there are too many results
        if len(results) > 25:
            await interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
            return
            
        options = [
            discord.SelectOption(
                label=f"{row[1]} - {row[2]} [{row[4]}]",
                description=f" EX Score: {row[6]}%, Pack: {row[3]}",
                value=str(index)
            )
            for index, row in enumerate(results)
        ]

        class ScoreSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="Choose a score...", options=options)

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=private)
                
                selected_index = int(self.values[0])
                selected_row = results[selected_index]
                if iscourse:
                    data = extract_course_data_from_row(selected_row)
                    data['isCourse'] = iscourse
                else:
                    data = extract_data_from_row(selected_row)
                data['gameMode'] = 'pump' if ispump else 'itg'
                embed, file = embedded_breakdown(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

                view = View()
                view.add_item(ScoreButton(interaction, data['songName'], user, isdouble, ispump, failed, difficulty, pack, private))

                await interaction.followup.send(content=None, embed=embed, file=file, ephemeral=private, view=view)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=True)
    else:
        await interaction.response.defer(ephemeral=private)
        
        selected_row = results[0]
        if iscourse:
            data = extract_course_data_from_row(selected_row)
            data['isCourse'] = iscourse
        else:
            data = extract_data_from_row(selected_row)
        data['gameMode'] = 'pump' if ispump else 'itg'
        embed, file = embedded_breakdown(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
        view = View()
        if not iscourse:
            view.add_item(ScoreButton(interaction, data['songName'], user, isdouble, ispump, failed, difficulty, pack, private))

        await interaction.followup.send(content=None, embed=embed, file=file, ephemeral=private, view=view)



# Quick access to the breakdown command from score that was submitted or recalled
class BreakdownButton(discord.ui.Button):
    def __init__(self, interaction: discord.Interaction, song: str, user: discord.User, isdouble: bool, ispump: bool, failed: bool, difficulty: int, pack: str, private: bool):
        super().__init__(label="View Breakdown", style=discord.ButtonStyle.primary)
        self.interaction = interaction
        self.song = song
        self.user = user
        self.isdouble = isdouble
        self.ispump = ispump
        self.failed = failed
        self.difficulty = difficulty
        self.pack = pack
        self.private = private

    async def callback(self, interaction: discord.Interaction):
        # Retrieve the breakdown command
        breakdown_command = interaction.client.tree.get_command("breakdown")
        if breakdown_command is None:
            await interaction.response.send_message("The breakdown command could not be found.", ephemeral=True)
            return

        # Create a namespace for the command arguments
        class Namespace:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        # Prepare the arguments for the breakdown command
        args = Namespace(
            interaction=interaction,
            song=self.song,
            user=self.user,
            isdouble=self.isdouble,
            ispump=self.ispump,
            iscourse=False,  # Assuming this is not a course
            failed=self.failed,
            difficulty=self.difficulty,
            pack=self.pack,
            private=self.private
        )

        # Invoke the breakdown command
        await breakdown_command._invoke_with_namespace(interaction, args)

#================================================================================================
# Database
#================================================================================================
#================================================================================================

# Initialize database
def init_db():
    conn = sqlite3.connect(database)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS CONFIG
                    (version TEXT PRIMARY KEY)''')

    c.execute('''CREATE TABLE IF NOT EXISTS USERS
                 (DiscordUser TEXT PRIMARY KEY, APIKey TEXT, submitDisabled TEXT DEFAULT 'enabled')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS CHANNELS
                 (serverID TEXT, channelID TEXT, PRIMARY KEY (serverID, channelID))''')
    

    normal_schema = '''
                 (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty INTEGER,
                  itgScore REAL, exScore REAL, grade TEXT, length TEXT, stepartist TEXT, hash TEXT,
                  scatter JSON, life JSON, worstWindow TEXT, date TEXT, mods TEXT, description TEXT, prevBestEx REAL, radar JSON)
                  '''
    course_schema = '''
                 (userID TEXT, courseName TEXT, pack TEXT, entries TEXT, scripter TEXT, difficulty INTEGER,
                  description TEXT, itgScore REAL, exScore REAL, grade TEXT, hash TEXT,
                  life JSON, date TEXT, mods TEXT, prevBestEx REAL, radar JSON)
                  '''

    tables_normal = [
        'SINGLES', 'SINGLESFAILS', 'DOUBLES', 'DOUBLESFAILS',
        'SINGLES_PUMP', 'SINGLESFAILS_PUMP', 'DOUBLES_PUMP', 'DOUBLESFAILS_PUMP'
    ]
    tables_courses = [
        'COURSESSINGLES', 'COURSESSINGLESFAILS', 'COURSESDOUBLES', 'COURSESDOUBLESFAILS',
        'COURSESSINGLES_PUMP', 'COURSESSINGLESFAILS_PUMP', 'COURSESDOUBLES_PUMP', 'COURSESDOUBLESFAILS_PUMP'
    ]

    for table in tables_normal:
        c.execute(f'CREATE TABLE IF NOT EXISTS {table} {normal_schema}')
    for table in tables_courses:
        c.execute(f'CREATE TABLE IF NOT EXISTS {table} {course_schema}')


    conn.commit()
    conn.close()

init_db()


#================================================================================================
# Embedded score
#================================================================================================

def embedded_score(data, user_id, title="Users Best Score", color=discord.Color.dark_grey()):
    
    if data.get('prevBestEx') is None:
        data['prevBestEx'] = 0

        if data.get('gameMode') == 'pump':
            title = f"{title} - PUMP"
        else:
            title = f"{title} - ITG"

    if data.get('songName'):
        if data.get('scatterplotData') is None:
            embed = discord.Embed(title="Unable to recall score", color=color)
            embed.add_field(name="Error", value="Required data were not collected for old scores. If you want to recall then get better score :P", inline=False)
            file = discord.File('lmao2.gif', filename='lmao2.gif')
            embed.set_image(url="attachment://lmao2.gif")
            return embed, file

        if data.get('style') == 'double':
            style = 'D'
        else:
            style = 'S'
            
        grade = data.get('grade')
        mapped_grade = grade_mapping.get(grade, grade)
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
        embed.add_field(name="Song", value=data.get('songName'), inline=True)
        # embed.add_field(name="Artist", value=data.get('artist'), inline=True)
        embed.add_field(name="Pack", value=data.get('pack'), inline=True)
        embed.add_field(name="Difficulty", value= style + str(data.get('difficulty')), inline=True)
        # embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
        upscore = round(float(data.get('exScore')) - float(data.get('prevBestEx')), 2)
        embed.add_field(name="EX Score", value=f"{data.get('exScore')}% (+ {upscore}%)", inline=True)
        embed.add_field(name="Grade", value=mapped_grade, inline=True)
        embed.add_field(name="Length", value=data.get('length'), inline=True)
        # embed.add_field(name="Stepartist", value=data.get('stepartist'), inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)

        # Create the scatter plot and save it as an image
        logging.info(f"Starting scatterplot creation for song: {data.get('songName')}")
        create_scatterplot_from_json(data.get('scatterplotData'), data.get('lifebarInfo'), output_file='scatterplot.png')
        logging.info(f"Completed scatterplot creation for song: {data.get('songName')}")

        # Send the embed with the image attachment
        file = discord.File('scatterplot.png', filename='scatterplot.png')
        embed.set_image(url="attachment://scatterplot.png")
    
    else:
        if data.get('style') == 'double':
            style = 'D'
        else:
            style = 'S'
        grade = data.get('grade')
        mapped_grade = grade_mapping.get(grade, grade)
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
        embed.add_field(name="Course", value=data.get('courseName'), inline=True)
        embed.add_field(name="Scripter", value=data.get('scripter'), inline=True)
        embed.add_field(name="Pack", value=data.get('pack'), inline=True)
        embed.add_field(name="Difficulty", value= style + str(data.get('difficulty')), inline=True)
        embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
        upscore = round(float(data.get('exScore')) - float(data.get('prevBestEx')), 2)
        embed.add_field(name="EX Score", value=f"{data.get('exScore')}% (+ {upscore}%)", inline=True)
        embed.add_field(name="Grade", value=mapped_grade, inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)
        
        create_scatterplot_from_json(None, data.get('lifebarInfo'), output_file='scatterplot.png')
        file = discord.File('scatterplot.png', filename='scatterplot.png')
        embed.set_image(url="attachment://scatterplot.png")

    return embed, file


#================================================================================================
# Embedded Breakdown
#================================================================================================

def embedded_breakdown(data, user_id, title="Score Breakdown", color=discord.Color.dark_grey()):
    
    if data.get('gameMode') == 'pump':
        title = f"{title} - PUMP"
    else:
        title = f"{title} - ITG"

    if data.get('isCourse'):
        embed = discord.Embed(title=f"{title}", color=color)
        embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
        embed.add_field(name="Course Name", value=data.get('courseName'), inline=True)
        embed.add_field(name="Pack", value=data.get('pack'), inline=True)
        embed.add_field(name="EX Score", value=f"{data.get('exScore')}%", inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=False)
        embed.add_field(name="Scripter", value=data.get('scripter'), inline=True)
        radar = data.get('radar')
        if radar:
            embed.add_field(name="Holds/Rolls/Mines", value=f"""
                        Holds: {radar.get('Holds')[0]}/{radar.get('Holds')[1]}
                        Rolls: {radar.get('Rolls')[0]}/{radar.get('Rolls')[1]}
                        Mines: {radar.get('Mines')[0]}/{radar.get('Mines')[1]}""", inline=True)
        else:
            embed.add_field(name="Holds/Rolls/Mines", value="No radar data available", inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)

        entries = data.get('entries')
        entries_str = ""
        for entry in entries:
            length_sec = int(round(float(entry.get('length', 0))))
            mins = length_sec // 60
            secs = length_sec % 60
            entries_str += f"{entry.get('name', 'Unknown')} - {entry.get('artist', 'Unknown')} - {entry.get('difficulty', 'N/A')} - {mins}:{secs:02d}\n"
        entries_str = entries_str.strip()  # Remove trailing newline
        embed.add_field(name="Song | Artist | Diff | Length", value=entries_str, inline=True)

        create_scatterplot_from_json(None, data.get('lifebarInfo'), output_file='scatterplot.png')
        file = discord.File('scatterplot.png', filename='scatterplot.png')
        embed.set_image(url="attachment://scatterplot.png")
        return embed, file


    if data.get('worstWindow') is None:
        embed = discord.Embed(title="Unable to create breakdown", color=color)
        embed.add_field(name="Error", value="No judgement window data found for this score. Old score. If you want breakdown get better score :P", inline=False)
        file = discord.File('lmao2.gif', filename='lmao2.gif')
        embed.set_image(url="attachment://lmao2.gif")
        return embed, file


    embed = discord.Embed(title=f"{title}", color=color)
    embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
    embed.add_field(name="Song", value=data.get('songName'), inline=True)
    embed.add_field(name="Pack", value=data.get('pack'), inline=True)
    embed.add_field(name="EX Score", value=f"{data.get('exScore')}%", inline=True)
    embed.add_field(name="Date played", value=data.get('date'), inline=False)

    judgements = {
            'fa_p': 0,
            'e_fa': 0,
            'l_fa': 0,
            'e_ex': 0,
            'l_ex': 0,
            'e_gr': 0,
            'l_gr': 0,
            'e_de': 0,
            'l_de': 0,
            'e_wo': 0,
            'l_wo': 0,
            'miss': 0
        }
        
    y_values = [point['y'] for point in data['scatterplotData'] if point['y'] != 0]
    jt = set_scale(data.get('worstWindow'))


    for y in y_values:
        if jt['l_wo'] < y < jt['l_de']:
            judgements['l_wo'] += 1
        elif jt['l_de'] <= y < jt['l_gr']:
            judgements['l_de'] += 1
        elif jt['l_gr'] <= y < jt['l_ex']:
            judgements['l_gr'] += 1
        elif jt['l_ex'] <= y < jt['l_fa']:
            judgements['l_ex'] += 1
        elif jt['l_fa'] <= y < jt['l_fap']:
            judgements['l_fa'] += 1
        elif jt['l_fap'] <= y <= jt['e_fap']:
            judgements['fa_p'] += 1
        elif jt['e_fap'] < y <= jt['e_fa'] if jt['e_fa'] != 200 else y < jt['e_fa']:
            judgements['e_fa'] += 1
        elif jt['e_fa'] < y <= jt['e_ex'] if jt['e_ex'] != 200 else y < jt['e_ex']:
            judgements['e_ex'] += 1
        elif jt['e_ex'] < y <= jt['e_gr'] if jt['e_gr'] != 200 else y < jt['e_gr']:
            judgements['e_gr'] += 1
        elif jt['e_gr'] < y <= jt['e_de'] if jt['e_de'] != 200 else y < jt['e_de']:
            judgements['e_de'] += 1
        elif jt['e_de'] < y < jt['e_wo']:
            judgements['e_wo'] += 1
        elif y == 200:
            judgements['miss'] += 1
    judgements['miss'] = int(judgements['miss'] / 2)


    embed.add_field(name="Judgements (E/L)", 
                    value=f"""
                    FA+: {judgements['fa_p']}
                    FA:  {judgements['e_fa']+judgements['l_fa']} ({judgements['e_fa']}/{judgements['l_fa']})
                    EX:  {judgements['e_ex']+judgements['l_ex']} ({judgements['e_ex']}/{judgements['l_ex']})
                    GR:  {judgements['e_gr']+judgements['l_gr']} ({judgements['e_gr']}/{judgements['l_gr']})
                    DE:  {judgements['e_de']+judgements['l_de']} ({judgements['e_de']}/{judgements['l_de']})
                    WO:  {judgements['e_wo']+judgements['l_wo']} ({judgements['e_wo']}/{judgements['l_wo']})
                    Miss: {judgements['miss']}""", inline=True)

    radar = data.get('radar')
    if radar:
        embed.add_field(name="Holds/Rolls/Mines", value=f"""
                        Holds: {radar.get('Holds')[0]}/{radar.get('Holds')[1]}
                        Rolls: {radar.get('Rolls')[0]}/{radar.get('Rolls')[1]}
                        Mines: {radar.get('Mines')[0]}/{radar.get('Mines')[1]}""", inline=True)
    else:
        embed.add_field(name="Holds/Rolls/Mines", value="No radar data available", inline=True)

    y_values = np.array([100 - point['y'] for point in data.get('scatterplotData') if point['y'] not in [0, 200]])
    
    worst_window = float(data.get('worstWindow'))
    y_scaled = np.round(1000 * scale(y_values, -100, 100, -worst_window, worst_window), 1)

    max_error = np.round(np.max(np.abs(y_scaled)), 1)
    mean = np.round(np.mean(y_scaled), 1)
    std_dev_3 = np.round(np.std(y_scaled) * 3, 1)
    mean_abs_error = np.round(np.sum(np.abs(y_scaled)) / len(y_scaled)) #NOTE: mean_abs error is directly reimplemented from Simply-Love-SM5/BGAnimations/ScreenEvaluation common/Panes/Pane5/default.lua


    #TODO: Reimplement this from SimplyLove? I don't think it's necessary
    # test = 0
    # for y in y_values:
    #     test += (y - mean) ** 2

    # std_dev = np.round(np.sqrt(test / (len(y_values)-1)), 1)
    # print("std dev: ", std_dev, "std dev * 3: ", std_dev * 3)

    embed.add_field(name="Graph stats",
                    value=f"""
                    mean abs err: {mean_abs_error}ms
                    mean: {mean}ms
                    std dev*3: {std_dev_3}ms
                    max error: {max_error}ms
                    (SL rounds differently)""",
                    inline=True)
    embed.add_field(name="Mods", value=data.get('mods'), inline=True)

    logging.info(f"Starting distribution plot creation for song: {data.get('songName')}")
    create_distribution_from_json(data.get('scatterplotData'), data.get('worstWindow'), output_file='distribution.png')
    logging.info(f"Completed distribution plot creation for song: {data.get('songName')}")
    # Send the embed with the image attachment
    file = discord.File('distribution.png', filename='distribution.png')
    embed.set_image(url="attachment://distribution.png")

    return embed, file

#================================================================================================
# Get top 3 scores
#================================================================================================

def get_top_scores(selected_row, interaction, num, tableType):
    # Fetch the top num EX scores for the given hash that are also part of the same server
    conn = sqlite3.connect(database)
    c = conn.cursor()

    query = 'SELECT userID, exScore FROM ' + tableType + ' WHERE hash = ? AND userID IN (SELECT userID FROM ' + tableType + ' WHERE hash = ?) ORDER BY exScore DESC LIMIT ?'

    c.execute(query, (selected_row[10], selected_row[10], num))
    top_scores = c.fetchall()
    conn.close()

    # Filter the top scores to include only members of the current guild
    top_scores = [(uid, ex_score) for uid, ex_score in top_scores if interaction.guild.get_member(int(uid))]

    # Format the top 3 scores
    top_scores_message = ""
    for idx, (uid, ex_score) in enumerate(top_scores, start=1):
        top_scores_message += f"{idx}. <@!{uid}>, EX Score: {ex_score}%\n"

    return top_scores_message



#================================================================================================
# Flask route to receive external data and send it to Discord
#================================================================================================
#================================================================================================


# Flask route to receive external data
@app.route('/send', methods=['POST'])
def send_message():
    data = request.json

    client_version = data.get('version')
    if not client_version or client_version != version:
        return jsonify({'status': 'Incorrect version of Module used. Version needed: ' + version}), 400

    api_key = data.get('api_key')

    # Check if the request contains an API key
    if not api_key:
        return jsonify({'status': 'Submission is missing API Key.'}), 402

    # Check if the API key exists in the database and fetch DiscordUser and submitDisabled
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('SELECT DiscordUser, submitDisabled FROM USERS WHERE APIKey = ?', (api_key,))
    result = c.fetchone()
    conn.close()
    if not result:
        return jsonify({'status': 'API Key has not been found in database.'}), 403

    user_id, submit_disabled = result

    # Handle chunked data reconstruction
    if data.get('isChunked'):
        hash_key = data.get('hash')
        scatter_chunks = data.get('scatterplotChunks', 0)
        lifebar_chunks = data.get('lifebarChunks', 0)
        
        logger.info(f"Processing chunked submission for hash {hash_key}")
        logger.info(f"Expected chunks - Scatterplot: {scatter_chunks}, Lifebar: {lifebar_chunks}")
        logger.info(f"Available pending chunks: {list(pending_chunks.keys())}")
        
        # Reconstruct scatterplotData if we have chunks
        if scatter_chunks > 0:
            if hash_key not in pending_chunks:
                logger.error(f"Hash {hash_key} not found in pending chunks")
                return jsonify({'status': f'No chunks found for hash {hash_key}. Chunks may have timed out.'}), 400
                
            scatterplot_data = []
            scatter_chunk_dict = pending_chunks[hash_key]['scatterplot']
            
            # Check if we have all scatterplot chunks
            if len(scatter_chunk_dict) == scatter_chunks:
                for i in range(1, scatter_chunks + 1):
                    if i in scatter_chunk_dict:
                        scatterplot_data.extend(scatter_chunk_dict[i])
                data['scatterplotData'] = scatterplot_data
                logger.info(f"Reconstructed scatterplot data: {len(scatterplot_data)} points")
            else:
                missing_chunks = [i for i in range(1, scatter_chunks + 1) if i not in scatter_chunk_dict]
                logger.error(f"Missing scatterplot chunks: {missing_chunks}")
                return jsonify({'status': f'Missing scatterplot chunks: {missing_chunks}'}), 400
        
        # Reconstruct lifebarInfo if we have chunks
        if lifebar_chunks > 0:
            if hash_key not in pending_chunks:
                logger.error(f"Hash {hash_key} not found in pending chunks")
                return jsonify({'status': f'No chunks found for hash {hash_key}. Chunks may have timed out.'}), 400
                
            lifebar_data = []
            lifebar_chunk_dict = pending_chunks[hash_key]['lifebar']
            
            # Check if we have all lifebar chunks
            if len(lifebar_chunk_dict) == lifebar_chunks:
                for i in range(1, lifebar_chunks + 1):
                    if i in lifebar_chunk_dict:
                        lifebar_data.extend(lifebar_chunk_dict[i])
                data['lifebarInfo'] = lifebar_data
                logger.info(f"Reconstructed lifebar data: {len(lifebar_data)} points")
            else:
                missing_chunks = [i for i in range(1, lifebar_chunks + 1) if i not in lifebar_chunk_dict]
                logger.error(f"Missing lifebar chunks: {missing_chunks}")
                return jsonify({'status': f'Missing lifebar chunks: {missing_chunks}'}), 400
        
        # Clean up chunks after reconstruction
        if hash_key in pending_chunks:
            del pending_chunks[hash_key]
            logger.info(f"Cleaned up chunks for hash {hash_key}")

    # Check if the request contains all required data
    required_keys_song = [
        'songName', 'artist', 'pack', 'length', 'stepartist', 'difficulty', 'description',
        'itgScore', 'exScore', 'grade', 'hash', 'worstWindow', 'style', 'mods', 'radar', 'gameMode'
    ]
    required_keys_course = [
        'courseName', 'pack', 'entries', 'hash', 'scripter', 'itgScore', 'description',
        'exScore', 'grade', 'style', 'mods', 'difficulty', 'radar', 'gameMode'
    ]
    
    # For songs, also require scatterplotData and lifebarInfo (unless reconstructed from chunks)
    if data.get('songName'):
        if 'scatterplotData' not in data:
            required_keys_song.append('scatterplotData')
        if 'lifebarInfo' not in data:
            required_keys_song.append('lifebarInfo')
    
    # For courses, also require lifebarInfo (unless reconstructed from chunks)  
    if data.get('courseName'):
        if 'lifebarInfo' not in data:
            required_keys_course.append('lifebarInfo')

    # Debug: Check what data we have after chunk reconstruction
    if data.get('isChunked'):
        logger.info(f"After chunk reconstruction, data keys: {list(data.keys())}")
        logger.info(f"Has scatterplotData: {'scatterplotData' in data}")
        logger.info(f"Has lifebarInfo: {'lifebarInfo' in data}")
    
    if not (all(key in data for key in required_keys_song) or all(key in data for key in required_keys_course)):
        
        # Debug: Show which keys are missing
        if data.get('songName'):
            missing_song_keys = [key for key in required_keys_song if key not in data]
            logger.error(f"Missing song keys: {missing_song_keys}")
        if data.get('courseName'):
            missing_course_keys = [key for key in required_keys_course if key not in data]
            logger.error(f"Missing course keys: {missing_course_keys}")
        
        # user = client.get_user(int(user_id))

        # asyncio.run_coroutine_threadsafe(
        # user.send(
        #     "Your score was not submitted. Your submission is missing some data. Please update your module to the latest version to ensure all required data is sent."
        # ),
        # client.loop
        # )
        logger.error("Submission missing required data")
        return jsonify({'status': 'Submission is missing data. Update module to the latest version.'}), 400
    
    isPB = True
    tableType = ''

    if data.get('courseName'):
        tableType += 'COURSES'
    if data.get('style') == 'double':
        tableType += 'DOUBLES'
    else:
        tableType += 'SINGLES'
    if data.get('grade') == 'Grade_Failed':
        tableType += 'FAILS'
        isPB = False
    
    if data.get('gameMode') == 'pump':
        tableType += '_PUMP'
    
    conn = sqlite3.connect(database)
    c = conn.cursor()

    # Check if the entry is already present via the hash and user ID
    fetchExisting = 'SELECT exScore FROM ' + tableType + ' WHERE hash = ? AND userID = ?'

    c.execute(fetchExisting, (data.get('hash'), user_id))
    existing_entry = c.fetchone()

    # Compare the ex score
    existing_ex_score = float(existing_entry[0]) if existing_entry else 0
    new_ex_score = float(data.get('exScore'))
    
    if existing_entry and new_ex_score > existing_ex_score:
        if data.get('courseName'):
            updateExisting = 'UPDATE ' + tableType + ' SET itgScore = ?, exScore = ?, grade = ?, life = ?, date = ?, mods = ?, prevBestEx = ?, radar = ? WHERE hash = ? AND userID = ?'
            c.execute(updateExisting,
                      (data.get('itgScore'), 
                       new_ex_score,
                       data.get('grade'), 
                       str(data.get('lifebarInfo')), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('mods'),
                       existing_ex_score,
                       str(data.get('radar')),
                       data.get('hash'),
                       user_id))
            conn.commit()

        else:
            updateExisting = 'UPDATE ' + tableType + ' SET itgScore = ?, exScore = ?, grade = ?, scatter = ?, life = ?, worstWindow = ?, date = ?, mods = ?, length = ?, prevBestEx = ?, radar = ? WHERE hash = ? AND userID = ?'
            c.execute(updateExisting, 
                      (data.get('itgScore'), 
                       new_ex_score,
                       data.get('grade'), 
                       str(data.get('scatterplotData')), 
                       str(data.get('lifebarInfo')), 
                       data.get('worstWindow'), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('mods'),
                       data.get('length'), # I was sending the wrong value lmao
                       existing_ex_score,
                       str(data.get('radar')),
                       data.get('hash'),
                       user_id))
            conn.commit()


    elif new_ex_score > existing_ex_score:
        if data.get('courseName'):
            insertNew = 'INSERT INTO ' + tableType + ' (userID, courseName, pack, entries, scripter, itgScore, exScore, grade, hash, life, date, mods, difficulty, description, prevBestEx, radar) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            c.execute(insertNew,
                      (user_id, 
                       data.get('courseName'), 
                       data.get('pack'), 
                       str(data.get('entries')), 
                       data.get('scripter'), 
                       data.get('itgScore'), 
                       new_ex_score, 
                       data.get('grade'), 
                       data.get('hash'), 
                       str(data.get('lifebarInfo')), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('mods'),
                       data.get('difficulty'),
                       data.get('description'),
                       '0',
                       str(data.get('radar'))
                       ))
                       
            conn.commit()
        else:
            insertNew = 'INSERT INTO ' + tableType + ' (userID, songName, artist, pack, difficulty, itgScore, exScore, grade, length, stepartist, hash, scatter, life, worstWindow, date, mods, description, prevBestEx, radar) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            c.execute(insertNew,
                      (user_id, 
                       data.get('songName'), 
                       data.get('artist'), 
                       data.get('pack'), 
                       data.get('difficulty'), 
                       data.get('itgScore'), 
                       new_ex_score, 
                       data.get('grade'), 
                       data.get('length'), 
                       data.get('stepartist'), 
                       data.get('hash'), 
                       str(data.get('scatterplotData')), 
                       str(data.get('lifebarInfo')), 
                       data.get('worstWindow'), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('mods'),
                       data.get('description'),
                       '0',
                       str(data.get('radar'))
                       ))
            
            conn.commit()
    else:
        isPB = False

    # Check if submit_disabled is a date and time and if it is past that time and date
    if submit_disabled != 'enabled' and submit_disabled != 'disabled':
        try:
            disabled_until = datetime.strptime(submit_disabled, os.getenv('DATE_FORMAT'))
            if datetime.now() > disabled_until:
                submit_disabled = 'enabled'
                conn = sqlite3.connect(database)
                c = conn.cursor()
                c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', ('enabled', user_id))
                conn.commit()
        except ValueError:
            pass

    if isPB and submit_disabled == 'enabled':

        data['date'] = datetime.now().strftime(os.getenv('DATE_FORMAT'))
        data['prevBestEx'] = existing_ex_score
        if data.get('courseName'):
            color = discord.Color.purple()
        elif data.get('style') == 'double':
            color = discord.Color.blue()
        else:
            color = discord.Color.green()
        
        embed, file = embedded_score(data, user_id, "New (Server) Personal Best!", color)

        conn = sqlite3.connect(database)
        c = conn.cursor()
        
        channel_results = []
        for guild in client.guilds:
            if guild.get_member(int(user_id)):

                c.execute('SELECT channelID FROM CHANNELS WHERE serverID = ?', (str(guild.id),))
                channel_results.extend([channel[0] for channel in c.fetchall()])

        getTopScores = f'SELECT userID, exScore FROM {tableType} WHERE hash = ? ORDER BY exScore DESC'
        c.execute(getTopScores, (data.get('hash'),))
        top_scores = c.fetchall()


        embed.add_field(name="Top Server Scores", value="", inline=False)
        for channel_id in channel_results:
            channel = client.get_channel(int(channel_id))

            # Filter the top scores to include only members of the current guild
            top_selected_scores = [(uid, ex_score) for uid, ex_score in top_scores if channel.guild.get_member(int(uid))][:3]

            # Format the top 3 scores
            top_scores_message = ""
            for idx, (uid, ex_score) in enumerate(top_selected_scores, start=1):
                top_scores_message += f"{idx}. <@!{uid}>, EX Score: {ex_score}%\n"
            
            embed.set_field_at(index=-1, name="Top Server Scores", value=top_scores_message, inline=False)
            
            asyncio.run_coroutine_threadsafe(
                channel.send(embed=embed, file=discord.File('scatterplot.png', filename='scatterplot.png'), allowed_mentions=discord.AllowedMentions.none()),
                client.loop
            )

    conn.close()
    return jsonify({'status': 'Submission has been successfully inserted.'}), 200

# Global storage for pending chunks
pending_chunks = {}

@app.route('/chunk', methods=['POST'])
def receive_chunk():
    data = request.json
    api_key = data.get('api_key')
    
    # Check if the request contains an API key
    if not api_key:
        return jsonify({'status': 'Chunk is missing API Key.'}), 402
    
    # Check if the API key exists in the database
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('SELECT DiscordUser, submitDisabled FROM USERS WHERE APIKey = ?', (api_key,))
    result = c.fetchone()
    conn.close()
    if not result:
        return jsonify({'status': 'API Key has not been found in database.'}), 403
    
    # Extract chunk information
    hash_key = data.get('hash')
    chunk_type = data.get('chunkType')  # 'scatterplot' or 'lifebar'
    chunk_index = data.get('chunkIndex')
    total_chunks = data.get('totalChunks')
    chunk_data = data.get('data')
    
    if not all([hash_key, chunk_type, chunk_index, total_chunks, chunk_data]):
        return jsonify({'status': 'Chunk is missing required data.'}), 400
    
    # Initialize storage for this hash if needed
    if hash_key not in pending_chunks:
        pending_chunks[hash_key] = {
            'scatterplot': {},
            'lifebar': {}
        }
    
    # Store the chunk
    pending_chunks[hash_key][chunk_type][chunk_index] = chunk_data
    
    # Check if we have all chunks for this type
    received_chunks = len(pending_chunks[hash_key][chunk_type])
    logger.info(f"Received {chunk_type} chunk {chunk_index}/{total_chunks} for hash {hash_key}")
    
    return jsonify({'status': f'Chunk {chunk_index}/{total_chunks} received successfully.'}), 200

#================================================================================================
# Run Flask, run Discord bot
#================================================================================================
#================================================================================================

# Run Flask app in a separate thread
def run_flask():
    # Disable Flask's default logging to avoid conflicts
    import logging as flask_logging
    werkzeug_logger = flask_logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(flask_logging.ERROR)
    
    logger.info("Starting Flask server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)

threading.Thread(target=run_flask).start()

logger.info("Starting Discord bot...")
logger.info(f"Discord bot version: {version}")
bot_token = os.getenv('DISCORD_BOT_TOKEN')
client.run(bot_token)