# understand how algorithms are implemented
# undertand data types
# start from seaching
# searching
# check if root is leaf
# if lef then just check all the keys
# else check where it lies w.r.t to keys and go to subsequent child Nodeone
# call change node to child node and iterate again

# insert
# understand helper function
# write helper functons
# do below steps using helper functions

# use a while true loop
# go to root  check if root is full
# if yes split root
#     then make new root
# else check root is leaf
#     if yes then add key, val
#     else check which child
#       if child is full
#         split child taking cases if it is leaf or not
#       else
#         add key, value to child only if child is leaf else traverse
import math
class Node:
    def __init__(self, leaf=False):
        self.leaf = leaf
        self.keys = []
        self.children = []
        self.values = []
        self.next = None

class BPlusTree:
    def __init__(self, order=4):
        self.order = order
        self.root = Node(leaf=True)

    def search ( self, key ) :
        # Search for a key in the B+ tree. Return the associated value if found, else None.
        # Traverse from root to appropriate leaf node.
        node=self.root
        while(node.leaf!=True):
            l=len(node.keys)
            if(key>= node.keys[l-1]):
                node=node.children[l]
                continue
            for i in range(0,l):
                if(key< node.keys[i]):
                    node=node.children[i]
                    break

        l=len(node.keys)
        for i in range(0,l):
            if(node.keys[i]==key):
                return node.values[i]

        return None


    def insert ( self , key , value ) :
        """
        Insert key-value pair into the B+ tree.
        Handle root splitting if necessary
        Maintain sorted order and balance properties.
        """
        root = self.root
        # If root is full, split it and make a new root
        if len(root.keys) == self.order:
            new_root = Node(leaf=False)
            new_root.children.append(root)
            # split child 0 of new_root (which is old root)
            self._split_child(new_root, 0)
            self.root = new_root

        # Insert into a non-full node (root is guaranteed non-full now)
        self._insert_non_full(self.root, key, value)


    def _insert_non_full ( self , node , key , value ) :
        # Insert key,value into node which is guaranteed to be non-full.
        if node.leaf:
            # find position to insert to keep keys sorted
            pos = 0
            while pos < len(node.keys) and node.keys[pos] < key:
                pos += 1
            # if key already exists, update the value
            if pos < len(node.keys) and node.keys[pos] == key:
                node.values[pos] = value
            else:
                node.keys.insert(pos, key)
                node.values.insert(pos, value)
            return

        # node is internal: find child to descend into
        # choose child index
        if len(node.keys) == 0:
            idx = 0
        elif key >= node.keys[-1]:
            idx = len(node.keys)
        else:
            idx = 0
            for i in range(len(node.keys)):
                if key < node.keys[i]:
                    idx = i
                    break

        child = node.children[idx]
        # if child is full, split it first
        if len(child.keys) == self.order:
            self._split_child(node, idx)
            # After split, decide which of the two children to descend into
            if idx < len(node.keys) and key >= node.keys[idx]:
                idx += 1
        # recurse into the appropriate child (now non-full)
        self._insert_non_full(node.children[idx], key, value)


    def _split_child ( self , parent , index ) :
        """
        Split the parent.children[index] node into two nodes.
        For leaves: preserve linked list and copy smallest key of right node up to parent.
        For internal nodes: promote middle key to parent and split children accordingly.
        """
        child = parent.children[index]
        new_child = Node(leaf=child.leaf)

        # choose split point
        # For order = max keys, put floor(order/2) keys in left, rest in right
        mid = self.order // 2

        if child.leaf:
            # split keys and values
            new_child.keys = child.keys[mid:]
            new_child.values = child.values[mid:]
            child.keys = child.keys[:mid]
            child.values = child.values[:mid]

            # link list maintenance
            new_child.next = child.next
            child.next = new_child

            # insert first key of new_child into parent
            promote_key = new_child.keys[0]
            parent.keys.insert(index, promote_key)
            parent.children.insert(index + 1, new_child)
        else:
            # internal node: promote middle key, split children around it
            promote_key = child.keys[mid]
            # left keys: up to mid-1 (0..mid-1), right keys: mid+1..
            new_child.keys = child.keys[mid + 1:]
            child.keys = child.keys[:mid]

            # split children: left has first mid+1 children, right has remaining
            new_child.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]

            parent.keys.insert(index, promote_key)
            parent.children.insert(index + 1, new_child)


    def delete ( self, key ) :
        """
        Delete key from the B+ tree.
        Handle underflow by borrowing from siblings or merging nodes.
        Update the root if it becomes empty.
        Return True if deletion succeeded, False otherwise.
        """
        pass

    def _delete ( self , node , key ) :
        # Recursive helper for deletion. Handle leaf and internal nodes .
        # Ensure all nodes maintain minimum keys after deletion.
        pass

    def _fill_child ( self , node , index ) :
        # Ensure child at given index has enough keys by borrowing from siblings or merging.

        pass

    def _borrow_from_prev ( self , node , index ) :
        # Borrow a key from the left sibling to prevent underflow.
        pass

    def _borrow_from_next ( self , node , index ) :
        # Borrow a key from the right sibling to prevent underflow
        pass

    def _merge ( self , node , index ) :
        # Merge child at index with its right sibling. Update parent keys
        pass

    def update ( self , key , new_value ) :
        # Update value associated with an existing key. Return True if successful.
        pass

    def range_query ( self , start_key , end_key ):
        """
        Return all key-value pairs where start_key <= key <= end_key.
        Traverse leaf nodes using the following pointers for efficient range scans.
        """
        pass

    def get_all ( self ) :
        # Return all key-value pairs in the tree using in-order traversal.
        pass

    # def visualize_tree ( self ):
    #     # Generate Graphviz representation of the B+ tree structure .
    #     pass

    # def _add_nodes ( self , dot , node ) :
    #     # Recursively add nodes to Graphviz object (for visualisation.
    #     pass

    # def _add_edges ( self , dot , node ) :
    #     # Add edges between nodes and dashed lines for leaf connections (for visualisation
    #     pass