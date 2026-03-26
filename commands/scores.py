import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View
import sqlite3

from utility.library import extract_data_from_row, extract_course_data_from_row
from utility.embeds import embedded_score, get_top_scores
from utility.config import database


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
        breakdown_command = interaction.client.tree.get_command("breakdown")
        if breakdown_command is None:
            await interaction.response.send_message("The breakdown command could not be found.", ephemeral=True)
            return

        class Namespace:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

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

        await breakdown_command._invoke_with_namespace(interaction, args)


class ScoresCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Recall score result
    #================================================================================================

    @app_commands.command(name="score", description="Recall score result from database.")
    async def score(self, interaction: discord.Interaction, song: str, isdouble: bool = False, ispump: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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
            if len(results) > 25:
                await interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
                return
            options = [
                discord.SelectOption(
                    label=f"{row[1]} - {row[2]} [{row[4]}]",
                    description=f" EX Score: {row[6]:.2f}%, Pack: {row[3]}",
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

            view = View()
            view.add_item(BreakdownButton(interaction, data['songName'], user, isdouble, ispump, failed, difficulty, pack, private))

            await interaction.followup.send(content=None, embed=embed, file=file, ephemeral=private, view=view)

    #================================================================================================
    # Recall course result
    #================================================================================================

    @app_commands.command(name="course", description="Recall course result from database.")
    async def course(self, interaction: discord.Interaction, name: str, isdouble: bool = False, user: discord.User = None, failed: bool = False, difficulty: int = 0, pack: str = "", private: bool = False):
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
            if len(results) > 25:
                await interaction.response.send_message("Too many results to pick from. Please be more specific.", ephemeral=True)
                return

            options = [
                discord.SelectOption(
                    label=f"{row[1]} - {row[2]} [{row[4]}]",
                    description=f" EX Score: {row[6]:.2f}%, Pack: {row[3]}",
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


async def setup(bot):
    await bot.add_cog(ScoresCog(bot))
