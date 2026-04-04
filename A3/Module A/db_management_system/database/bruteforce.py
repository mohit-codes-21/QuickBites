class BruteForceDB:
    def __init__(self):
        self.keys = []
        self.row_ids = []

    def insert(self, key, row_id):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                self.row_ids[i] = row_id
                return
        self.keys.append(key)
        self.row_ids.append(row_id)

    def search(self, key):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                return self.row_ids[i]
        return None

    def delete(self, key):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                self.keys.pop(i)
                self.row_ids.pop(i)
                return True
        return False

    def range_query(self, start, end):
        results = [
            (self.keys[i], self.row_ids[i])
            for i in range(len(self.keys))
            if start <= self.keys[i] <= end
        ]
        return sorted(results, key=lambda x: x[0])  # add this

    def get_all(self):
        return [(self.keys[i], self.row_ids[i]) for i in range(len(self.keys))]