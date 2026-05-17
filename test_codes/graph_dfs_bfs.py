"""图的 DFS 和 BFS 实现"""

from collections import deque


class Graph:
    def __init__(self):
        self.adj = {}

    def add_edge(self, u, v):
        if u not in self.adj:
            self.adj[u] = []
        if v not in self.adj:
            self.adj[v] = []
        self.adj[u].append(v)
        self.adj[v].append(u)

    def dfs(self, start):
        """深度优先搜索"""
        visited = set()
        result = []

        def explore(node):
            visited.add(node)
            result.append(node)
            for neighbor in self.adj.get(node, []):
                if neighbor not in visited:
                    explore(neighbor)

        explore(start)
        return result

    def bfs(self, start):
        """广度优先搜索"""
        visited = {start}
        result = []
        queue = deque([start])

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in self.adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return result


if __name__ == '__main__':
    g = Graph()
    g.add_edge(0, 1)
    g.add_edge(0, 2)
    g.add_edge(1, 3)
    g.add_edge(1, 4)
    g.add_edge(2, 5)
    g.add_edge(2, 6)

    print("DFS:", g.dfs(0))
    print("BFS:", g.bfs(0))
