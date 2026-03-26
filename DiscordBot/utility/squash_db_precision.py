import ast
import sqlite3


def _backup_db(db_path, logger):
    backup_path = db_path + ".bak"

    conn = sqlite3.connect(db_path)
    backup_conn = sqlite3.connect(backup_path)
    with backup_conn:
        conn.backup(backup_conn)
    backup_conn.close()
    conn.close()
    logger.info(f"Database backed up to {backup_path}")
    return backup_path

def _round_nested_numbers(value, decimal_places):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), decimal_places)
    if isinstance(value, list):
        return [_round_nested_numbers(item, decimal_places) for item in value]
    if isinstance(value, dict):
        return {k: _round_nested_numbers(v, decimal_places) for k, v in value.items()}
    return value


def _parse_serialized_points(raw_value, logger, table_name, column_name):
    if raw_value is None:
        return None
    if isinstance(raw_value, (list, dict)):
        return raw_value

    text = str(raw_value).strip()
    if not text:
        return None

    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        logger.warning("Unable to parse payload in %s.%s, skipping value", table_name, column_name)
        return None


def _get_target_tables(connection):
    c = connection.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    table_names = [row[0] for row in c.fetchall()]

    target_tables = []
    for table_name in table_names:
        c.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in c.fetchall()}
        target_columns = [name for name in ("life", "scatter") if name in columns]
        if target_columns:
            target_tables.append((table_name, target_columns))

    return target_tables


def _squash_table_rows(connection, table_name, target_columns, decimal_places, logger, batch_size=250):
    read_cursor = connection.cursor()
    write_cursor = connection.cursor()

    select_columns = ", ".join(["rowid"] + target_columns)
    read_cursor.execute(f"SELECT {select_columns} FROM {table_name}")

    rows_updated = 0
    while True:
        batch_rows = read_cursor.fetchmany(batch_size)
        if not batch_rows:
            break

        for row in batch_rows:
            rowid = row[0]
            values_by_column = dict(zip(target_columns, row[1:]))
            updates = {}

            for column_name, raw_value in values_by_column.items():
                parsed = _parse_serialized_points(raw_value, logger, table_name, column_name)
                if parsed is None:
                    continue

                rounded = _round_nested_numbers(parsed, decimal_places)
                rounded_serialized = str(rounded)

                if raw_value != rounded_serialized:
                    updates[column_name] = rounded_serialized

            if updates:
                set_clause = ", ".join([f"{column} = ?" for column in updates])
                params = list(updates.values()) + [rowid]
                write_cursor.execute(f"UPDATE {table_name} SET {set_clause} WHERE rowid = ?", params)
                rows_updated += 1

    return rows_updated


def _squash_db_precision(db_path, logger, decimal_places=3):
    connection = sqlite3.connect(db_path)
    total_rows_updated = 0

    try:
        for table_name, target_columns in _get_target_tables(connection):
            updated_in_table = _squash_table_rows(
                connection,
                table_name,
                target_columns,
                decimal_places,
                logger,
            )

            if updated_in_table:
                logger.info("Updated %s rows in table %s", updated_in_table, table_name)
                total_rows_updated += updated_in_table

        connection.commit()
    finally:
        connection.close()

    logger.info("Precision squash complete. Total rows updated: %s", total_rows_updated)
    return total_rows_updated


def _vacuum_database(db_path, logger):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("VACUUM")
    finally:
        connection.close()

    logger.info("Database compaction complete (VACUUM).")


def backup_and_squash(db_path, logger, decimal_places=3, compact=True):
    _backup_db(db_path, logger)
    rows_updated = _squash_db_precision(db_path, logger, decimal_places=decimal_places)

    if compact:
        _vacuum_database(db_path, logger)

    return rows_updated



