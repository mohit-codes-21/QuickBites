from database.bplustree import BPlusTree
from database.bruteforce import BruteForceDB

class Table:
    def __init__(self, name, schema, order=8, search_key=None, index_type="bplustree"):
        self.name = name                             
        self.schema = schema                         
        self.order = order                           
        self.search_key = search_key                 
        self.index_type = index_type

        # --- THE HEAP (Central Data Store) ---
        self.heap = {}
        self.next_row_id = 0                         

        # --- THE INDEX (Lightweight Pointers Only) ---
        if self.index_type == "bplustree":
            self.data = BPlusTree(order=order)
        elif self.index_type == "bruteforce":
            self.data = BruteForceDB()
        else:
            raise ValueError("Unknown index_type. Use 'bplustree' or 'bruteforce'")

        if self.search_key is not None and self.search_key not in self.schema:
            raise ValueError("search_key must be one of the columns in schema")

    def validate_record(self, record):
        if not isinstance(record, dict): return False
        if set(record.keys()) != set(self.schema.keys()): return False
        for column, expected_type in self.schema.items():
            value = record[column]
            if isinstance(expected_type, type):
                if not isinstance(value, expected_type): return False
            else:
                type_name = str(expected_type).lower()
                if type_name in ("int", "<class 'int'>") and not isinstance(value, int): return False
                if type_name in ("str", "<class 'str'>") and not isinstance(value, str): return False
                if type_name in ("float", "<class 'float'>") and not isinstance(value, float): return False
                if type_name in ("bool", "<class 'bool'>") and not isinstance(value, bool): return False
        return True

    def insert(self, record):
        if self.search_key is None: raise ValueError("search_key is not set")
        if not self.validate_record(record): raise ValueError("Record schema mismatch")
        key = record[self.search_key]

        existing_row_id = self.data.search(key)
        if existing_row_id is not None:
            self.heap[existing_row_id] = record.copy()
            return existing_row_id

        row_id = self.next_row_id
        self.heap[row_id] = record.copy()
        self.next_row_id += 1
        self.data.insert(key, row_id)
        return row_id

    def get(self, record_id):
        # 1. Search Index for pointer
        row_id = self.data.search(record_id)
        
        # 2. Access Heap via pointer
        if row_id is not None:
            return self.heap[row_id]
        return None

    def get_all(self):
        return [self.heap[row_id] for _, row_id in self.data.get_all()]

    def update(self, record_id, new_record):
        if self.search_key is None: raise ValueError("search_key is not set")
        if not self.validate_record(new_record): raise ValueError("Record schema mismatch")

        row_id = self.data.search(record_id)
        if row_id is None: return False

        new_record = new_record.copy()
        new_record[self.search_key] = record_id
        self.heap[row_id] = new_record 
        return True

    def delete(self, record_id):
        # 1. Search Index to retrieve the row_id pointer FIRST
        row_id = self.data.search(record_id)
        if row_id is None: return False
        
        # 2. Delete the lightweight pointer from the Index
        self.data.delete(record_id)
        
        # 3. Use the retrieved pointer to delete from the Heap
        del self.heap[row_id]       
        return True

    def range_query(self, start_value, end_value):
        pointers = self.data.range_query(start_value, end_value)
        return [self.heap[row_id] for _, row_id in pointers]