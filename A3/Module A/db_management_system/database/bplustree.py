import math
import bisect
class Node:
    def __init__(self, leaf=False):
        self.leaf = leaf
        self.keys = []
        self.children = []
        self.values = []
        self.next = None

class BPlusTree:
    def _find_leaf(self, key):
        """Helper method to traverse to the correct leaf node using binary search."""
        node = self.root
        while not node.leaf:
            # bisect_right finds the index where the key should go.
            idx = bisect.bisect_right(node.keys, key)
            node = node.children[idx]
        return node

    def __init__(self, order=4):
        self.order = order
        self.root = Node(leaf=True)

    def search(self, key):
        # 1. Traverse to the correct leaf
        leaf = self._find_leaf(key)

        # 2. Binary search within the leaf to find the key
        idx = bisect.bisect_left(leaf.keys, key)

        # 3. Check if the key exists at that index
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            return leaf.values[idx]

        return None


    def insert(self, key, value):

        max_keys = self.order - 1

        # Defer the split to after insertion
        self._insert_non_full(self.root, key, value)

        # If the root overflowed during the insertion, split it now
        if len(self.root.keys) > max_keys:
            new_root = Node(leaf=False)
            new_root.children.append(self.root)

            # Use your template's split function
            self._split_child(new_root, 0)
            self.root = new_root

    def _insert_non_full(self, node, key, value):

        max_keys = self.order - 1

        if node.leaf:
            pos = bisect.bisect_left(node.keys, key)

            if pos < len(node.keys) and node.keys[pos] == key:
                node.values[pos] = value
            else:
                node.keys.insert(pos, key)
                node.values.insert(pos, value)
            return

        # Internal node: find child index to descend to
        idx = bisect.bisect_right(node.keys, key)

        # Recurse FIRST
        self._insert_non_full(node.children[idx], key, value)

        # React AFTER: Check if the child we just inserted into overflowed
        if len(node.children[idx].keys) > max_keys:
            self._split_child(node, idx)

    def _split_child(self, parent, index):

        child = parent.children[index]
        new_child = Node(leaf=child.leaf)

        k = len(child.keys) # This is currently max_keys + 1

        if child.leaf:
            mid = k // 2

            new_child.keys = child.keys[mid:]
            new_child.values = child.values[mid:]
            child.keys = child.keys[:mid]
            child.values = child.values[:mid]

            new_child.next = child.next
            child.next = new_child

            promote_key = new_child.keys[0]

            parent.keys.insert(index, promote_key)
            parent.children.insert(index + 1, new_child)
        else:
            mid = k // 2
            promote_key = child.keys[mid]

            new_child.keys = child.keys[mid + 1:]
            child.keys = child.keys[:mid]

            new_child.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]

            parent.keys.insert(index, promote_key)
            parent.children.insert(index + 1, new_child)

    def delete(self, key):

        if self.root is None:
            return False

        deleted = self._delete(self.root, key)

        # After deletion, if root is internal and has no keys, replace with its single child
        if self.root is not None and not self.root.leaf and len(self.root.keys) == 0:
            self.root = self.root.children[0]

        # If root is an empty leaf, keep it as a valid node
        if self.root is not None and self.root.leaf and len(self.root.keys) == 0:
            self.root = Node(leaf=True)

        return deleted

    def _delete(self, node, key):
        if node.leaf:
            pos = bisect.bisect_left(node.keys, key)
            if pos < len(node.keys) and node.keys[pos] == key:
                node.keys.pop(pos)
                node.values.pop(pos)
                return True
            else:
                return False

        idx = bisect.bisect_right(node.keys, key)

        # Recurse FIRST
        deleted = self._delete(node.children[idx], key)

        if not deleted:
            return False

        child = node.children[idx]

        if child.leaf:
            min_keys = math.ceil((self.order - 1) / 2)
        else:
            min_keys = math.ceil(self.order / 2) - 1

        # React AFTER: Fix the child if it underflowed
        merged = False
        if len(node.children[idx].keys) < min_keys:
            merged = self._fill_child(node, idx)

        # Only update separator key if no merge happened
        # (after a merge, node.children[idx] may no longer exist or point to wrong node)
        if not merged and child.leaf and idx > 0 and idx < len(node.children) and len(node.children[idx].keys) > 0:
            node.keys[idx - 1] = node.children[idx].keys[0]

        return True


    def _fill_child(self, node, index):
        if node.children[index].leaf:
            min_keys = math.ceil((self.order - 1) / 2)
        else:
            min_keys = math.ceil(self.order / 2) - 1

        # Try borrow from previous sibling
        if index - 1 >= 0 and len(node.children[index - 1].keys) > min_keys:
            self._borrow_from_prev(node, index)
            return False  # borrowed, no merge

        # Try borrow from next sibling
        if index + 1 < len(node.children) and len(node.children[index + 1].keys) > min_keys:
            self._borrow_from_next(node, index)
            return False  # borrowed, no merge

        # Otherwise merge with a sibling
        if index - 1 >= 0:
            self._merge(node, index - 1)
        else:
            self._merge(node, index)
        
        return True  # merged
    def _borrow_from_prev ( self , node , index ) :
        # Borrow a key from the left sibling to prevent underflow.
        left = node.children[index - 1]
        right = node.children[index]

        # If leaves, move last key from left to front of right
        if right.leaf:
            # move key/value
            right.keys.insert(0, left.keys.pop())
            right.values.insert(0, left.values.pop())
            # update parent separator: parent.keys[index-1] should be first key of right
            node.keys[index - 1] = right.keys[0]
        else:
            # Internal node borrow:
            # Move parent's separator down to front of right.keys, move left's last key up to parent
            # Move left's last child to front of right.children
            right.keys.insert(0, node.keys[index - 1])
            node.keys[index - 1] = left.keys.pop()
            # move last child from left to be first child of right
            right.children.insert(0, left.children.pop())

    def _borrow_from_next ( self , node , index ) :
        # Borrow a key from the right sibling to prevent underflow
        left = node.children[index]
        right = node.children[index + 1]

        # If leaves, move first key from right to end of left
        if left.leaf:
            left.keys.append(right.keys.pop(0))
            left.values.append(right.values.pop(0))
            # update parent separator to new first key of right
            node.keys[index] = right.keys[0]
        else:
            # Internal node borrow:
            # Move parent's separator down to end of left.keys, move right's first key up to parent
            left.keys.append(node.keys[index])
            node.keys[index] = right.keys.pop(0)
            # move first child from right to end of left.children
            left.children.append(right.children.pop(0))

    def _merge ( self , node , index ) :
        # Merge child at index with its right sibling. Update parent keys
        left = node.children[index]
        right = node.children[index + 1]

        if left.leaf:
            # merge keys and values, fix linked list
            left.keys.extend(right.keys)
            left.values.extend(right.values)
            left.next = right.next
            # remove right child and parent separator
            node.children.pop(index + 1)
            node.keys.pop(index)
        else:
            # For internal nodes: pull down separator key, then append right's keys and children
            # node.keys[index] is the separator between left and right
            left.keys.append(node.keys[index])
            left.keys.extend(right.keys)
            left.children.extend(right.children)
            # remove right child and parent separator
            node.children.pop(index + 1)
            node.keys.pop(index)

    def update(self, key, new_value):
        # 1. Traverse to the correct leaf
        leaf = self._find_leaf(key)

        # 2. Binary search within the leaf
        idx = bisect.bisect_left(leaf.keys, key)

        # 3. Update if found
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            leaf.values[idx] = new_value
            return True

        return False


    def range_query(self, start_key, end_key):
        # VALID FIX: Return a list instead of a dict
        result = []
        node = self._find_leaf(start_key)
        idx = bisect.bisect_left(node.keys, start_key)

        while node is not None:
            while idx < len(node.keys):
                if node.keys[idx] > end_key:
                    return result

                # VALID FIX: Append as a tuple
                result.append((node.keys[idx], node.values[idx]))
                idx += 1

            node = node.next
            idx = 0

        return result

    def get_all(self):
        # VALID FIX: Return a list instead of a dict
        node = self.root
        while not node.leaf:
            node = node.children[0]

        result = []
        while node is not None:
            for i in range(len(node.keys)):
                # VALID FIX: Append as a tuple
                result.append((node.keys[i], node.values[i]))
            node = node.next

        return result

    def visualize_tree(self):
        # Generate Graphviz representation of the B+ tree structure.
        try:
            import graphviz
        except ImportError:
            print("Graphviz is not installed. Please run: pip install graphviz")
            return None

        # FIX: Changed shape to 'none' so Graphviz doesn't crash on flat edges
        dot = graphviz.Digraph(name="BPlusTree", node_attr={'shape': 'none'})
        
        self._add_nodes(dot, self.root)
        self._add_edges(dot, self.root)
        
        return dot

    def _add_nodes(self, dot, node):
        # Recursively add nodes to Graphviz object (for visualisation)
        if node is None:
            return

        if len(node.keys) == 0:
            label = '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0"><TR><TD>EMPTY</TD></TR></TABLE>>'
        else:
            # Create a table cell <TD> for each key
            tds = "".join(f"<TD>{k}</TD>" for k in node.keys)
            label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0"><TR>{tds}</TR></TABLE>>'

        dot.node(str(id(node)), label)

        # Recurse for children
        if not node.leaf:
            for child in node.children:
                self._add_nodes(dot, child)

    def _add_edges(self, dot, node):

        if node is None:
            return

        if not node.leaf:
            for child in node.children:
                dot.edge(str(id(node)), str(id(child)))
                self._add_edges(dot, child)

        if node.leaf and node.next is not None:
            # constraint="false" keeps the graph from pushing the linked leaf down a level
            dot.edge(str(id(node)), str(id(node.next)), style="dashed", constraint="false")

