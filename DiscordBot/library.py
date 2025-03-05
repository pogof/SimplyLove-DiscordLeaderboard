import json

#================================================================================================
# Mappings lol
#================================================================================================
# Grade mapping
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
# Judgement times mapping
#================================================================================================

# Where the judgement window ends for each judgement
# Values are scaled based on what the Scraper returns (original scale is 0.1815 to -0.1815, mapped to 0 to 200) 

def scale(value, min_input, max_input, min_output, max_output):
    return ((value - min_input) * (max_output - min_output)) / (max_input - min_input) + min_output

def set_scale(worstWindow):

    worst_window = float(worstWindow)

    jt = {
        'e_fap': scale(-0.015, worst_window, -worst_window, 0, 200), #0.015   
        'l_fap': scale(0.015, worst_window, -worst_window, 0, 200), #-0.015
        'e_fa': scale(-0.023, worst_window, -worst_window, 0, 200), #0.023
        'l_fa': scale(0.023, worst_window, -worst_window, 0, 200), #-0.023
        'e_ex': scale(-0.0445, worst_window, -worst_window, 0, 200), #0.0445
        'l_ex': scale(0.0445, worst_window, -worst_window, 0, 200), #-0.0445
        'e_gr': scale(-0.1035, worst_window, -worst_window, 0, 200), #0.1035
        'l_gr': scale(0.1035, worst_window, -worst_window, 0, 200), #-0.1035
        'e_de': scale(-0.1365, worst_window, -worst_window, 0, 200), #0.1365
        'l_de': scale(0.1365, worst_window, -worst_window, 0, 200), #-0.1365
        'e_wo': scale(-0.1815, worst_window, -worst_window, 0, 200), #0.1815
        'l_wo': scale(0.1815, worst_window, -worst_window, 0, 200) #-0.1815
    }
    return jt


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
        'lifebarInfo': json.loads(row[12].replace("'", '"') if row[12] else '[]'),
        'worstWindow': row[13],
        'date': row[14],
        'mods': row[15],
        'prevBestEx': row[17]
    }

def extract_course_data_from_row(row):
    return {
        'courseName': row[1],
        'pack': row[2],
        'entries': row[3],
        'scripter': row[4],
        'difficulty': row[5],
        'description': row[6],
        'itgScore': row[7],
        'exScore': row[8],
        'grade': row[9],
        'hash': row[10],
        'lifebarInfo': json.loads(row[11].replace("'", '"') if row[11] else '[]'),
        'date': row[12],
        'mods': row[13],
        'prevBestEx': row[14]
    }