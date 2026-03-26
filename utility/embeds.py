import discord
import numpy as np
import logging
import sqlite3

from utility.library import grade_mapping, set_scale, scale
from utility.plot import build_plot_attachment, create_scatterplot_from_json, create_distribution_from_json
from utility.config import database


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
            file = discord.File('resources/lmao2.gif', filename='lmao2.gif')
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
        embed.add_field(name="Difficulty", value=style + str(data.get('difficulty')), inline=True)
        # embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
        upscore = round(float(data.get('exScore')) - float(data.get('prevBestEx')), 2)
        embed.add_field(name="EX Score", value=f"{float(data.get('exScore')):.2f}% (+ {upscore:.2f}%)", inline=True)
        embed.add_field(name="Grade", value=mapped_grade, inline=True)
        embed.add_field(name="Length", value=data.get('length'), inline=True)
        # embed.add_field(name="Stepartist", value=data.get('stepartist'), inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)

        logging.info(f"Starting scatterplot creation for song: {data.get('songName')}")
        file = build_plot_attachment(create_scatterplot_from_json, 'scatterplot.png', data.get('scatterplotData'), data.get('lifebarInfo'))
        logging.info(f"Completed scatterplot creation for song: {data.get('songName')}")

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
        embed.add_field(name="Difficulty", value=style + str(data.get('difficulty')), inline=True)
        embed.add_field(name="ITG Score", value=f"{data.get('itgScore')}%", inline=True)
        upscore = round(float(data.get('exScore')) - float(data.get('prevBestEx')), 2)
        embed.add_field(name="EX Score", value=f"{float(data.get('exScore')):.2f}% (+ {upscore:.2f}%)", inline=True)
        embed.add_field(name="Grade", value=mapped_grade, inline=True)
        embed.add_field(name="Date played", value=data.get('date'), inline=True)
        embed.add_field(name="Mods", value=data.get('mods'), inline=True)

        file = build_plot_attachment(create_scatterplot_from_json, 'scatterplot.png', None, data.get('lifebarInfo'))
        embed.set_image(url="attachment://scatterplot.png")

    return embed, file


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
        embed.add_field(name="EX Score", value=f"{float(data.get('exScore')):.2f}%", inline=True)
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
        entries_str = entries_str.strip()
        embed.add_field(name="Song | Artist | Diff | Length", value=entries_str, inline=True)

        file = build_plot_attachment(create_scatterplot_from_json, 'scatterplot.png', None, data.get('lifebarInfo'))
        embed.set_image(url="attachment://scatterplot.png")
        return embed, file

    if data.get('worstWindow') is None:
        embed = discord.Embed(title="Unable to create breakdown", color=color)
        embed.add_field(name="Error", value="No judgement window data found for this score. Old score. If you want breakdown get better score :P", inline=False)
        file = discord.File('resources/lmao2.gif', filename='lmao2.gif')
        embed.set_image(url="attachment://lmao2.gif")
        return embed, file

    embed = discord.Embed(title=f"{title}", color=color)
    embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
    embed.add_field(name="Song", value=data.get('songName'), inline=True)
    embed.add_field(name="Pack", value=data.get('pack'), inline=True)
    embed.add_field(name="EX Score", value=f"{float(data.get('exScore')):.2f}%", inline=True)
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
    mean_abs_error = np.round(np.sum(np.abs(y_scaled)) / len(y_scaled))  #NOTE: reimplemented from Simply-Love-SM5/BGAnimations/ScreenEvaluation common/Panes/Pane5/default.lua

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
    file = build_plot_attachment(create_distribution_from_json, 'distribution.png', data.get('scatterplotData'), data.get('worstWindow'))
    logging.info(f"Completed distribution plot creation for song: {data.get('songName')}")
    embed.set_image(url="attachment://distribution.png")

    return embed, file


def get_top_scores(selected_row, interaction, num, tableType):
    conn = sqlite3.connect(database)
    c = conn.cursor()

    query = ('SELECT userID, exScore FROM ' + tableType +
             ' WHERE hash = ? AND userID IN (SELECT userID FROM ' + tableType +
             ' WHERE hash = ?) ORDER BY exScore DESC LIMIT ?')

    c.execute(query, (selected_row[10], selected_row[10], num))
    top_scores = c.fetchall()
    conn.close()

    top_scores = [(uid, ex_score) for uid, ex_score in top_scores if interaction.guild.get_member(int(uid))]

    top_scores_message = ""
    for idx, (uid, ex_score) in enumerate(top_scores, start=1):
        top_scores_message += f"{idx}. <@!{uid}>, EX Score: {float(ex_score):.2f}%\n"

    return top_scores_message
