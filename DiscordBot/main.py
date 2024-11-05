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
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import json
import os
from dotenv import load_dotenv
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
    `/usethischannel - (Un)Sets the current channel as the results channel. You may use it in multiple channels. (Admin only).`
    """
    # Send the help message as an ephemeral message
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
        disabled_until = disabled_until.strftime('%Y-%m-%d %H:%M:%S')

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
async def score(interaction: discord.Interaction, song: str, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    if failed == True:
        query = "SELECT * FROM FAILS WHERE 1=1"
    else:
        query = "SELECT * FROM SUBMISSIONS WHERE 1=1"
    
    
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
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack = ?"
        params.append(str(pack))

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
                embed, file = embedded_score(data, str(interaction.user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                top_scores_message = get_top_scores(selected_row, interaction, 3)
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
        embed, file = embedded_score(data, str(interaction.user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        top_scores_message = get_top_scores(selected_row, interaction, 3)
        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)


        await interaction.response.send_message(content=None, embed=embed, file=file, ephemeral=private)


#================================================================================================
# compare two users
#================================================================================================

# @client.tree.command(name="compareall", description="Compare two users' scores. If only one user is provided, it will compare their scores with yours.")
# @app_commands.describe(user_one="The first user to compare", user_two="The second user to compare (optional)", private="Whether the response should be private")
# async def compareall(interaction: discord.Interaction, user_one: discord.User, user_two: discord.User = None, private: bool = False):
#     if interaction.guild is None:
#         await interaction.response.send_message("This command can only be used in a server.")
#         return
    
#     if user_two is None:
#         user_two = interaction.user

#     user_one_id = str(user_one.id)
#     user_two_id = str(user_two.id)

#     conn = sqlite3.connect(database)
#     c = conn.cursor()

#     # Find all hashes that have been played by both players
#     c.execute('''SELECT hash 
#                  FROM SUBMISSIONS 
#                  WHERE userID = ? 
#                  INTERSECT 
#                  SELECT hash 
#                  FROM SUBMISSIONS 
#                  WHERE userID = ?''', (user_one_id, user_two_id))
#     common_hashes = c.fetchall()

#     if not common_hashes:
#         await interaction.response.send_message("No common scores found between the two users.", ephemeral=private)
#         conn.close()
#         return

#     embed = discord.Embed(title="Score Comparison", color=discord.Color.blue())
#     #embed.add_field(name="", value=f"", inline=True)
#     embed.add_field(name="Player One", value=f"<@!{user_one_id}>", inline=True)
#     embed.add_field(name="Player Two", value=f"<@!{user_two_id}>", inline=True)
#     embed.add_field(name="Difference", value="", inline=True)

#     # Initialize a counter
#     score_count = 0
#     max_scores = 5

#     for hash_tuple in common_hashes:
#         hash_value = hash_tuple[0]

#         # Get scores for user one
#         c.execute('''SELECT songName, artist, pack, difficulty, exScore 
#                     FROM SUBMISSIONS 
#                     WHERE userID = ? AND hash = ?''', (user_one_id, hash_value))
#         user_one_score = c.fetchone()

#         # Get scores for user two
#         c.execute('''SELECT exScore 
#                     FROM SUBMISSIONS 
#                     WHERE userID = ? AND hash = ?''', (user_two_id, hash_value))
#         user_two_score = c.fetchone()

#         if user_one_score and user_two_score:
#             song_name, artist, pack, difficulty, user_one_ex_score = user_one_score
#             user_two_ex_score = user_two_score[0]

#             embed.add_field(
#                 name=f"{song_name} - {artist} [{difficulty}]",
#                 value=f"Pack: {pack}",
#                 inline=False
#             )
#             embed.add_field(name="", value=f'{user_one_ex_score}%', inline=True)
#             embed.add_field(name="", value=f'{user_two_ex_score}%', inline=True)
#             difference = round(float(user_one_ex_score) - float(user_two_ex_score), 2)
#             embed.add_field(name="", value=f'{difference}%', inline=True)

#             # Increment the counter
#             score_count += 1

#             # Check if the maximum number of scores has been reached
#             if score_count >= max_scores:
#                 break

#     # If there are more scores, add a button to show the next 10 scores
#     if score_count >= max_scores:
#         button = discord.ui.Button(label="Show more", style=discord.ButtonStyle.primary)

#         async def button_callback(interaction):
#             # Logic to show the next 10 scores
#             pass

#         button.callback = button_callback
#         view = discord.ui.View()
#         view.add_item(button)
#         await interaction.response.send_message(embed=embed, view=view, ephemeral=private)
#     else:
#         await interaction.response.send_message(embed=embed, ephemeral=private)

#     conn.close()


#================================================================================================
# Breakdown of score
#================================================================================================

@client.tree.command(name="breakdown", description="More in depth breakdown of a score.")
async def breakdown(interaction: discord.Interaction, song: str, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.")
        return
    
    if failed == True:
        query = "SELECT * FROM FAILS WHERE 1=1"
    else:
        query = "SELECT * FROM SUBMISSIONS WHERE 1=1"
    
    
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
    if difficulty:
        query += " AND difficulty = ?"
        params.append(str(difficulty))
    if pack:
        query += " AND pack = ?"
        params.append(str(pack))

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
                embed, file = embedded_breakdown(data, str(interaction.user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())
                #top_scores_message = get_top_scores(selected_row, interaction, 3)
                #embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)
                
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
        embed, file = embedded_breakdown(data, str(interaction.user.id), "Selected Score", discord.Color.red() if failed else discord.Color.dark_grey())

        judgements = {
            'fa_p': 0,
            'e_fa': 0,
            'l_fa': 0,
            'e_ex': 0,
            'l_ex': 0,
            'e_gd': 0,
            'l_gd': 0,
            'e_de': 0,
            'l_de': 0,
            'e_wo': 0,
            'l_wo': 0,
            'miss': 0
        }
        
        y_values = [100-point['y'] for point in data['scatterplotData']]
        
        i = 0
        for y in y_values:
            if  -15/2 <= y <= 15/2:
                judgements['fa_p'] += 1
            elif -23/2 <= y < -15/2:
                judgements['e_fa'] += 1
            elif 15/2 > y >= 23/2:
                judgements['l_fa'] += 1
            elif -44.5/2 <= y < -23/2:
                judgements['e_ex'] += 1
            elif 44.5/2 > y >= 23/2:
                judgements['l_ex'] += 1
            elif -103.5/2 <= y < -44.5/2:
                judgements['e_gd'] += 1
            elif 103.5/2 > y >= 44.5/2:
                judgements['l_gd'] += 1
            elif -136.5/2 <= y < -103.5/2:
                judgements['e_de'] += 1
            elif 136.5/2 > y >= 103.5/2:
                judgements['l_de'] += 1
            elif -181.5/2 <= y < -136.5/2:
                judgements['e_wo'] += 1
            elif 181.5/2 > y >= 136.5/2:
                judgements['l_wo'] += 1
            elif y == 100:
                judgements['miss'] += 1
            i += 1

        judgements['miss'] = int(judgements['miss'] / 2)

        print(i-judgements['miss'])


        embed.add_field(name="Judgements", value=f"FA+: {judgements['fa_p']}\nFantastic: {judgements['e_fa']}/{judgements['l_fa']}\nExcellent: {judgements['e_ex']}/{judgements['l_ex']}\nGreat: {judgements['e_gd']}/{judgements['l_gd']}\nDecent: {judgements['e_de']}/{judgements['l_de']}\nWay Off: {judgements['e_wo']}/{judgements['l_wo']}\nMiss: {judgements['miss']}", inline=False)

        #top_scores_message = get_top_scores(selected_row, interaction, 3)
        #embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)


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
    
    c.execute('''CREATE TABLE IF NOT EXISTS SUBMISSIONS
                 (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty TEXT,
                  itgScore TEXT, exScore TEXT, grade TEXT, length TEXT, stepartist TEXT, hash TEXT,
                  scatter JSON, life JSON)''')

    c.execute('''CREATE TABLE IF NOT EXISTS FAILS
                 (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty TEXT,
                  itgScore TEXT, exScore TEXT, grade TEXT, length TEXT, stepartist TEXT, hash TEXT,
                  scatter TEXT, life TEXT)''')
    conn.commit()
    conn.close()

init_db()


#================================================================================================
# Graph generation
#================================================================================================
# Scatter plot generation
#================================================================================================

def create_scatterplot_from_json(data, lifebar_info,  output_file='scatterplot.png'):


    # Extract x, y, and color values, excluding points with y=0 or y=200 (misses)
    x_values = [point['x'] for point in data if point['y'] not in [0, 200]]
    y_values = [-point['y'] for point in data if point['y'] not in [0, 200]]
    colors = [point['color'] for point in data if point['y'] not in [0, 200]]
    
    # Extract lifebarInfo data points
    lifebar_x_values = [point['x'] for point in lifebar_info]
    lifebar_y_values = [-200+point['y'] for point in lifebar_info]


    # Set plot size
    plt.figure(figsize=(10, 2))  # Size in inches (1000x200 pixels)

    # Add a horizontal line at y = -100 (center of judgement)
    plt.axhline(y=-100, color='white', linestyle='-', alpha=0.3, linewidth=2)

    # Add the step scatter points
    plt.scatter(x_values, y_values, c=colors, marker='s', s=5)
    
    # Add vertical lines for all points with y=200 (misses)
    for point in data:
        if point['y'] == 200:
            vertical_line_color = point['color']
            plt.axvline(x=point['x'], color=vertical_line_color, linestyle='-')
    
    # Plot lifebarInfo as a continuous line
    plt.plot(lifebar_x_values, lifebar_y_values, color='white', linestyle='-', linewidth=2)

    # Set the x-axis limits to 0 to 1000
    plt.xlim(0, 1000)
    # Set the y-axis limits to -210 to 10
    plt.ylim(-210, 10) #TODO: Zoom based on worst judgement (excluding misses)
    plt.axis('off')
    plt.gca().set_facecolor('black')
    plt.gcf().patch.set_facecolor('black')
    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
    plt.close()


#================================================================================================
# Distribution generation
#================================================================================================

def create_distribution_from_json(data, lifebar_info,  output_file='distribution.png'):


    # Assuming x_values and y_values are already defined
    y_values = [100-point['y'] for point in data if point['y'] not in [0, 200]]



    # Create a figure
    plt.figure(figsize=(10, 6))
    kde = sns.kdeplot(y_values, color='black', alpha=0, bw_adjust=0.12)

    # Get the x and y data from the KDE plot
    x_data = kde.get_lines()[0].get_xdata()
    y_data = kde.get_lines()[0].get_ydata()

    # Ensure x_data and y_data are single lists
    if isinstance(x_data[0], np.ndarray):
        x_data = np.concatenate(x_data)
    if isinstance(y_data[0], np.ndarray):
        y_data = np.concatenate(y_data)

    plt.axvline(x=0, color='white', alpha=0.5 , linestyle='-', linewidth=3)
    
    # Fill the area under the curve with different colors
    plt.fill_between(x_data, y_data, where=((x_data >= -181.5/2) & (x_data <= 181.5/2)), color='#c9855e')
    plt.fill_between(x_data, y_data, where=((x_data >= -136.5/2) & (x_data <= 136.5/2)), color='#b45cff')
    plt.fill_between(x_data, y_data, where=((x_data >= -103.5/2) & (x_data <= 103.5/2)), color='#66c955')
    plt.fill_between(x_data, y_data, where=((x_data >= -44.5/2) & (x_data <= 44.5/2)), color='#e29c18')
    plt.fill_between(x_data, y_data, where=((x_data >= -23/2) & (x_data <= 23/2)), color='#ffffff')
    plt.fill_between(x_data, y_data, where=((x_data >= -15/2) & (x_data <= 15/2)), color='#21cce8')




    # Set the x-axis
    plt.xlim(-181.5/2, 181.5/2)
    #plt.ylim(0.0001, 0.07)

    plt.axis('off')
    plt.gca().set_facecolor('black')
    plt.gcf().patch.set_facecolor('black')
    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
    plt.close()


#================================================================================================
# Grade mapping
#================================================================================================
#================================================================================================

grade_mapping = {
    'Grade_Tier00': '⭐⭐⭐⭐⭐',
    'Grade_Tier01': '⭐⭐⭐⭐',
    'Grade_Tier02': '⭐⭐⭐',
    'Grade_Tier03': '⭐⭐',
    'Grade_Tier04': '⭐',
    'Grade_Tier05': 'S+',
    'Grade_Tier06': 'S',
    'Grade_Tier07': 'S-',
    'Grade_Tier08': 'A+',
    'Grade_Tier09': 'A',
    'Grade_Tier10': 'A-',
    'Grade_Tier11': 'B+',
    'Grade_Tier12': 'B',
    'Grade_Tier13': 'B-',
    'Grade_Tier14': 'C+',
    'Grade_Tier15': 'C',
    'Grade_Tier16': 'C-',
    'Grade_Tier17': 'D',
    'Grade_Tier99': 'Q?'
}


#================================================================================================
# Data from database to dict
#================================================================================================

def extract_data_from_row(row):
    return {
        'songName': row[1],
        'artist': row[2],
        'pack': row[3],
        'difficulty': row[4],
        'itgScore': row[5],
        'exScore': row[6],
        'grade': row[7],
        'length': row[8],
        'stepartist': row[9],
        'scatterplotData': json.loads(row[11].replace("'", '"') if row[11] else '[]'),
        'lifebarInfo': json.loads(row[12].replace("'", '"') if row[12] else '[]')
    }


#================================================================================================
# Embedded score
#================================================================================================

def embedded_score(data, user_id, title="Users Best Score", color=discord.Color.dark_grey()):

    grade = data.get('grade')
    mapped_grade = grade_mapping.get(grade, grade)
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="User", value=f"<@!{user_id}>", inline=False)
    embed.add_field(name="Song", value=data.get('songName'), inline=True)
    embed.add_field(name="Artist", value=data.get('artist'), inline=True)
    embed.add_field(name="Pack", value=data.get('pack'), inline=True)
    embed.add_field(name="Difficulty", value=data.get('difficulty'), inline=True)
    embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
    embed.add_field(name="EX Score", value=f"{data.get('exScore')}%", inline=True)
    embed.add_field(name="Grade", value=mapped_grade, inline=True)
    embed.add_field(name="Length", value=data.get('length'), inline=True)
    embed.add_field(name="Stepartist", value=data.get('stepartist'), inline=True)

    # Create the scatter plot and save it as an image
    create_scatterplot_from_json(data.get('scatterplotData'), data.get('lifebarInfo'), output_file='scatterplot.png')

    # Send the embed with the image attachment
    file = discord.File('scatterplot.png', filename='scatterplot.png')
    embed.set_image(url="attachment://scatterplot.png")

    return embed, file


#================================================================================================
# Embedded Breakdown
#================================================================================================

def embedded_breakdown(data, user_id, title="Score Breakdown", color=discord.Color.dark_grey()):
    
    grade = data.get('grade')
    mapped_grade = grade_mapping.get(grade, grade)
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="User", value=f"<@!{user_id}>", inline=False)
    embed.add_field(name="Song", value=data.get('songName'), inline=True)
    embed.add_field(name="Pack", value=data.get('pack'), inline=True)
    embed.add_field(name="EX Score", value=f"{data.get('exScore')}%", inline=True)

    create_distribution_from_json(data.get('scatterplotData'), data.get('lifebarInfo'), output_file='distribution.png')
    # Send the embed with the image attachment
    file = discord.File('distribution.png', filename='distribution.png')
    embed.set_image(url="attachment://distribution.png")

    return embed, file

#================================================================================================
# Get top 3 scores
#================================================================================================

def get_top_scores(selected_row, interaction, num):
    # Fetch the top num EX scores for the given hash that are also part of the same server
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('''SELECT userID, exScore 
                    FROM SUBMISSIONS 
                    WHERE hash = ? AND userID IN (SELECT userID FROM SUBMISSIONS WHERE hash = ?) 
                    ORDER BY exScore DESC LIMIT ?''', (selected_row[10], selected_row[10], num))
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
    
    isPB = False
    # Check if the entry is already present via the hash and user ID
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute('SELECT exScore FROM SUBMISSIONS WHERE hash = ? AND userID = ?', (data.get('hash'), user_id))
    existing_entry = c.fetchone()

    c.execute('SELECT exScore FROM FAILS WHERE hash = ? AND userID = ?', (data.get('hash'), user_id))
    existing_fails_entry = c.fetchone()

    # Compare the ex score
    existing_ex_score = float(existing_entry[0]) if existing_entry else 0
    existing_fails_ex_score = float(existing_fails_entry[0]) if existing_fails_entry else 0
    new_ex_score = float(data.get('exScore'))
    
    if existing_entry and new_ex_score > existing_ex_score and data.get('grade') != 'Grade_Failed':

        isPB = True
        c.execute('''UPDATE SUBMISSIONS
                        SET itgScore = ?, exScore = ?, grade = ?, scatter = ?, life = ?
                        WHERE hash = ? AND userID = ?''',
                    (data.get('itgScore'), new_ex_score, data.get('grade'), str(data.get('scatterplotData')), str(data.get('lifebarInfo')), data.get('hash'), user_id))
        conn.commit()

    elif new_ex_score > existing_ex_score and data.get('grade') != 'Grade_Failed':

        isPB = True
        
        c.execute('''INSERT INTO SUBMISSIONS (userID, songName, artist, pack, difficulty, itgScore, exScore, grade, length, stepartist, hash, scatter, life)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, data.get('songName'), data.get('artist'), data.get('pack'), data.get('difficulty'), data.get('itgScore'), data.get('exScore'), data.get('grade'), data.get('length'), data.get('stepartist'), data.get('hash'), str(data.get('scatterplotData')), str(data.get('lifebarInfo'))))
        conn.commit()
    
    elif existing_fails_entry and data.get('grade') == 'Grade_Failed' and new_ex_score > existing_fails_ex_score:

        c.execute('''UPDATE FAILS
                    SET itgScore = ?, exScore = ?, grade = ?, scatter = ?, life = ?
                    WHERE hash = ? AND userID = ?''',
                (data.get('itgScore'), new_ex_score, data.get('grade'), str(data.get('scatterplotData')), str(data.get('lifebarInfo')), data.get('hash'), user_id))
        conn.commit()
    
    elif (not existing_fails_entry) and data.get('grade') == 'Grade_Failed':

        c.execute('''INSERT INTO FAILS (userID, songName, artist, pack,
                  difficulty, itgScore, exScore, grade, length, stepartist, hash, scatter, life)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, data.get('songName'), data.get('artist'), data.get('pack'),
                  data.get('difficulty'), data.get('itgScore'), data.get('exScore'), data.get('grade'),
                  data.get('length'), data.get('stepartist'), data.get('hash'),
                  str(data.get('scatterplotData')), str(data.get('lifebarInfo'))))
        conn.commit()


    # Check if submit_disabled is a date and time and if it is past that time and date
    if submit_disabled != 'enabled' and submit_disabled != 'disabled':
        try:
            disabled_until = datetime.strptime(submit_disabled, '%Y-%m-%d %H:%M:%S')
            if datetime.now() > disabled_until:
                submit_disabled = 'enabled'
                conn = sqlite3.connect(database)
                c = conn.cursor()
                c.execute('UPDATE USERS SET submitDisabled = ? WHERE DiscordUser = ?', ('enabled', user_id))
                conn.commit()
        except ValueError:
            pass


    if isPB and submit_disabled == 'enabled':
        embed, file = embedded_score(data, user_id, "New (Server) Personal Best!", discord.Color.green())
        for guild in client.guilds:
            member = guild.get_member(int(user_id))

            if member:
                c.execute('SELECT channelID FROM CHANNELS WHERE serverID = ?', (str(guild.id),))
                channel_result = c.fetchone()

                if channel_result:
                    channel_id = int(channel_result[0])
                    channel = client.get_channel(channel_id)

                    if channel:
                        
                        # Fetch the top 3 EX scores for the given hash that are also part of the same server
                        c.execute('''SELECT userID, exScore 
                                FROM SUBMISSIONS 
                                WHERE hash = ? AND userID IN (SELECT userID FROM SUBMISSIONS WHERE hash = ?) 
                                ORDER BY exScore DESC LIMIT 3''', (data.get('hash'), data.get('hash')))
                        top_scores = c.fetchall()

                        # Filter the top scores to include only members of the current guild
                        top_scores = [(uid, ex_score) for uid, ex_score in top_scores if guild.get_member(int(uid))]

                        # Format the top 3 scores
                        top_scores_message = ""
                        for idx, (uid, ex_score) in enumerate(top_scores, start=1):
                            top_scores_message += f"{idx}. <@!{uid}>, EX Score: {ex_score}%\n"

                        
                        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)
                                
                        asyncio.run_coroutine_threadsafe(channel.send(embed=embed, file=file, allowed_mentions=discord.AllowedMentions.none()), client.loop)


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