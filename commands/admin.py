import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

from utility.library import extract_data_from_row, extract_course_data_from_row
from utility.embeds import embedded_score
from utility.config import database


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Help command
    #================================================================================================

    @app_commands.command(name="help", description="Shows the available commands.")
    async def help(self, Interaction: discord.Interaction):
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

    @app_commands.command(name="usethischannel", description="(Un)Set the current channel as the results channel. (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def usethischannel(self, Interaction: discord.Interaction):
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
        except Exception as e:
            await Interaction.response.send_message(f"An error occurred: {e}")

    @usethischannel.error
    async def usethischannel_error(self, Interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await Interaction.response.send_message("You do not have the required permissions to use this command.", ephemeral=True)
        else:
            await Interaction.response.send_message("An error occurred while trying to run this command.", ephemeral=True)

    #================================================================================================
    # ADMIN COMMAND: Delete score
    #================================================================================================

    @app_commands.command(name="deletescore", description="Delete a score from the database. (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def deletescore(self, Interaction: discord.Interaction, song: str, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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
            if len(results) > 25:
                await Interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
                return

            options = []
            for index, row in enumerate(results):
                if iscourse:
                    label = f"{row[1]} - {row[4]} [{row[5]}]"
                    description = f" EX Score: {row[8]:.2f}%, Pack: {row[2]}"
                else:
                    label = f"{row[1]} - {row[2]} [{row[4]}]"
                    description = f" EX Score: {row[6]:.2f}%, Pack: {row[3]}"
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


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
