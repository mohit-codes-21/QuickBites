# database/db_manager.py
from .table import Table

class DatabaseManager:
    def __init__(self):
        self.tables = {}

    def create_table(self, table_name, order=4):
        """Creates a new table if it doesn't already exist."""
        if table_name not in self.tables:
            self.tables[table_name] = Table(table_name, order)
            return True
        return False

    def get_table(self, table_name):
        """Retrieves an existing table by name."""
        return self.tables.get(table_name)

    def drop_table(self, table_name):
        """Removes a table from the database manager."""
        if table_name in self.tables:
            del self.tables[table_name]
            return True
        return False