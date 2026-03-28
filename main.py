from datetime import datetime, timedelta
import discord
from discord.ext import commands
import sqlite3
from flask import Flask, request, jsonify
import threading
import asyncio
import os
import sys
import logging
import time
from dotenv import load_dotenv
load_dotenv()

from commands.api_keys import file_pack, registration_message
from utility.library import *
from utility.plot import *
from utility.config import database
from utility.embeds import embedded_score
from utility.version import APP_VERSION


version = APP_VERSION


#================================================================================================
# Initial setup
#================================================================================================
# Set up Logging
#================================================================================================

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


#================================================================================================
# Sync commands on bot startup
#================================================================================================

class LeaderboardBot(commands.Bot):
    async def setup_hook(self):
        extensions = [
            'commands.admin',
            'commands.api_keys',
            'commands.scores',
            'commands.compare',
            'commands.unplayed',
            'commands.breakdown',
        ]
        for ext in extensions:
            await self.load_extension(ext)

client = LeaderboardBot(command_prefix='!', intents=intents)

@client.event
async def on_ready():
    print('Bot is ready.')
    try:
        sync = await client.tree.sync()
        print(f"Synced {len(sync)} commands.")
    except Exception as e:
        print(f"An error occurred while syncing commands: {e}")

    await send_update_notification()

#================================================================================================
# Database
#================================================================================================
#================================================================================================

# Initialize database
def init_db():
    conn = sqlite3.connect(database)
    c = conn.cursor()

    c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'CONFIG'")
    config_table_exists = c.fetchone() is not None

    c.execute('''CREATE TABLE IF NOT EXISTS CONFIG
                    (version TEXT PRIMARY KEY,
              updateNotificationSent BOOL DEFAULT 0)''')

    if not config_table_exists:
        c.execute('INSERT INTO CONFIG (version) VALUES (?)', (version,))

    c.execute('''CREATE TABLE IF NOT EXISTS USERS
                 (DiscordUser TEXT PRIMARY KEY, APIKey TEXT, submitDisabled TEXT DEFAULT 'enabled', updateNotification BOOL DEFAULT 1)''')
    
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
# Database cleanup tasks on startup
# This stuff here is cleaning up shit from the previous version(s).
#================================================================================================

# Remove unnecessary precision from scatterplot and lifebar data
# Add updateNotification column to USERS table if it doesn't exist
def update_140():
    conn = sqlite3.connect(database)
    c = conn.cursor()

    c.execute(f"ALTER TABLE USERS ADD COLUMN updateNotification BOOL DEFAULT 1")
    c.execute(f"ALTER TABLE CONFIG ADD COLUMN updateNotificationSent BOOL DEFAULT 0")
    conn.commit()
    
    c.execute('SELECT version FROM CONFIG')
    row = c.fetchone()
    conn.close()
    
    if not row:
        from utility.squash_db_precision import backup_and_squash

        logger.info(f"Updating database version to {version}")
        logger.info(f"Squashing and compacting database. This might take a while...")
        backup_and_squash(database, logger, decimal_places=3, compact=True)


conn = sqlite3.connect(database)
c = conn.cursor()
c.execute('SELECT version FROM CONFIG')
row = c.fetchone()
if not row or row[0] is None:
    update_140()
conn.close()

# Set version in the database to match the current version of the bot. 
# This is used to determine if future updates need to run any cleanup 
# tasks and what order to apply them in.
conn = sqlite3.connect(database)
c = conn.cursor()
c.execute('SELECT version FROM CONFIG')
row = c.fetchone()
if not row or row[0] != version:
    c.execute('DELETE FROM CONFIG')
    c.execute('INSERT INTO CONFIG (version, updateNotificationSent) VALUES (?, ?)', (version, 0))
    conn.commit()
    logger.info(f"Database has been updated to version {version}")
conn.close()


