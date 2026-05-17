"""代码质量分析引擎 —— 从规范、结构、可读性等维度评估代码，生成学习建议。"""

import ast
import re
from collections import Counter


class CodeAnalyzer:
    """分析单份代码的质量，生成问题和改进建议。"""

    PYTHON_KEYWORDS = {
        'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
        'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
        'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
        'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
        'try', 'while', 'with', 'yield'
    }

    JAVA_KEYWORDS = {
        'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch',
        'char', 'class', 'continue', 'default', 'do', 'double', 'else', 'enum',
        'extends', 'final', 'finally', 'float', 'for', 'if', 'implements',
        'import', 'int', 'interface', 'long', 'new', 'package', 'private',
        'protected', 'public', 'return', 'short', 'static', 'super', 'switch',
        'this', 'throw', 'throws', 'try', 'void', 'while'
    }

    def __init__(self, source_code, language='python'):
        self.source_code = source_code
        self.lines = source_code.split('\n')
        self.language = language
        self.issues = []
        self.suggestions = []
        self.score = 100  # 起始满分，每发现一个问题扣分

    def analyze(self):
        """执行全部检测，返回分析报告。"""
        self._check_function_length()
        self._check_nesting_depth()
        self._check_magic_numbers()
        self._check_naming_convention()
        self._check_repeated_code()
        self._check_comments()
        self._generate_suggestions()
        return self._build_report()

    # ================================================================
    # 检测规则
    # ================================================================

    def _check_function_length(self):
        """检测函数过长（PEP 8 建议 ≤ 50 行）。"""
        if self.language == 'python':
            in_func = False
            func_name = ''
            func_start = 0
            func_lines = 0
            for i, line in enumerate(self.lines, 1):
                stripped = line.strip()
                if stripped.startswith('def '):
                    in_func = True
                    func_name = stripped[4:].split('(')[0]
                    func_start = i
                    func_lines = 0
                elif in_func:
                    # 函数结束时（顶格非空行 且 非注释）
                    if stripped and not stripped.startswith('#') and not stripped.startswith(' '):
                        if not stripped.startswith('@'):  # 装饰器
                            if func_lines > 50:
                                self._add_issue(
                                    f'函数 "{func_name}" 过长（{func_lines} 行），'
                                    f'建议拆分为 ≤50 行的小函数',
                                    'style', 5
                                )
                            in_func = False
                    else:
                        func_lines += 1
                        if stripped:
                            func_lines += 1

    def _check_nesting_depth(self):
        """检测嵌套层级过深（> 4 层）。"""
        indent_history = []
        for i, line in enumerate(self.lines, 1):
            if not line.strip() or line.strip().startswith('#'):
                continue
            spaces = len(line) - len(line.lstrip(' '))
            # 更新缩进栈
            while indent_history and indent_history[-1] >= spaces:
                indent_history.pop()
            indent_history.append(spaces)
            depth = len(indent_history) - 1  # 0 为模块顶层
            if depth > 4:
                self._add_issue(
                    f'第 {i} 行嵌套层级过深（{depth} 层），建议重构为更扁平的结构',
                    'structure', 8
                )
                break  # 每文件只报一次

    def _check_magic_numbers(self):
        """检测魔法数字（非 0/1/-1 的字面量直接出现在表达式中）。"""
        magic_pattern = re.compile(r'(?<![a-zA-Z_"])\b([2-9]\d*)\b(?!["\'])')
        found = set()
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('import'):
                continue
            matches = magic_pattern.findall(line)
            for m in matches:
                if m not in found:
                    found.add(m)
        if len(found) > 3:
            self._add_issue(
                f'发现 {len(found)} 个魔法数字（{", ".join(list(found)[:5])}...），'
                f'建议定义为命名常量',
                'readability', len(found) * 2
            )

    def _check_naming_convention(self):
        """检测命名规范。"""
        if self.language == 'python':
            # 变量名应小写 + 下划线
            snake_pattern = re.compile(r'^[a-z_][a-z0-9_]*$')
            cap_pattern = re.compile(r'^[A-Z_][A-Z0-9_]*$')  # 常量
            bad_names = []
            for i, line in enumerate(self.lines, 1):
                # 检测赋值语句中的变量名
                match = re.match(r'^(\s*)([a-zA-Z_]\w*)\s*=', line)
                if match:
                    name = match.group(2)
                    if name in self.PYTHON_KEYWORDS:
                        continue
                    if name[0].isupper() and not cap_pattern.match(name):
                        bad_names.append(f'L{i}:{name}')
                    elif name[0].islower() and not snake_pattern.match(name):
                        if '_' not in name and any(c.isupper() for c in name):
                            bad_names.append(f'L{i}:{name} (camelCase)')
            if len(bad_names) > 0:
                self._add_issue(
                    f'命名不规范: {", ".join(bad_names[:5])}，'
                    f'Python 变量应使用 snake_case',
                    'naming', len(bad_names) * 3
                )

    def _check_repeated_code(self):
        """检测文件内重复代码块（≥5 行相同）。"""
        if len(self.lines) < 10:
            return
        # 5 行滑动窗口
        seen = {}
        repeated = 0
        for i in range(len(self.lines) - 5):
            block = '\n'.join(self.lines[i:i + 5])
            bare = block.strip()
            if not bare or bare.startswith('#') or bare.startswith('import'):
                continue
            h = hash(bare)
            if h in seen and i - seen[h] > 5:
                repeated += 1
            else:
                seen[h] = i
        if repeated > 0:
            self._add_issue(
                f'发现 {repeated} 处重复代码块（≥5 行），建议提取为独立函数',
                'structure', repeated * 10
            )

    def _check_comments(self):
        """检测注释覆盖率和质量。"""
        total = len(self.lines)
        comment_lines = 0
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
                comment_lines += 1
        ratio = comment_lines / max(total, 1)
        if ratio < 0.02:
            self._add_issue('代码缺少注释，建议对关键逻辑添加说明', 'readability', 3)

    # ================================================================
    # 报告生成
    # ================================================================

    def _add_issue(self, message, category, penalty):
        self.issues.append({
            'message': message,
            'category': category,      # style / structure / readability / naming
            'severity': '高' if penalty >= 10 else '中' if penalty >= 5 else '低',
            'penalty': penalty,
        })
        self.score = max(0, self.score - penalty)

    def _generate_suggestions(self):
        """根据检测到的问题生成改进建议。"""
        if not self.issues:
            self.suggestions.append({
                'title': '代码质量良好',
                'detail': '未发现明显问题，继续保持！',
                'resource': None,
            })
            return

        for issue in self.issues:
            cat = issue['category']
            msg = issue['message']
            sug = {'title': '', 'detail': '', 'resource': None}

            if '过长' in msg:
                sug['title'] = '拆分长函数'
                sug['detail'] = '每个函数应只做一件事。若函数超过 50 行，将其中的逻辑块提取为独立的辅助函数。'
                sug['resource'] = '《重构：改善既有代码的设计》第 6 章 - 提炼函数'
            elif '嵌套' in msg:
                sug['title'] = '减少嵌套层级'
                sug['detail'] = '使用提前返回（early return）、提取子函数、或使用 guard clause 来降低嵌套深度。'
                sug['resource'] = '《代码整洁之道》第 3 章 - 函数'
            elif '魔法数字' in msg:
                sug['title'] = '消除魔法数字'
                sug['detail'] = '将字面量提取为命名常量（如 MAX_SIZE = 100），提高可读性和可维护性。'
                sug['resource'] = '《代码大全》第 12 章 - 命名常量'
            elif '命名' in msg:
                sug['title'] = '规范命名风格'
                sug['detail'] = f'{"Python" if self.language == "python" else "Java"} 命名规范：变量用 snake_case，类名用 PascalCase，常量用 UPPER_CASE。'
                sug['resource'] = 'PEP 8 命名规范 / Google Java Style Guide'
            elif '重复' in msg:
                sug['title'] = '消除重复代码'
                sug['detail'] = '出现两次及以上的相似代码块应提取为函数。DRY 原则：Don\'t Repeat Yourself。'
                sug['resource'] = '《重构》第 2 章 - 重复代码（Duplicated Code）'
            elif '注释' in msg:
                sug['title'] = '增加代码注释'
                sug['detail'] = '为关键算法、复杂业务逻辑、非显而易见的处理添加注释。好的注释解释"为什么"而不是"是什么"。'
                sug['resource'] = '《代码整洁之道》第 4 章 - 注释'

            self.suggestions.append(sug)

    def _build_report(self):
        return {
            'language': self.language,
            'total_lines': len(self.lines),
            'score': max(0, self.score),
            'grade': self._grade(self.score),
            'issues': self.issues,
            'suggestions': self.suggestions,
        }

    @staticmethod
    def _grade(score):
        if score >= 90:
            return 'A (优秀)'
        elif score >= 75:
            return 'B (良好)'
        elif score >= 60:
            return 'C (一般)'
        else:
            return 'D (需改进)'


def analyze_code(file_path, language='python'):
    """分析指定文件并返回报告。"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        source = f.read()
    analyzer = CodeAnalyzer(source, language)
    return analyzer.analyze()
