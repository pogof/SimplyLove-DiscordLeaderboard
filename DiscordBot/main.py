from datetime import datetime, timedelta
import discord
from discord.ext import commands
from discord import Button, app_commands
from discord.utils import escape_mentions
import sqlite3
import secrets
from flask import Flask, request, jsonify
import threading
import asyncio
import numpy as np
import os
from dotenv import load_dotenv

from library import *
from plot import *

load_dotenv()


#================================================================================================
# Set up the Discord bot and Flask app
#================================================================================================

# Initialize Flask app
app = Flask(__name__) #TODO: Change this to your app name

# Initialize Discord bot
intents = discord.Intents.default()
intents.members = True  # Enable the members intent
intents.message_content = True  # Enable the message content intent
client = commands.Bot(command_prefix='!', intents=intents)

database = 'database.db'


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
@commands.has_permissions(administrator=True)
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
async def usethischannel_error(Interaction: discord.Interaction, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await Interaction.response.send_message("You do not have the required permissions to use this command.", ephemeral=True)
    else:
        await Interaction.response.send_message("An error occurred while trying to run this command.", ephemeral=True)


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
async def score(interaction: discord.Interaction, song: str, isdouble: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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
                data = extract_data_from_row(selected_row)

                if isdouble:
                    data['style'] = 'double'

                #print(data)
                embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
                embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)
                
                #TODO: It worked without deleting the message, at least for a little while :(
                #Need to figure something out lol
                await interaction.message.delete()
                await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=private)
    else:
        selected_row = results[0]
        data = extract_data_from_row(selected_row)

        if isdouble:
            data['style'] = 'double'
        embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

        await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

#================================================================================================
# Recall course result
#================================================================================================

