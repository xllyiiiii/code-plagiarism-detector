"""相似度计算引擎 —— 多维度量化两份代码/文本的相似程度。"""


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
    综合计算两份代码或文本的相似度。

    根据 content_type 自动分发到代码管线或文本管线。
    """
    if features_a.get('content_type') == 'text' and features_b.get('content_type') == 'text':
        return _compute_text_similarity(features_a, features_b)

    # 类型不匹配（不应发生，batch_compare 已分区）
    if features_a.get('content_type') != features_b.get('content_type'):
        return {'jaccard': 0.0, 'tree_edit': 0.0, 'ngram': 0.0, 'final': 0.0}

    # 代码管线（原有逻辑）
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

    final = 0.40 * tree_edit + 0.35 * jaccard + 0.25 * ngram

    return {
        'jaccard': round(jaccard, 4),
        'tree_edit': round(tree_edit, 4),
        'ngram': round(ngram, 4),
        'final': round(final, 4),
    }


def batch_compare(submissions, threshold=0.70):
    """
    对一组提交进行两两比对。代码和文本分开比较，不交叉。

    Args:
        submissions: list of (submission_id, features_dict)
        threshold: 相似度阈值

    Returns:
        list of (sub_a_id, sub_b_id, scores_dict)
    """
    code_subs = [(sid, f) for sid, f in submissions
                 if f.get('content_type') != 'text']
    text_subs = [(sid, f) for sid, f in submissions
                 if f.get('content_type') == 'text']

    def _pairwise(group):
        results = []
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                id_a, feat_a = group[i]
                id_b, feat_b = group[j]
                scores = compute_similarity(feat_a, feat_b)
                if scores['final'] >= threshold:
                    results.append((id_a, id_b, scores))
        return results

    results = _pairwise(code_subs) + _pairwise(text_subs)
    results.sort(key=lambda x: x[2]['final'], reverse=True)
    return results


# ================================================================
# 文本相似度函数
# ================================================================


def _text_lcs_similarity(sentences_a, sentences_b):
    """句子级最长公共子序列相似度。归一化后返回 0~1。"""
    if not sentences_a and not sentences_b:
        return 1.0
    m, n = len(sentences_a), len(sentences_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if sentences_a[i - 1] == sentences_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    return lcs_len / max(m, n) if max(m, n) > 0 else 0.0


def _compute_text_similarity(features_a, features_b):
    """文本版相似度计算。权重与代码版一致。

    35% Jaccard（词 shingle 重叠）+ 40% LCS（句子结构）+ 25% N-gram（局部词语重叠）
    """
    jaccard = jaccard_similarity(
        features_a.get('subtree_hashes', []),
        features_b.get('subtree_hashes', [])
    )

    lcs = _text_lcs_similarity(
        features_a.get('sentences', []),
        features_b.get('sentences', [])
    )

    ngram = ngram_similarity(
        features_a.get('tokens', []),
        features_b.get('tokens', []),
        n=3
    )

    final = 0.40 * lcs + 0.35 * jaccard + 0.25 * ngram

    return {
        'jaccard': round(jaccard, 4),
        'tree_edit': round(lcs, 4),
        'ngram': round(ngram, 4),
        'final': round(final, 4),
    }
