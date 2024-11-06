import sqlite3

# This script is used to update the database schema to the latest version.
# Make sure you have a backup of the old database before running this script.
# Rename the file to database.db after you are done.



# Connect to the database
conn = sqlite3.connect('users.db')
c = conn.cursor()

# Alter USERS table to add submitDisabled column
c.execute('''ALTER TABLE USERS ADD COLUMN submitDisabled TEXT DEFAULT 'enabled' ''')

# Create a temporary table for CHANNELS with the new schema
c.execute('''CREATE TABLE IF NOT EXISTS CHANNELS_NEW
             (serverID TEXT, channelID TEXT, PRIMARY KEY (serverID, channelID))''')

# Copy data from old CHANNELS table to new CHANNELS table
c.execute('''INSERT INTO CHANNELS_NEW (serverID, channelID)
             SELECT serverID, channelID FROM CHANNELS''')

# Drop the old CHANNELS table and rename the new one
c.execute('''DROP TABLE CHANNELS''')
c.execute('''ALTER TABLE CHANNELS_NEW RENAME TO CHANNELS''')

# Alter SUBMISSIONS table to add new columns
c.execute('''ALTER TABLE SUBMISSIONS ADD COLUMN scatter JSON''')
c.execute('''ALTER TABLE SUBMISSIONS ADD COLUMN life JSON''')
c.execute('''ALTER TABLE SUBMISSIONS ADD COLUMN worstWindow TEXT''')

# Create the new FAILS table
c.execute('''CREATE TABLE IF NOT EXISTS FAILS
             (userID TEXT, songName TEXT, artist TEXT, pack TEXT, difficulty TEXT,
              itgScore TEXT, exScore TEXT, grade TEXT, length TEXT, stepartist TEXT, hash TEXT,
              scatter JSON, life JSON, worstWindow TEXT)''')

# Commit the changes and close the connection
conn.commit()
conn.close()