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

# deltion

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
        max_keys = self.order - 1

        # If root is full, split it and make a new root
        if len(root.keys) == max_keys:
            new_root = Node(leaf=False)
            new_root.children.append(root)

            # split child 0 of new_root (which is old root)
            self._split_child(new_root, 0)

            self.root = new_root

        # Insert into a non-full node (root is guaranteed non-full now)
        self._insert_non_full(self.root, key, value)


    def _insert_non_full ( self , node , key , value ) :
        # Recursive helper to insert into a non-full node.
        # Split child nodes if they become full during insertion.

        if node.leaf:
            pos = 0
            while pos < len(node.keys) and key > node.keys[pos]:
                pos += 1

            if pos < len(node.keys) and node.keys[pos] == key:
                node.values[pos] = value
            else:
                node.keys.insert(pos, key)
                node.values.insert(pos, value)
            return

        # find child index to descend to

        idx = 0
        while idx < len(node.keys) and key >= node.keys[idx]:
            idx += 1

        child = node.children[idx]
        max_keys = self.order - 1

        if len(child.keys) == max_keys:
            self._split_child(node, idx)

            # after split, decide which child to descend to
            if idx < len(node.keys) and key >= node.keys[idx]:
                idx += 1

        self._insert_non_full(node.children[idx], key, value)


    def _split_child ( self , parent , index ) :
        """
        Split the arentchild at the given index
        For leaves:preserve the linked list structure and copy the middle key to the parent.
        For internal nodes: promote the middle key and split the children
        """

        child = parent.children[index]
        new_child = Node(leaf=child.leaf)

        # choose split point based on actual number of keys in the child
        k = len(child.keys)

        if child.leaf:
            # for leaves, give left ceil(k/2) keys, right the rest
            mid = (k + 1) // 2

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
            # for internal nodes promote the middle key
            mid = k // 2
            promote_key = child.keys[mid]

            new_child.keys = child.keys[mid + 1:]
            child.keys = child.keys[:mid]

            new_child.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]

            parent.keys.insert(index, promote_key)
            parent.children.insert(index + 1, new_child)
# check if root is leaf if yes
#     try to delete return true or False
# else
#     call _deleete
# travers till leaf
# delele the key,
# if it is first key
#     then remove it from parent and replace with new key in parent also and also properly change the next pointer
# else just delete it
# check if minimum number of keys in delted node
# if >min
#     no probem end function
# else
#     try to borrow from left , try to borrow from right
#     try to merge with left or try to merge with right
# (Merging)
# provide left siblign for merging
# merge left and right update the next pointers and delete the right child value that is present in the parnet

    def delete ( self, key ) :
        """
        Delete key from the B+ tree.
        Handle underflow by borrowing from siblings or merging nodes.
        Update the root if it becomes empty.
        Return True if deletion succeeded, False otherwise.
        """
        if self.root is None:
            return False

        deleted = self._delete(self.root, key)

        # After deletion, if root is internal and has no keys, replace with its single child
        if self.root is not None and not self.root.leaf and len(self.root.keys) == 0:
            # promote the single child to be the new root
            self.root = self.root.children[0]

        # If root is a leaf and becomes empty, represent tree as an empty leaf (keep root as a node)
        if self.root is not None and self.root.leaf and len(self.root.keys) == 0:
            # keep a valid Node object as root (avoid None to keep insert/search safe)
            self.root = Node(leaf=True)

        return deleted

    def _delete ( self , node , key ) :
        # Recursive helper for deletion. Handle leaf and internal nodes .
        # Ensure all nodes maintain minimum keys after deletion.

        max_keys = self.order - 1
        min_keys = math.ceil(self.order / 2) - 1

        # If node is a leaf, remove the key if present
        if node.leaf:
            # find key linearly (avoid bisect as requested)
            pos = 0
            while pos < len(node.keys) and node.keys[pos] < key:
                pos += 1

            if pos < len(node.keys) and node.keys[pos] == key:
                # delete key and corresponding value
                node.keys.pop(pos)
                node.values.pop(pos)
                return True
            else:
                return False

        # Internal node: decide which child to descend into
        idx = 0
        while idx < len(node.keys) and key >= node.keys[idx]:
            idx += 1

        # Ensure the child we will descend into has at least min_keys+1 before descending
        child = node.children[idx]
        if len(child.keys) == min_keys:
            self._fill_child(node, idx)
            # fill may have changed structure (merge), recompute idx
            idx = 0
            while idx < len(node.keys) and key >= node.keys[idx]:
                idx += 1
            # guard if children changed
            if idx >= len(node.children):
                idx = len(node.children) - 1

        # Recurse into the (now safe) child
        deleted = self._delete(node.children[idx], key)
        if not deleted:
            return False


        return True

    def _fill_child ( self , node , index ) :
        # Ensure child at given index has enough keys by borrowing from siblings or merging.

        max_keys = self.order - 1
        min_keys = math.ceil(self.order / 2) - 1

        child = node.children[index]

        # Try borrow from previous sibling
        if index - 1 >= 0 and len(node.children[index - 1].keys) > min_keys:
            self._borrow_from_prev(node, index)
            return

        # Try borrow from next sibling
        if index + 1 < len(node.children) and len(node.children[index + 1].keys) > min_keys:
            self._borrow_from_next(node, index)
            return

        # Otherwise merge with a sibling
        if index + 1 < len(node.children):
            # merge child with next sibling
            self._merge(node, index)
        else:
            # merge with previous sibling (index-1)
            self._merge(node, index - 1)

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

    def update ( self , key , new_value ) :
        # Update value associated with an existing key. Return True if successful.

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
                node.values[i]=new_value
                return True

        return False


    def range_query ( self , start_key , end_key ):
        """
        Return all key-value pairs where start_key <= key <= end_key.
        Traverse leaf nodes using the following pointers for efficient range scans.
        """
        ans={}
        node=self.root
        while(node.leaf!=True):
            l=len(node.keys)
            if(start_key>= node.keys[l-1]):
                node=node.children[l]
                continue
            for i in range(0,l):
                if(start_key< node.keys[i]):
                    node=node.children[i]
                    break


        while(node!=None):
            for i in range(0,len(node.keys)):
                if(node.keys[i]>=start_key):
                    j=i
                    while(node!= None):
                        while(j<len(node.keys)):
                            if(node.keys[j]>end_key):
                                return ans
                            ans[node.keys[j]]=node.values[j]
                            j+=1
                        node=node.next
                        j=0
                    return ans
            node=node.next

        return {}

    def get_all ( self ) :
        node=self.root
        while(node.leaf!=True):
            node=node.children[0]
        ans={}
        while(node!= None):
            i=0
            while(i<len(node.keys)):
                ans[node.keys[i]]=node.values[i]
                i+=1
            node=node.next

        return ans


    # def visualize_tree ( self ):
    #     # Generate Graphviz representation of the B+ tree structure .
    #     pass

    # def _add_nodes ( self , dot , node ) :
    #     # Recursively add nodes to Graphviz object (for visualisation.
    #     pass

    # def _add_edges ( self , dot , node ) :
    #     # Add edges between nodes and dashed lines for leaf connections (for visualisation
    #     pass