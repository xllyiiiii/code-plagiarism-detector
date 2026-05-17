"""二叉树实现（模仿抄袭版本 - 重命名 + 微调顺序）"""


class BinaryNode:
    def __init__(self, data=0, left_child=None, right_child=None):
        self.data = data
        self.left_child = left_child
        self.right_child = right_child


def preorder_traversal(root_node):
    """前序遍历"""
    output = []

    def helper(current):
        if current is None:
            return
        output.append(current.data)
        helper(current.left_child)
        helper(current.right_child)

    helper(root_node)
    return output


def inorder_traversal(root_node):
    """中序遍历"""
    output = []

    def helper(current):
        if current is None:
            return
        helper(current.left_child)
        output.append(current.data)
        helper(current.right_child)

    helper(root_node)
    return output


def postorder_traversal(root_node):
    """后序遍历"""
    output = []

    def helper(current):
        if current is None:
            return
        helper(current.left_child)
        helper(current.right_child)
        output.append(current.data)

    helper(root_node)
    return output


def level_traversal(root_node):
    """层序遍历"""
    if root_node is None:
        return []
    output = []
    waiting_list = [root_node]
    while waiting_list:
        current = waiting_list.pop(0)
        output.append(current.data)
        if current.left_child:
            waiting_list.append(current.left_child)
        if current.right_child:
            waiting_list.append(current.right_child)
    return output


if __name__ == '__main__':
    tree_root = BinaryNode(1)
    tree_root.left_child = BinaryNode(2)
    tree_root.right_child = BinaryNode(3)
    tree_root.left_child.left_child = BinaryNode(4)
    tree_root.left_child.right_child = BinaryNode(5)
    tree_root.right_child.right_child = BinaryNode(6)

    print("前序:", preorder_traversal(tree_root))
    print("中序:", inorder_traversal(tree_root))
    print("后序:", postorder_traversal(tree_root))
    print("层序:", level_traversal(tree_root))
