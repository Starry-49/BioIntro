# BioIntro - 生物信息学导论题库

基于 Transformer 语义检索与知识驱动的智能题库生成系统。

## 项目概述

BioIntro 是一个针对《生物信息学导论》课程的知识驱动题库系统，结合以下核心算法：

- **Transformer 语义嵌入**：使用 Sentence-Transformers 模型进行深层语义检索
- **多路混合检索**：BM25 (24%) + TF-IDF (18%) + RapidFuzz (12%) + Semantic (38%) + Type Bonus (8%)
- **图像近邻文字摘取**：从 PPTX 幻灯片中提取图像关联的标题、正文与备注文字
- **风格驱动生成**：基于旧题风格匹配，利用相似度打分机制生成新题

## 五大知识板块

| 板块 | 知识条目 | 来源 |
|------|---------|------|
| 引言及基因组信息学 | 411 | 6 个 PPTX |
| 转录组信息学 | 213 | 4 个 PPTX |
| 蛋白组信息学 | 186 | 4 个 PPTX |
| 生物分子网络 | 77 | 1 个 PPTX |
| 计算机辅助药物发现 | 75 | 2 个 PPTX |

## 项目结构

```
BioIntro/
├── functions/synquest/          # 核心 Python 模块
│   ├── knowledge_loader.py      # 多格式知识源加载与归一化
│   ├── question_engine.py       # 混合检索 + 风格驱动题目生成
│   ├── figure_track.py          # 图像题独立流水线
│   └── cli.py                   # 命令行接口
├── scripts/
│   ├── build_question_bank.py   # 从 previous.docx 构建题库
│   ├── build_knowledge_base.py  # 从 PPTX 幻灯片提取知识库
│   └── sync_generated_to_biointro.py  # 归一化与合并生成题
├── example/                     # GitHub Pages 静态站点
│   ├── index.html               # 首页
│   ├── practice.html            # 答题与生成页
│   ├── reader.html              # 知识阅读页
│   ├── assets/                  # CSS + JS
│   └── data/                    # 题库与知识库 JSON
├── setup.py                     # Python 包配置
└── requirements.txt             # 依赖
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 从幻灯片构建知识库
python scripts/build_knowledge_base.py

# 从旧题文档构建题库
python scripts/build_question_bank.py

# 使用 CLI 生成新题
python -m synquest synthesize \
  --kb example/data/knowledge-base/biointro-core.json \
  --style-bank example/data/question-bank.json \
  --count 20 --seed 42
```

## 核心算法

### 知识抽取
- OOXML ZIP 解析：直接解析 PPTX/DOCX 的 XML 结构
- 标题占位符检测：识别幻灯片标题 vs 正文
- 重复指纹去重：消除重复幻灯片
- 关键词加权提取：标题 ×3、摘要 ×2、正文 ×1

### 题目生成
- **BM25 检索**：Jieba 分词后的词汇级检索
- **TF-IDF 相似度**：n-gram 向量化 + 余弦相似度
- **RapidFuzz 模糊匹配**：token_set_ratio 提示去重
- **Semantic Embedding**：Sentence-Transformer 语义嵌入检索
- **答案签名匹配**：数值/命令/缩写/短语分类，确保选项一致性

### 质量过滤
- 提示长度检查
- OCR 噪声检测
- 焦点主题有效性验证
- 选项签名兼容性过滤

## GitHub Pages

访问 [https://starry-49.github.io/BioIntro/](https://starry-49.github.io/BioIntro/) 体验在线题库。

## License

MIT
