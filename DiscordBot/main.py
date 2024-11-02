import discord
from discord.ext import commands
import sqlite3
import secrets
from flask import Flask, request, jsonify
import threading
import asyncio
import matplotlib.pyplot as plt
import json
import os
from dotenv import load_dotenv

load_dotenv()

dev = False


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

def create_scatterplot_from_json(data, lifebar_info,  output_file='scatterplot.png'):
    # Extract x, y, and color values, excluding points with y=0 or y=200
    x_values = [point['x'] for point in data if point['y'] not in [0, 200]]
    y_values = [-point['y'] for point in data if point['y'] not in [0, 200]]
    colors = [point['color'] for point in data if point['y'] not in [0, 200]]
    
    # Extract lifebarInfo data points
    lifebar_x_values = [point['x'] for point in lifebar_info]
    lifebar_y_values = [-200+point['y'] for point in lifebar_info]


    # Create the scatter plot
    plt.figure(figsize=(10, 2))  # Size in inches (1000x200 pixels)

    # Add a horizontal line at y = -100
    plt.axhline(y=-100, color='white', linestyle='-', alpha=0.3, linewidth=2)

    # Add the step scatter points
    plt.scatter(x_values, y_values, c=colors, marker='s', s=5)
    

    # Add vertical lines for all points with y=200 (aka for all misses)
    for point in data:
        if point['y'] == 200:
            vertical_line_color = point['color']
            plt.axvline(x=point['x'], color=vertical_line_color, linestyle='-')
    
    # Plot lifebarInfo as a continuous line
    plt.plot(lifebar_x_values, lifebar_y_values, color='white', linestyle='-', linewidth=2)


    # Set the x-axis limits to 0 to 1000
    plt.xlim(0, 1000)
    # Set the y-axis limits to -210 to 10
    plt.ylim(-210, 10)
    plt.axis('off')
    plt.gca().set_facecolor('black')
    plt.gcf().patch.set_facecolor('black')
    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
    plt.close()

    # Display the plot
    #plt.show()

#================================================================================================

# Initialize Flask app
app = Flask(__name__) #TODO: Change this to your app name

