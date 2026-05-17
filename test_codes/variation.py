"""二叉树遍历（迭代版本 + 不同结构风格）"""


class Node:
    def __init__(self, value):
        self.value = value
        self.lchild = None
        self.rchild = None


def traverse_pre(root):
    """前序遍历 - 迭代实现"""
    if root is None:
        return []
    res = []
    stack = [root]
    while stack:
        cur = stack.pop()
        res.append(cur.value)
        if cur.rchild:
            stack.append(cur.rchild)
        if cur.lchild:
            stack.append(cur.lchild)
    return res


def traverse_in(root):
    """中序遍历 - 迭代实现"""
    res = []
    stack = []
    cur = root
    while stack or cur:
        while cur:
            stack.append(cur)
            cur = cur.lchild
        cur = stack.pop()
        res.append(cur.value)
        cur = cur.rchild
    return res


def traverse_post(root):
    """后序遍历 - 双栈迭代"""
    if root is None:
        return []
    res = []
    s1 = [root]
    s2 = []
    while s1:
        node = s1.pop()
        s2.append(node)
        if node.lchild:
            s1.append(node.lchild)
        if node.rchild:
            s1.append(node.rchild)
    while s2:
        res.append(s2.pop().value)
    return res


def traverse_level(root):
    """层序遍历"""
    if not root:
        return []
    from collections import deque
    res = []
    q = deque([root])
    while q:
        node = q.popleft()
        res.append(node.value)
        if node.lchild:
            q.append(node.lchild)
        if node.rchild:
            q.append(node.rchild)
    return res


if __name__ == '__main__':
    t = Node(1)
    t.lchild = Node(2)
    t.rchild = Node(3)
    t.lchild.lchild = Node(4)
    t.lchild.rchild = Node(5)
    t.rchild.rchild = Node(6)

    print("前序:", traverse_pre(t))
    print("中序:", traverse_in(t))
    print("后序:", traverse_post(t))
    print("层序:", traverse_level(t))
