"""图的遍历实现（模仿抄袭 - 重命名变量）"""

from collections import deque


class MyGraph:
    def __init__(self):
        self.neighbors = {}

    def connect(self, a, b):
        if a not in self.neighbors:
            self.neighbors[a] = []
        if b not in self.neighbors:
            self.neighbors[b] = []
        self.neighbors[a].append(b)
        self.neighbors[b].append(a)

    def depth_first(self, begin):
        """深度优先"""
        seen = set()
        output = []

        def search(v):
            seen.add(v)
            output.append(v)
            for next_node in self.neighbors.get(v, []):
                if next_node not in seen:
                    search(next_node)

        search(begin)
        return output

    def breadth_first(self, begin):
        """广度优先"""
        seen = {begin}
        output = []
        waiting = deque([begin])

        while waiting:
            current = waiting.popleft()
            output.append(current)
            for next_node in self.neighbors.get(current, []):
                if next_node not in seen:
                    seen.add(next_node)
                    waiting.append(next_node)

        return output


if __name__ == '__main__':
    my_graph = MyGraph()
    my_graph.connect(0, 1)
    my_graph.connect(0, 2)
    my_graph.connect(1, 3)
    my_graph.connect(1, 4)
    my_graph.connect(2, 5)
    my_graph.connect(2, 6)

    print("DFS:", my_graph.depth_first(0))
    print("BFS:", my_graph.breadth_first(0))