#================================================================================================
# Initialize database
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS USERS
                 (DiscordUser TEXT PRIMARY KEY, APIKey TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS CHANNELS
                 (serverID TEXT PRIMARY KEY, channelID TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS SUBMISSIONS
                 (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty TEXT,
                  itgScore TEXT, exScore TEXT, grade TEXT, length TEXT, stepartist TEXT, hash TEXT)''')
    conn.commit()
    conn.close()

init_db()

#================================================================================================

intents = discord.Intents.default()
intents.members = True  # Enable the members intent
intents.message_content = True  # Enable the message content intent
client = commands.Bot(command_prefix='!', intents=intents)

#================================================================================================

@client.event
async def on_ready():
    print('Bot is ready.')

#================================================================================================

@client.command()
@commands.has_permissions(administrator=True)
async def usethischannel(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    server_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)

    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO CHANNELS (serverID, channelID) VALUES (?, ?)', (server_id, channel_id))
        conn.commit()
        conn.close()
        await ctx.send(f'This channel has been set as the results channel. You can change it at any time by running this command again in different channel.')
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@usethischannel.error
async def usethischannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have the required permissions to use this command.")
    else:
        await ctx.send("An error occurred while trying to run this command.")

#================================================================================================

client.remove_command('help')
@client.command()
async def help(ctx):
    help_message = """
    **Here are the available commands:**
    `!generate` - Generates a new API key and sends it to your DM.
    `!usethischannel` - Sets the current channel as the results channel (Admin only).
    """
    await ctx.send(help_message)

#================================================================================================

@client.command()
async def generate(ctx):
    user_id = str(ctx.author.id)
    
    # Generate a unique 20-character long key
    while True:
        api_key = secrets.token_urlsafe(20)[:20]
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM USERS WHERE APIKey = ?', (api_key,))
        if not c.fetchone():
            break
        conn.close()

    c.execute('INSERT OR REPLACE INTO USERS (DiscordUser, APIKey) VALUES (?, ?)', (user_id, api_key))
    conn.commit()
    conn.close()

    bot_url = os.getenv('BOT_URL')

    # Create the .ini file
    ini_content = f"BotURL={bot_url}\nAPIKey={api_key}\n"
    with open('DiscordLeaderboard.ini', 'w') as ini_file:
        ini_file.write(ini_content)

    # Send the .ini file as an attachment
    await ctx.author.send(
        f"""This is your new API key. DO NOT SHARE IT! If you had a key previously, the old one will no longer work.
        \nAPI Key: `{api_key}`
        \nCompleted ini file has been attached for your convenience. Please copy it into your profile folder.
        \nAlso note that your scores will be sent to all servers where both you and the bot are present.
        """,
        file=discord.File('DiscordLeaderboard.ini')
    )
    await ctx.send(f'Your key has been sent to your DM. Expect a message shortly.')

#================================================================================================

# Flask route to receive external data
@app.route('/send', methods=['POST'])
def send_message():
    data = request.json
    api_key = data.get('api_key')

    if not api_key:
        return jsonify({'status': 'Request is missing API Key.'}), 402

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT DiscordUser FROM USERS WHERE APIKey = ?', (api_key,))
    result = c.fetchone()
    conn.close()

    if not result:
        return jsonify({'status': 'API Key has not been found in database.'}), 403

    user_id = int(result[0])
    user = asyncio.run_coroutine_threadsafe(client.fetch_user(user_id), client.loop).result()

    if not user:
        return jsonify({'status': 'API Key exists, but you apparently not. Impressive'}), 404
    
    isPB = False
    # Check if the entry is already present via the hash and user ID
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT exScore FROM SUBMISSIONS WHERE hash = ? AND userID = ?', (data.get('hash'), user_id))
    existing_entry = c.fetchone()

    if existing_entry:
        # Compare the ex score
        existing_ex_score = float(existing_entry[0])
        new_ex_score = float(data.get('exScore'))

        if ((new_ex_score > existing_ex_score) and (data.get('grade') != 'Grade_Failed')) or dev == True:
            
            isPB = True
            # Overwrite the score and ex score with the new one
            c.execute('''UPDATE SUBMISSIONS
                         SET itgScore = ?, exScore = ?, grade = ?
                         WHERE hash = ? AND userID = ?''',
                      (data.get('itgScore'), new_ex_score, data.get('grade'), data.get('hash'), user_id))
            conn.commit()
    elif (data.get('grade') != 'Grade_Failed') or dev == True:
        isPB = True
        # Insert the new submission into the SUBMISSIONS table
        c.execute('''INSERT INTO SUBMISSIONS (userID, songName, artist, pack, difficulty, itgScore, exScore, grade, length, stepartist, hash)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, data.get('songName'), data.get('artist'), data.get('pack'), data.get('difficulty'), data.get('itgScore'), data.get('exScore'), data.get('grade'), data.get('length'), data.get('stepartist'), data.get('hash')))
        conn.commit()

    conn.close()


    if isPB:
        # Iterate through all guilds the bot is part of
        for guild in client.guilds:
            member = guild.get_member(user_id)
            if member:
                # Fetch the channel ID from the CHANNELS table for this guild
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT channelID FROM CHANNELS WHERE serverID = ?', (str(guild.id),))
                channel_result = c.fetchone()
                conn.close()

                if channel_result:
                    channel_id = int(channel_result[0])
                    channel = client.get_channel(channel_id)
                    if channel:

                        # Fetch the top 3 EX scores for the given hash that are also part of the same server
                        conn = sqlite3.connect('users.db')
                        c = conn.cursor()
                        c.execute('''SELECT userID, exScore 
                                     FROM SUBMISSIONS 
                                     WHERE hash = ? AND userID IN (SELECT DiscordUser FROM USERS WHERE DiscordUser IN (SELECT userID FROM SUBMISSIONS WHERE hash = ?)) 
                                     ORDER BY exScore DESC LIMIT 3''', (data.get('hash'), data.get('hash')))
                        top_scores = c.fetchall()
                        conn.close()

                        # Format the top 3 scores
                        top_scores_message = ""
                        for idx, (uid, ex_score) in enumerate(top_scores, start=1):
                            top_scores_message += f"{idx}. <@!{uid}>, EX Score: {ex_score}%\n"

                        grade = data.get('grade')
                        mapped_grade = grade_mapping.get(grade, grade)
                        embed = discord.Embed(title="New (Server) Personal Best!", color=discord.Color.green())
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
                        embed.add_field(name="Top Server Scores", value=top_scores_message, inline=False)

                        # Create the scatter plot and save it as an image
                        create_scatterplot_from_json(data.get('scatterplotData'), data.get('lifebarInfo'), output_file='scatterplot.png')

                        # Send the embed with the image attachment
                        file = discord.File('scatterplot.png', filename='scatterplot.png')
                        embed.set_image(url="attachment://scatterplot.png")
                        asyncio.run_coroutine_threadsafe(channel.send(embed=embed, file=file, allowed_mentions=discord.AllowedMentions.none()), client.loop)
                        #asyncio.run_coroutine_threadsafe(channel.send(message, allowed_mentions=discord.AllowedMentions.none()), client.loop)

    return jsonify({'status': 'success'}), 200



# Run Flask app in a separate thread
def run_flask():
    app.run(host='0.0.0.0', port=5000)

threading.Thread(target=run_flask).start()

bot_token = os.getenv('DISCORD_BOT_TOKEN')

client.run(bot_token)