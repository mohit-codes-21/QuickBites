# database/table.py
from .bplustree import BPlusTree

class Table:
    def __init__(self, name, order=4):
        self.name = name
        self.index = BPlusTree(order=order)

    def insert_record(self, key, record):
        """Inserts a record associated with a key into the B+ Tree."""
        self.index.insert(key, record)

    def search_record(self, key):
        """Finds whether a key exists and returns the record."""
        return self.index.search(key)

    def delete_record(self, key):
        """Removes a key and its record from the B+ Tree."""
        return self.index.delete(key)

    def range_query(self, start_key, end_key):
        """Retrieves all keys and records within a given range."""
        return self.index.range_query(start_key, end_key)
        
    def visualize_index(self):
        """Visualizes the B+ Tree structure for this table."""
        return self.index.visualize_tree()