async def send_update_notification():
    bot_url = os.getenv('BOT_URL')
    if not bot_url:
        logger.warning("Skipping update notifications because BOT_URL is not configured.")
        return

    conn = sqlite3.connect(database)
    c = conn.cursor()

    c.execute('SELECT updateNotificationSent FROM CONFIG')
    notif_sent = c.fetchone()
    conn.close()

    if notif_sent and not notif_sent[0]:
        conn = sqlite3.connect(database)
        c = conn.cursor()

        c.execute('UPDATE CONFIG SET updateNotificationSent = 1 WHERE version = ?', (version,))
        conn.commit()

        c.execute("SELECT DiscordUser, APIKey FROM USERS WHERE APIKey IS NOT NULL AND APIKey != '' AND updateNotification = 1")
        users_to_notify = c.fetchall()
        conn.close()

        for user_id, api_key in users_to_notify:
            try:
                user = client.get_user(int(user_id)) or await client.fetch_user(int(user_id))
                pack_file = file_pack(api_key, bot_url)
                await user.send(
                    f"The bot has been updated to version `{version}`. Please replace your local files with the attached package.\n{registration_message}",
                    file=pack_file
                )
            except discord.Forbidden:
                logger.warning(f"Could not send update notification to user {user_id}: DMs are disabled.")
            except discord.HTTPException as exc:
                logger.warning(f"Could not send update notification to user {user_id}: {exc}")
            except Exception:
                logger.exception(f"Unexpected error while sending update notification to user {user_id}")
        logger.info(f"Sent update notifications to {len(users_to_notify)} users.")


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
        
        # Reconstruct data using thread-safe chunk manager
        scatter_data, lifebar_data, error = chunk_manager.get_and_remove_chunks(
            user_id, hash_key, scatter_chunks, lifebar_chunks
        )
        
        if error:
            logger.error(f"Chunk reconstruction failed: {error}")
            return jsonify({'status': f'Chunk reconstruction failed: {error}'}), 400
        
        # Add reconstructed data to the main data object
        if scatter_data is not None:
            data['scatterplotData'] = scatter_data
            logger.info(f"Reconstructed scatterplot data: {len(scatter_data)} points")
        
        if lifebar_data is not None:
            data['lifebarInfo'] = lifebar_data
            logger.info(f"Reconstructed lifebar data: {len(lifebar_data)} points")

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
    
    # Reduce precision of scatter plot and lifebar data to 3 decimal places before storing
    data['scatterplotData'] = reduce_precision(data.get('scatterplotData'), 3)
    data['lifebarInfo'] = reduce_precision(data.get('lifebarInfo'), 3)

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
                top_scores_message += f"{idx}. <@!{uid}>, EX Score: {float(ex_score):.2f}%\n"
            
            embed.set_field_at(index=-1, name="Top Server Scores", value=top_scores_message, inline=False)
            channel_file = clone_discord_file(file)
            
            asyncio.run_coroutine_threadsafe(
                channel.send(embed=embed, file=channel_file, allowed_mentions=discord.AllowedMentions.none()), client.loop
            )

    conn.close()
    return jsonify({'status': 'Submission has been successfully inserted.'}), 200

# Global storage for pending chunks with threading support
from collections import defaultdict

