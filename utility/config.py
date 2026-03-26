import os

project_root = os.path.dirname(os.path.dirname(__file__))
db_folder = os.path.join(project_root, 'dbdata')
os.makedirs(db_folder, exist_ok=True)
database = os.path.join(db_folder, 'database.db')
