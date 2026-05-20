from typing import Set


def extract_product_categories_from_text(text: str) -> Set[str]:
    categories = set()
    text_lower = str(text).lower()

    category_keywords = {
        '蓝牙音箱': ['蓝牙', '音箱', '音响', '音频', '音乐', '播放', 'sound', 'speaker', 'bluetooth'],
        '抽纸': ['抽纸', '纸巾', '纸', 'tissue', 'paper', 'paper towel'],
        '服装': ['服装', '衣服', '裤子', '裙子', '上衣', '外套', 'clothing', 'fashion', 'apparel'],
        '食品': ['食品', '零食', '饮料', '吃', '喝', '美味', 'food', 'snack', 'drink'],
        '美妆': ['美妆', '化妆品', '护肤', '口红', '粉底', 'makeup', 'cosmetic', 'beauty'],
        '家居': ['家居', '家具', '装饰', '床', '沙发', 'home', 'furniture', 'decoration'],
        '数码': ['数码', '手机', '电脑', '平板', 'digital', 'phone', 'computer', 'tablet'],
        '运动': ['运动', '健身', '跑步', '瑜伽', 'sport', 'fitness', 'running', 'yoga'],
        '母婴': ['母婴', '婴儿', '宝宝', '奶粉', 'mother', 'baby', 'infant', 'milk powder'],
        '汽车': ['汽车', '车', '轮胎', '机油', 'car', 'auto', 'tire', 'oil']
    }

    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                categories.add(category)
                print(f"[语义验证] 在文本中发现类别关键词: '{keyword}' -> 类别 '{category}'")
                break

    brand_categories = {
        'morepure': '抽纸',
        'vinda': '抽纸',
        '心相印': '抽纸',
        '洁柔': '抽纸',
        'sony': '蓝牙音箱',
        'jbl': '蓝牙音箱',
        'bose': '蓝牙音箱',
        '小米': '数码',
        '华为': '数码',
        '苹果': '数码'
    }

    for brand, category in brand_categories.items():
        if brand in text_lower:
            categories.add(category)
            print(f"[语义验证] 在文本中发现品牌: '{brand}' -> 类别 '{category}'")

    return categories

