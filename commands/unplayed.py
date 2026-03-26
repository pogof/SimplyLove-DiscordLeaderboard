import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

from utility.config import database


async def unplayed_logic(interaction: discord.Interaction, page: int, order, private, results, user_two_id):

    order_mapping = {
        "asc_alpha": "Ascending Alphabetical Order",
        "desc_alpha": "Descending Alphabetical Order"
    }

    embed = discord.Embed(title=f"Unplayed charts - Order: {order_mapping[order]}", color=discord.Color.blue())
    embed.set_footer(text=f"Page {page}")
    if user_two_id:
        embed.add_field(name=f"Compared to user", value=f"<@!{user_two_id}>", inline=True)
    else:
        embed.add_field(name=f"Compared to all other players", value="", inline=True)

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


class UnplayedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #================================================================================================
    # Unplayed songs
    #================================================================================================

    @app_commands.command(name="unplayed", description="Returns a list of songs that you have not played.")
    @app_commands.describe(user_two="User to compare (optional)", private="Whether the response should be private", order="The order asc/desc_ex, _alpha")
    async def unplayed(self, interaction: discord.Interaction, user_two: discord.User = None, isdouble: bool = False, ispump: bool = False, iscourse: bool = False, page: int = 1, order: str = "desc_alpha", private: bool = True, pack: str = "", difficulty: int = 0):
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
            order_by = "s1.songName DESC"

        tableType = ''
        if iscourse:
            tableType = 'COURSES'
        if isdouble:
            tableType = 'DOUBLES'
        else:
            tableType = 'SINGLES'
        if ispump:
            tableType += '_PUMP'

        if user_two_id:
            query = ('SELECT DISTINCT s2.songName, s2.artist, s2.pack, s2.difficulty FROM ' + tableType +
                     ' s2 LEFT JOIN ' + tableType + ' s1 ON s2.hash = s1.hash AND s1.userID = ? WHERE s1.userID IS NULL AND s2.userID = ?')
            params = [user_one_id, user_two_id]
            if difficulty:
                query += " AND s2.difficulty = ?"
                params.append(str(difficulty))
            if pack:
                query += " AND s2.pack LIKE ?"
                params.append(f"%{pack}%")
        else:
            query = ('SELECT DISTINCT s1.songName, s1.artist, s1.pack, s1.difficulty FROM ' + tableType +
                     ' s1 LEFT JOIN ' + tableType + ' s2 ON s1.hash = s2.hash AND s2.userID = ? WHERE s2.userID IS NULL AND s1.userID != ?')
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


async def setup(bot):
    await bot.add_cog(UnplayedCog(bot))