@client.tree.command(name="course", description="Recall course result from database.")
async def course(interaction: discord.Interaction, song: str, isdouble: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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

    if song:
        query += " AND courseName LIKE ?"
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
                
                #TODO: It worked without deleting the message, at least for a little while :(
                #Need to figure something out lol
                await interaction.message.delete()
                await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=private)
    else:
        selected_row = results[0]
        data = extract_course_data_from_row(selected_row)
        if isdouble:
            data['style'] = 'double'
        embed, file = embedded_score(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        top_scores_message = get_top_scores(selected_row, interaction, 3, tableType)
        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

        await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

#================================================================================================
# compare two users
#================================================================================================

@client.tree.command(name="compare", description="Compare two users' scores. If only one user is provided, it will compare their scores with yours.")
@app_commands.describe(user_one="The first user to compare", user_two="The second user to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha, _diff")
async def compare(interaction: discord.Interaction, user_two: discord.User, user_one: discord.User = None, isdouble: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_ex", private: bool = True, pack: str = "", difficulty: int = 0, song_name: str = ""):
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
@app_commands.describe(user_two="User to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha, _diff")
async def unplayed(interaction: discord.Interaction, user_two: discord.User = None, isdouble: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_alpha", private: bool = True, pack: str = "", difficulty: int = 0):
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
async def breakdown(interaction: discord.Interaction, song: str, user: discord.User = None, isdouble: bool = False, iscourse: bool = False,  failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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
                data = extract_data_from_row(selected_row)
                embed, file = embedded_breakdown(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                
                #TODO: It worked without deleting the message, at least for a little while :(
                #Need to figure something out lol
                await interaction.message.delete()
                await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)

        view = discord.ui.View()
        view.add_item(ScoreSelect())
        await interaction.response.send_message("Multiple scores found. Please select one:", view=view, ephemeral=private)
    else:
        selected_row = results[0]
        data = extract_data_from_row(selected_row)
        embed, file = embedded_breakdown(data, str(user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)


#================================================================================================
# Database
#================================================================================================
#================================================================================================

# Initialize database
def init_db():
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS USERS
                 (DiscordUser TEXT PRIMARY KEY, APIKey TEXT, submitDisabled TEXT DEFAULT 'enabled')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS CHANNELS
                 (serverID TEXT, channelID TEXT, PRIMARY KEY (serverID, channelID))''')
    
    tablesNormal = ['SINGLES', 'SINGLESFAILS', 'DOUBLES', 'DOUBLESFAILS']
    tablesCourses = ['COURSESSINGLES', 'COURSESSINGLESFAILS', 'COURSESDOUBLES', 'COURSESDOUBLESFAILS']

    for table in tablesNormal:
        c.execute(f'''CREATE TABLE IF NOT EXISTS {table}
                 (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty TEXT,
                  itgScore TEXT, exScore TEXT, grade TEXT, length TEXT, stepartist TEXT, hash TEXT,
                  scatter JSON, life JSON, worstWindow TEXT, date TEXT, mods TEXT, description TEXT, prevBestEx TEXT)''')
    
    for table in tablesCourses:
        c.execute(f'''CREATE TABLE IF NOT EXISTS {table}
                 (userID TEXT, courseName TEXT, pack TEXT, entries TEXT, scripter TEXT, difficulty TEXT,
                  description TEXT, itgScore TEXT, exScore TEXT, grade TEXT, hash TEXT,
                  life JSON, date TEXT, mods TEXT, prevBestEx TEXT)''')



    conn.commit()
    conn.close()

init_db()


#================================================================================================
# Embedded score
#================================================================================================

def embedded_score(data, user_id, title="Users Best Score", color=discord.Color.dark_grey()):
    
    if data.get('prevBestEx') is None:
        data['prevBestEx'] = 0

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
        embed.add_field(name="Artist", value=data.get('artist'), inline=True)
        embed.add_field(name="Pack", value=data.get('pack'), inline=True)
        embed.add_field(name="Difficulty", value= style + data.get('difficulty'), inline=True)
        embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
        upscore = round(float(data.get('exScore')) - float(data.get('prevBestEx')), 2)
        embed.add_field(name="EX Score", value=f"{data.get('exScore')}% (+ {upscore}%)", inline=True)
        embed.add_field(name="Grade", value=mapped_grade, inline=True)
        embed.add_field(name="Length", value=data.get('length'), inline=True)
        embed.add_field(name="Stepartist", value=data.get('stepartist'), inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)

        # Create the scatter plot and save it as an image
        create_scatterplot_from_json(data.get('scatterplotData'), data.get('lifebarInfo'), output_file='scatterplot.png')

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
        embed.add_field(name="Difficulty", value= style + data.get('difficulty'), inline=True)
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
    

    if data.get('worstWindow') is None:
        embed = discord.Embed(title="Unable to create breakdown", color=color)
        embed.add_field(name="Error", value="No judgement window data found for this score. Old score. If you want breakdown get better score :P", inline=False)
        file = discord.File('lmao2.gif', filename='lmao2.gif')
        embed.set_image(url="attachment://lmao2.gif")
        return embed, file

    grade = data.get('grade')
    mapped_grade = grade_mapping.get(grade, grade)
    embed = discord.Embed(title=title, color=color)
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
                    Note that the numbers are rounded differently then in SL.""",
                    inline=True)

    create_distribution_from_json(data.get('scatterplotData'), data.get('worstWindow'), output_file='distribution.png')
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
    api_key = data.get('api_key')

    #print(data)

    # Check if the request contains an API key
    if not api_key:
        return jsonify({'status': 'Request is missing API Key.'}), 402

    # Check if the API key exists in the database and fetch DiscordUser and submitDisabled
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('SELECT DiscordUser, submitDisabled FROM USERS WHERE APIKey = ?', (api_key,))
    result = c.fetchone()
    conn.close()
    if not result:
        return jsonify({'status': 'API Key has not been found in database.'}), 403

    user_id, submit_disabled = result

    # Check if the request contains all required data
    required_keys_song = [
        'songName', 'artist', 'pack', 'length', 'stepartist', 'difficulty', 'description',
        'itgScore', 'exScore', 'grade', 'hash', 'scatterplotData', 'lifebarInfo',
        'worstWindow', 'style', 'modifiers'
    ]
    required_keys_course = [
        'courseName', 'pack', 'entries', 'hash', 'scripter', 'itgScore', 'description',
        'exScore', 'grade', 'lifebarInfo', 'style', 'modifiers', 'difficulty'
    ]

    if not (all(key in data for key in required_keys_song) or all(key in data for key in required_keys_course)):
        #print("Request is missing required data.")
        
        user = client.get_user(int(user_id))

        asyncio.run_coroutine_threadsafe(
        user.send(
            "Your score was not submitted. Your submission is missing some data. Please update your module to the latest version to ensure all required data is sent."
        ),
        client.loop
        )
        print("Something is missing")
        return jsonify({'status': 'Request is missing some data field(s).'}), 400
    
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
            updateExisting = 'UPDATE ' + tableType + ' SET itgScore = ?, exScore = ?, grade = ?, life = ?, date = ?, mods = ?, prevBestEx = ? WHERE hash = ? AND userID = ?'
            c.execute(updateExisting,
                      (data.get('itgScore'), 
                       new_ex_score,
                       data.get('grade'), 
                       str(data.get('lifebarInfo')), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('modifiers'),
                       existing_ex_score,
                       data.get('hash'),
                       user_id))
            conn.commit()

        else:
            updateExisting = 'UPDATE ' + tableType + ' SET itgScore = ?, exScore = ?, grade = ?, scatter = ?, life = ?, worstWindow = ?, date = ?, mods = ?, length = ?, prevBestEx = ? WHERE hash = ? AND userID = ?'
            c.execute(updateExisting, 
                      (data.get('itgScore'), 
                       new_ex_score,
                       data.get('grade'), 
                       str(data.get('scatterplotData')), 
                       str(data.get('lifebarInfo')), 
                       data.get('worstWindow'), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('modifiers'),
                       data.get('length'), # I was sending the wrong value lmao
                       existing_ex_score,
                       data.get('hash'),
                       user_id))
            conn.commit()


    elif new_ex_score > existing_ex_score:
        if data.get('courseName'):
            insertNew = 'INSERT INTO ' + tableType + ' (userID, courseName, pack, entries, scripter, itgScore, exScore, grade, hash, life, date, mods, difficulty, description, prevBestEx) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            c.execute(insertNew,
                      (user_id, 
                       data.get('courseName'), 
                       data.get('pack'), 
                       data.get('entries'), 
                       data.get('scripter'), 
                       data.get('itgScore'), 
                       new_ex_score, 
                       data.get('grade'), 
                       data.get('hash'), 
                       str(data.get('lifebarInfo')), 
                       datetime.now().strftime(os.getenv('DATE_FORMAT')),
                       data.get('modifiers'),
                       data.get('difficulty'),
                       data.get('description'),
                       '0'))
                       
            conn.commit()
        else:
            insertNew = 'INSERT INTO ' + tableType + ' (userID, songName, artist, pack, difficulty, itgScore, exScore, grade, length, stepartist, hash, scatter, life, worstWindow, date, mods, description, prevBestEx) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
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
                       data.get('modifiers'),
                       data.get('description'),
                       '0'))
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


        for guild in client.guilds:
            #print("Guilds: ", guild.name)

            c.execute('SELECT channelID FROM CHANNELS WHERE serverID = ?', (str(guild.id),))
            channel_results = c.fetchall()

            for channel_result in channel_results:
                channel_id = int(channel_result[0])
                channel = client.get_channel(channel_id)
                if channel:
                    #print(f"Sending message to channel: {channel.name} (ID: {channel_id}) in guild: {guild.name}")
                    
                    data['date'] = datetime.now().strftime(os.getenv('DATE_FORMAT'))
                    data['prevBestEx'] = existing_ex_score
                    
                    if data.get('courseName'):
                        color = discord.Color.purple()
                    elif data.get('style') == 'double':
                        color = discord.Color.blue()
                    else:
                        color = discord.Color.green()

                    embed, file = embedded_score(data, user_id, "New (Server) Personal Best!", color)
                    #embed.set_image(url="attachment://scatterplot.png")
                    
                    toPost = 'SELECT userID, exScore FROM ' + tableType + ' WHERE hash = ? AND userID IN (SELECT userID FROM ' + tableType + ' WHERE hash = ?) ORDER BY exScore DESC LIMIT 3'
                    c.execute(toPost, (data.get('hash'), data.get('hash')))
                    top_scores = c.fetchall()

                    # Filter the top scores to include only members of the current guild
                    top_scores = [(uid, ex_score) for uid, ex_score in top_scores if guild.get_member(int(uid))]

                    # Format the top 3 scores
                    top_scores_message = ""
                    for idx, (uid, ex_score) in enumerate(top_scores, start=1):
                        top_scores_message += f"{idx}. <@!{uid}>, EX Score: {ex_score}%\n"


                    
                    embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)


                    asyncio.run_coroutine_threadsafe(channel.send(embed=embed, file=file, allowed_mentions=discord.AllowedMentions.none()), client.loop)
                #else:
                    #print(f"Channel with ID {channel_id} not found in guild {guild.name}")


    conn.close()
    return jsonify({'status': 'success'}), 200


#================================================================================================
# Run Flask, run Discord bot
#================================================================================================
#================================================================================================

# Run Flask app in a separate thread
def run_flask():
    app.run(host='0.0.0.0', port=5000)
threading.Thread(target=run_flask).start()

bot_token = os.getenv('DISCORD_BOT_TOKEN')
client.run(bot_token)