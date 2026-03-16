# table.py

# Assuming your B+ Tree class is named BPlusTree and is inside bplustree.py
from bplustree import BPlusTree

class Table:
    def __init__(self, name, b_tree_order=4):
        """
        Initialises a Table which uses a B+ Tree as its indexing engine.
        """
        self.name = name
        self.index = BPlusTree(order=b_tree_order)

    def insert_record(self, key, record):
        """Associates a value (record) with a key in the tree."""
        self.index.insert(key, record)

    def get_record(self, key):
        """Performs an exact search for a key to return its associated record."""
        return self.index.search(key)

    def update_record(self, key, new_record):
        """Updates the value associated with an existing key."""
        return self.index.update(key, new_record)

    def delete_record(self, key):
        """Removes a key and its associated record from the index."""
        return self.index.delete(key)

    def range_query(self, start_key, end_key):
        """Retrieves all records within a given key range."""
        return self.index.range_query(start_key, end_key)
        
    def get_all_records(self):
        """Retrieves all records currently stored in the table."""
        return self.index.get_all()