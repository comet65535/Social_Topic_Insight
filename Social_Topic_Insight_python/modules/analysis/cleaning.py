import re

class TextCleaner:
    @staticmethod
    def clean(text: str) -> str:
        if not text: return ""

        if re.match(r'^[\d\s\W_]+$', text):
            return ""
        
        # 1. URL -> 替换为空格 (防止前后词粘连)
        text = re.sub(r'(https?|ftp)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+', ' ', text)
        
        # 2. 处理 "回复@xxx:" -> 替换为空格
        text = re.sub(r'回复@.*?:', ' ', text)
        
        # 3. 处理 @用户 -> 替换为空格 (重要！防止 "A@B C" 变成 "AC")
        text = re.sub(r'@[\w\u4e00-\u9fa5]+', ' ', text)
        
        # 4. 处理话题 #话题# -> 替换为 " 话题 " (前后加空格，突出话题)
        text = re.sub(r'#([^#]+)#', r' \1 ', text)
        
        # 5. 中英文/数字之间加空格 (解决 CCTV1非遗 -> CCTV1 非遗)
        # 模式：[中文][英文数字] -> [中文] [英文数字]
        text = re.sub(r'([\u4e00-\u9fa5])([a-zA-Z0-9])', r'\1 \2', text)
        # 模式：[英文数字][中文] -> [英文数字] [中文]
        text = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fa5])', r'\1 \2', text)

        text = re.sub(r'(来源|视频|内容|全文|展开|查看|上热门|热门|vlog|日常|智搜)', '', text)

        # 6. 合并多余空格
        text = re.sub(r'\s+', ' ', text)

        if text.count('#') > 6:
            return ""

        if len(text.strip()) < 4:
            return ""
        
        return text.strip()