class ChunkManager:
    def __init__(self):
        self.chunks = {}
        self.lock = threading.RLock()
        self.chunk_timestamps = {}
        self.cleanup_interval = 300  # 5 minutes timeout
        
    def store_chunk(self, user_id, hash_key, chunk_type, chunk_index, chunk_data, total_chunks):
        """Store a chunk with thread safety"""
        composite_key = f"{user_id}:{hash_key}"
        
        with self.lock:
            current_time = time.time()
            
            # Initialize storage for this user+hash combination
            if composite_key not in self.chunks:
                self.chunks[composite_key] = {
                    'scatterplot': {},
                    'lifebar': {},
                    'total_chunks': {'scatterplot': 0, 'lifebar': 0}
                }
                self.chunk_timestamps[composite_key] = current_time
            
            # Update timestamp
            self.chunk_timestamps[composite_key] = current_time
            
            # Store total chunks info
            self.chunks[composite_key]['total_chunks'][chunk_type] = total_chunks
            
            # Store the chunk
            self.chunks[composite_key][chunk_type][chunk_index] = chunk_data
            
            received_count = len(self.chunks[composite_key][chunk_type])
            return received_count, total_chunks
    
    def get_and_remove_chunks(self, user_id, hash_key, scatter_chunks, lifebar_chunks):
        """Get complete chunks and remove from storage"""
        composite_key = f"{user_id}:{hash_key}"
        
        with self.lock:
            if composite_key not in self.chunks:
                return None, None, "No chunks found"
            
            chunk_data = self.chunks[composite_key]
            
            # Check if we have all required chunks
            scatter_data = []
            lifebar_data = []
            
            if scatter_chunks > 0:
                if len(chunk_data['scatterplot']) != scatter_chunks:
                    missing = [i for i in range(1, scatter_chunks + 1) 
                             if i not in chunk_data['scatterplot']]
                    return None, None, f"Missing scatterplot chunks: {missing}"
                
                # Reconstruct scatterplot data in order
                for i in range(1, scatter_chunks + 1):
                    scatter_data.extend(chunk_data['scatterplot'][i])
            
            if lifebar_chunks > 0:
                if len(chunk_data['lifebar']) != lifebar_chunks:
                    missing = [i for i in range(1, lifebar_chunks + 1) 
                             if i not in chunk_data['lifebar']]
                    return None, None, f"Missing lifebar chunks: {missing}"
                
                # Reconstruct lifebar data in order
                for i in range(1, lifebar_chunks + 1):
                    lifebar_data.extend(chunk_data['lifebar'][i])
            
            # Clean up
            del self.chunks[composite_key]
            del self.chunk_timestamps[composite_key]
            
            return scatter_data if scatter_chunks > 0 else None, \
                   lifebar_data if lifebar_chunks > 0 else None, \
                   None
    
    def cleanup_expired_chunks(self):
        """Remove chunks older than cleanup_interval"""
        current_time = time.time()
        
        with self.lock:
            expired_keys = [
                key for key, timestamp in self.chunk_timestamps.items()
                if current_time - timestamp > self.cleanup_interval
            ]
            
            for key in expired_keys:
                if key in self.chunks:
                    del self.chunks[key]
                if key in self.chunk_timestamps:
                    del self.chunk_timestamps[key]
                    
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired chunk sets")

# Global chunk manager
chunk_manager = ChunkManager()

# Start cleanup thread
def chunk_cleanup_worker():
    while True:
        time.sleep(60)  # Run cleanup every minute
        chunk_manager.cleanup_expired_chunks()

cleanup_thread = threading.Thread(target=chunk_cleanup_worker, daemon=True)
cleanup_thread.start()

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
    
    user_id, _ = result
    
    # Extract chunk information
    hash_key = data.get('hash')
    chunk_type = data.get('chunkType')  # 'scatterplot' or 'lifebar'
    chunk_index = data.get('chunkIndex')
    total_chunks = data.get('totalChunks')
    chunk_data = data.get('data')
    
    if not all([hash_key, chunk_type, chunk_index, total_chunks, chunk_data]):
        return jsonify({'status': 'Chunk is missing required data.'}), 400
    
    # Store chunk using thread-safe manager
    received_count, total_count = chunk_manager.store_chunk(
        user_id, hash_key, chunk_type, chunk_index, chunk_data, total_chunks
    )
    
    logger.info(f"Received {chunk_type} chunk {chunk_index}/{total_chunks} for user {user_id}, hash {hash_key}")
    
    return jsonify({'status': f'Chunk {chunk_index}/{total_chunks} received successfully. ({received_count}/{total_count} {chunk_type} chunks received)'}), 200

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