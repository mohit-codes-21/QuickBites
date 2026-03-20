class BruteForceDB:
    def __init__(self):
        self.data = []

    def insert(self, key, value):
        for i, (k, v) in enumerate(self.data):
            if k == key:
                self.data[i] = (key, value)
                return
        self.data.append((key, value))

    def search(self, key):
        for k, v in self.data:
            if k == key:
                return v
        return None

    def delete(self, key):
        for i, (k, _) in enumerate(self.data):
            if k == key:
                self.data.pop(i)
                return True
        return False

    def range_query(self, start, end):
        return [(k, v) for k, v in self.data if start <= k <= end]