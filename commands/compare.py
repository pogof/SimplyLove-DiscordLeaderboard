import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

from utility.config import database


async def compare_logic(interaction: discord.Interaction, page: int, order, private, results, user_one_id, user_two_id):

    order_mapping = {
        "asc_ex": "Ascending EX Score",
        "desc_ex": "Descending EX Score",
        "asc_alpha": "Ascending Alphabetical Order",
        "desc_alpha": "Descending Alphabetical Order",
        "asc_diff": "Ascending Difference",
        "desc_diff": "Descending Difference"
    }

    embed = discord.Embed(title=f"Score Comparison - Order: {order_mapping[order]}", color=discord.Color.blue())
    embed.set_footer(text=f"Page {page}")
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


class CompareCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Compare two users
    #================================================================================================

    @app_commands.command(name="compare", description="Compare two users' scores. If only one user is provided, it will compare their scores with yours.")
    @app_commands.describe(user_one="The first user to compare", user_two="The second user to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha, _diff")
    async def compare(self, interaction: discord.Interaction, user_two: discord.User, user_one: discord.User = None, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_ex", private: bool = True, pack: str = "", difficulty: int = 0, song_name: str = ""):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.")
            return
        if user_one is None:
            user_one = interaction.user

        user_one_id = str(user_one.id)
        user_two_id = str(user_two.id)

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
            order_by = "s1.exScore DESC"

        tableType = ''
        if iscourse:
            tableType = 'COURSES'
        if isdouble:
            tableType = 'DOUBLES'
        else:
            tableType = 'SINGLES'
        if ispump:
            tableType += '_PUMP'

        query = ('SELECT s1.songName, s1.artist, s1.pack, s1.difficulty, s1.exScore, s2.exScore FROM ' +
                 tableType + ' s1 JOIN ' + tableType + ' s2 ON s1.hash = s2.hash WHERE s1.userID = ? AND s2.userID = ?')

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


async def setup(bot):
    await bot.add_cog(CompareCog(bot))
