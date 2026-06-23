code-plagiarism-detector
介绍
基于 AST（抽象语法树）的高校代码抄袭检测与学习辅助平台。

传统查重工具（MOSS、JPlag）依赖 token 序列的 n-gram 重叠度计算相似度，对变量重命名、循环等价替换等规避手段识别较弱。本平台的核心思路是：不比较代码"长什么样"，而是比较代码"做了什么"。

主要技术点包括：

多语言 AST 的标准化统一表示（Python / Java / C / C++ / JavaScript）
树编辑距离算法在查重场景下的工程化落地
大规模代码对的性能优化（漏斗式筛选策略）
交互式可视化图表与业务逻辑的联动（ECharts 热力图 + 力导向图）
PythonAnywhere 云部署环境下的兼容性适配
线上 Demo：https://xlllyyi.pythonanywhere.com

软件架构
├── app/ │ ├── models/ # SQLAlchemy 数据模型（User/Course/Assignment/Submission） │ ├── api/ # Flask 路由（RESTful API） │ ├── core/ │ │ ├── ast_parser/ # tree-sitter 多语言 AST 解析 + 标准化 │ │ ├── similarity/ # Jaccard + 树编辑距离 + 综合评分 │ │ └── learning/ # 重构建议 + 代码规范检测 │ ├── tasks/ # 异步查重任务 │ └── utils/ # 通用工具 ├── frontend/ │ ├── templates/ # HTML 模板 │ └── static/ # CSS / JS / ECharts ├── tests/ # pytest 单元测试 └── run.py # 项目启动入口

技术栈：Python 3.10+ / Flask / SQLAlchemy / SQLite / tree-sitter / ECharts

安装教程
克隆仓库
git clone https://gitee.com/xiangleyi/code-plagiarism-detector.git
cd code-plagiarism-detector


安装依赖

bash
pip install -r requirements.txt
初始化数据库

bash
python run.py init-db
启动服务

bash
python run.py

使用说明
管理员：默认账号 admin / admin123，可创建课程、管理用户、配置系统参数

教师：创建作业 → 设置截止日期和相似度阈值 → 学生提交后一键发起查重 → 查看热力图/力导向图/双栏对比视图

学生：提交代码 → 查看个人查重报告 → 接收重构建议和学习资源推荐
