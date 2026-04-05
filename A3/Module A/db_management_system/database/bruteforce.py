class BruteForceDB:
    def __init__(self):
        self.keys = []
        self.values = []

    def insert(self, key, value):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                self.values[i] = value
                return
        self.keys.append(key)
        self.values.append(value)

    def search(self, key):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                return self.values[i]
        return None

    def delete(self, key):
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                self.keys.pop(i)
                self.values.pop(i)
                return True
        return False

    def range_query(self, start, end):
        results = [
            (self.keys[i], self.values[i])
            for i in range(len(self.keys))
            if start <= self.keys[i] <= end
        ]
        return sorted(results, key=lambda x: x[0])  # add this

    def get_all(self):
        return [(self.keys[i], self.values[i]) for i in range(len(self.keys))]