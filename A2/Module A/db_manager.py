# db_manager.py

from table import Table

class DatabaseManager:
    def __init__(self):
        """
        Initialises the Database Manager to manage multiple Table structures.
        """
        # A dictionary to hold our tables: { 'table_name': Table_Object }
        self.tables = {}

    def create_table(self, table_name, b_tree_order=4):
        """Creates a new table and adds it to the manager."""
        if table_name in self.tables:
            raise ValueError(f"Table '{table_name}' already exists.")
        
        new_table = Table(table_name, b_tree_order)
        self.tables[table_name] = new_table
        print(f"Table '{table_name}' created successfully.")
        return new_table

    def get_table(self, table_name):
        """Retrieves an existing table by its name."""
        if table_name not in self.tables:
            raise ValueError(f"Table '{table_name}' does not exist.")
        
        return self.tables[table_name]

    def drop_table(self, table_name):
        """Removes a table from the database manager."""
        if table_name in self.tables:
            del self.tables[table_name]
            print(f"Table '{table_name}' dropped successfully.")
            return True
        return False

    def list_tables(self):
        """Returns a list of all table names currently in the database."""
        return list(self.tables.keys())