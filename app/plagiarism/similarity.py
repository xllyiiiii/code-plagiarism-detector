"""相似度计算引擎 —— 多维度量化两份代码的相似程度。"""


def jaccard_similarity(set_a, set_b):
    """
    AST 子树哈希集合的 Jaccard 相似度。
    对重命名完全不敏感，权重 30%。
    """
    sa = set(set_a)
    sb = set(set_b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def ngram_similarity(tokens_a, tokens_b, n=5):
    """
    Token n-gram 重叠度。
    辅助维度，权重 10%。
    """
    from hashlib import md5

    def _grams(tokens, k):
        if len(tokens) < k:
            return {md5(' '.join(tokens).encode()).hexdigest()[:12]}
        g = set()
        for i in range(len(tokens) - k + 1):
            gram = ' '.join(tokens[i:i + k])
            g.add(md5(gram.encode()).hexdigest()[:12])
        return g

    ga = _grams(tokens_a, n)
    gb = _grams(tokens_b, n)
    if not ga and not gb:
        return 1.0
    return len(ga & gb) / len(ga | gb)


def tree_edit_similarity(ast_a, ast_b):
    """
    树编辑距离相似度（简化版：基于节点类型序列的编辑距离）。
    完整 APTED 算法作为后续优化方向。
    权重 40%。
    """
    def _node_type_sequence(node):
        """BFS 遍历提取节点类型序列。"""
        seq = []
        if node is None:
            return seq
        queue = [node]
        while queue:
            cur = queue.pop(0)
            if isinstance(cur, dict):
                seq.append(cur.get('_type', '?'))
                for key, val in cur.items():
                    if key.startswith('_'):
                        continue
                    if isinstance(val, dict):
                        queue.append(val)
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                queue.append(item)
        return seq

    seq_a = _node_type_sequence(ast_a)
    seq_b = _node_type_sequence(ast_b)

    if not seq_a and not seq_b:
        return 1.0

    # Levenshtein distance on node type sequences
    m, n = len(seq_a), len(seq_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # delete
                dp[i][j - 1] + 1,      # insert
                dp[i - 1][j - 1] + cost  # replace
            )

    edit_dist = dp[m][n]
    max_len = max(m, n)
    return 1.0 - (edit_dist / max_len)


def compute_similarity(features_a, features_b):
    """
    综合计算两份代码的相似度。

    Args:
        features_a, features_b: extract_features() 返回的字典

    Returns:
        dict: {
            'jaccard': float,
            'tree_edit': float,
            'ngram': float,
            'final': float,         # 加权综合得分
        }
    """
    jaccard = jaccard_similarity(
        features_a.get('subtree_hashes', []),
        features_b.get('subtree_hashes', [])
    )

    tree_edit = tree_edit_similarity(
        features_a.get('ast_root'),
        features_b.get('ast_root')
    )

    ngram = ngram_similarity(
        features_a.get('tokens', []),
        features_b.get('tokens', [])
    )

    # 综合加权（初期语义哈希暂未启用，权重重新分配）
    final = 0.40 * tree_edit + 0.35 * jaccard + 0.25 * ngram

    return {
        'jaccard': round(jaccard, 4),
        'tree_edit': round(tree_edit, 4),
        'ngram': round(ngram, 4),
        'final': round(final, 4),
    }


def batch_compare(submissions, threshold=0.70):
    """
    对一组提交进行两两比对，返回高相似度对。

    Args:
        submissions: list of (submission_id, features_dict)
        threshold: 相似度阈值

    Returns:
        list of (sub_a_id, sub_b_id, scores_dict)
    """
    results = []
    n = len(submissions)

    for i in range(n):
        for j in range(i + 1, n):
            id_a, feat_a = submissions[i]
            id_b, feat_b = submissions[j]
            scores = compute_similarity(feat_a, feat_b)

            if scores['final'] >= threshold:
                results.append((id_a, id_b, scores))

    results.sort(key=lambda x: x[2]['final'], reverse=True)
    return results
