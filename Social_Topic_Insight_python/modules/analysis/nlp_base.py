import os
import re
import jieba
import jieba.posseg as pseg
import jieba.analyse
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import pipeline
from core.config import settings

class NLPProcessor:
    _instance = None
    
    # === 保持你的原始配置 ===
    EVENT_TRIGGERS = {
        "污染","排污","垃圾","异味","噪音",
        "关闭","闭馆","停业","封闭",
        "举报","投诉","爆料","曝光",
        "事故","受伤","死亡","火灾",
        "维权","抗议","强拆","冲突",
        "涨价","收费","罚款","塌房","烂尾","非遗","玉玉症","王者","王者荣耀","绝区零"
    }
    
    NEGATIVE_TRIGGERS = [
        "死亡", "身亡", "去世", "遇难", "尸体", 
        "事故", "惨案", "悲剧", "玩忽职守", "渎职",
        "烂尾", "跑路", "骗局", "受害者", "维权",
        "辐射", "污染", "致癌", "有毒", "塌房", "出轨"
    ]

    INVALID_POS = {"x", "u", "w", "c", "p", "o"}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        print(">>> [NLP Core] Initializing models and dictionaries...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        pipe_device = 0 if self.device == "cuda" else -1

        # 1. 加载 Embedding
        print(f">>> [NLP Core] Loading Embedding: {settings.EMBEDDING_MODEL}")
        #shibing624/text2vec-base-chinese 把中文句子变成向量
        self.embedder = SentenceTransformer(settings.EMBEDDING_MODEL, device=self.device) 

        # 2. 加载情感分析
        sentiment_model = "lxyuan/distilbert-base-multilingual-cased-sentiments-student"
        #情感分析模型,打分（判断是积极、消极还是中性）
        print(f">>> [NLP Core] Loading Sentiment: {sentiment_model}")
        try:
            self.sentiment_pipe = pipeline(
                "sentiment-analysis",
                model=sentiment_model,
                tokenizer=sentiment_model,
                device=pipe_device,
                top_k=None
            )
        except Exception as e:
            print(f"!!! Sentiment model failed to load: {e}")
            self.sentiment_pipe = None

        # 3. Jieba 初始化与字典加载
        jieba.initialize()
        self._load_userdicts()
        self._load_stopwords()
        print(">>> [NLP Core] Ready.")

    def _load_userdicts(self):
        base_dir = os.path.dirname(__file__)
        user_dict_path = os.path.join(base_dir, "user_dict.txt")
        # 你的补丁逻辑
        fix_words = [
            ("老年团", "n"), ("坐大巴", "v"), ("毛爷爷", "n"), 
            ("闭馆", "v"), ("污染", "vn"), ("监守自盗", "i"),
            ("秋后算账", "i"), ("霸王茶姬", "nz"), ("咖啡因", "n") ,("塌房" ,"v"),("UP主", "n")
        ]
        for w, t in fix_words:
            jieba.add_word(w, tag=t)
            
        if os.path.exists(user_dict_path):
            jieba.load_userdict(user_dict_path)

    def _load_stopwords(self):
        base_dir = os.path.dirname(__file__)
        files = ["stopwords.txt"]
        self.stopwords = set()
        for fname in files:
            path = os.path.join(base_dir, fname)
            if not os.path.exists(path): continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for ln in f:
                        w = ln.strip()
                        if w: self.stopwords.add(w)
            except Exception: pass
        
        # 你的硬编码补充
        self.stopwords |= {"的","了","在","是","我","有","和","就","不","人","都","一","一个","上","也","很","到","说","去","你","我们","他们","自己","什么","怎么","大家","或者"}

    def _generate_candidates(self, text: str, max_ngram=3):
        """
        生成候选词：正则强提取 + POS 组合 + N-gram
        【更新】增强了数词与单位/名词的绑定逻辑
        """
        candidates = set()

        # --- A. 强规则提取 (书名号、双引号、话题) ---
        titles = re.findall(r'《([^》]+)》', text)
        for t in titles: candidates.add(t)
            
        hashtags = re.findall(r'#([^#]+)#', text)
        for h in hashtags: candidates.add(h)

        # --- B. 基于分词的提取 ---
        words = list(pseg.cut(text))
        tokens = [w.word for w in words]
        flags = [w.flag for w in words]
        
        # 1. POS 组合规则 (核心修改区域)
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i+1]
            
            # 停用词检查：如果词在停用词表中，通常跳过
            # 但为了保留 "1人" 这种词（"人"可能是停用词），我们需要对数词组合网开一面
            # 逻辑：如果是数词组合，即使 w2 是通用量词(如"个")，也允许合并，后续 MMR 会根据权重筛选
            is_stop = (w1.word in self.stopwords or w2.word in self.stopwords)
            
            valid_combos = False
            
            # --- 原有逻辑 ---
            # n + eng (个税App)
            if w1.flag.startswith('n') and 'eng' in w2.flag: valid_combos = True
            if 'eng' in w1.flag and w2.flag.startswith('n'): valid_combos = True
            # v + m (超过100)
            if w1.flag.startswith('v') and w2.flag == 'm': valid_combos = True

            # --- 【新增】数词绑定逻辑 ---
            # 场景1：数词(m) + [量词(q) / 名词(n) / 时间(t) / 英文(eng)]
            # 例子：3月(m+t), 2周年(m+n), 1人(m+n), 5000万(m+m/n), 5G(m+eng)
            if w1.flag == 'm':
                if (w2.flag.startswith('q') or 
                    w2.flag.startswith('n') or 
                    w2.flag.startswith('t') or 
                    w2.flag == 'eng' or 
                    w2.flag == 'm'): # 允许 5000+万
                    valid_combos = True
                    # 特权：如果是数词绑定，忽略停用词限制 (例如 "3个" 虽然 "个" 是停用词，但组合起来有意义)
                    is_stop = False 

            # 场景2：[英文(eng) / 名词(n)] + 数词(m)
            # 例子：Top10, iPhone15, 阶段2
            if (w1.flag == 'eng' or w1.flag.startswith('n')) and w2.flag == 'm':
                valid_combos = True
                is_stop = False

            # 执行合并
            if valid_combos and not is_stop:
                candidates.add(w1.word + w2.word)

        # 2. Sliding N-grams (N-gram 逻辑保持不变)
        n_len = len(tokens)
        for L in range(1, max_ngram+1):
            for i in range(n_len - L + 1):
                seg = tokens[i:i+L]
                seg_flags = flags[i:i+L]
                
                skip = False
                for t in seg:
                    if t in self.stopwords: 
                        skip = True; break
                if skip: continue
                
                # 过滤掉单独的数词、量词等
                if L == 1:
                    # 单字数词(m)不提取，必须组合；eng也通常不单独提取除非很长
                    if seg_flags[0] in self.INVALID_POS or seg_flags[0] == 'm' or seg_flags[0] == 'eng':
                        continue
                else:
                    has_invalid = False
                    for f in seg_flags:
                        if f in self.INVALID_POS: has_invalid = True; break
                    if has_invalid: continue

                cand = "".join(seg)
                if cand.isdigit(): continue # 再次确保不提取纯数字
                if len(cand) <= 1: continue
                
                candidates.add(cand)

        # 3. 硬注入白名单事件词
        for trig in self.EVENT_TRIGGERS:
            if trig in text:
                candidates.add(trig)

        return list(candidates)

    def get_keywords(self, text: str, top_k: int = 5):
        """
        MMR 逻辑：生成 -> 排序 -> 多样性过滤
        (完全保留你的原始逻辑)
        """
        if not text or len(text) < 3: return []

        candidates = self._generate_candidates(text, max_ngram=3)

        if not candidates:
            tags = jieba.analyse.extract_tags(text, topK=top_k)
            return tags[:top_k]

        doc_emb = self.embedder.encode(text)
        cand_embs = self.embedder.encode(candidates)

        def cos_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        doc_sims = []
        for i, cand in enumerate(candidates):
            sim = cos_sim(cand_embs[i], doc_emb)
            if f"《{cand}》" in text:
                sim *= 1.5 
            doc_sims.append((cand, sim, cand_embs[i]))
        
        doc_sims.sort(key=lambda x: x[1], reverse=True)

        final_keywords = []
        final_embeddings = [] 
        
        for cand, sim, emb in doc_sims:
            if len(final_keywords) >= top_k: break
            
            if cand in self.stopwords: continue
            if cand.isdigit(): continue
            
            is_substring = False
            for exist in final_keywords:
                if cand in exist or exist in cand: 
                    is_substring = True; break
            if is_substring: continue

            is_redundant = False
            for exist_emb in final_embeddings:
                redundancy_score = cos_sim(emb, exist_emb)
                if redundancy_score > 0.89: 
                    is_redundant = True; break
            
            if is_redundant: continue

            final_keywords.append(cand)
            final_embeddings.append(emb)

        return final_keywords

    def get_sentiment(self, text: str) -> float:
        """混合情感分析 (保留死线逻辑)"""
        if not text: return 0.0

        for trigger in self.NEGATIVE_TRIGGERS:
            if trigger in text:
                return -0.95

        if self.sentiment_pipe is None: return 0.0
        
        try:
            results = self.sentiment_pipe(text[:510])[0]
            if isinstance(results, dict): results = [results]
            
            pos_score = 0.0
            neg_score = 0.0
            
            for r in results:
                label = str(r["label"]).lower()
                prob = r["score"]
                if "positive" in label: pos_score = prob
                elif "negative" in label: neg_score = prob
            
            final_score = pos_score - neg_score
            return round(final_score, 4)
        except Exception as e:
            print(f"Sentiment Error: {e}")
            return 0.0

    def get_embedding(self, text: str):
        if not text: return []
        return self.embedder.encode(text).tolist()