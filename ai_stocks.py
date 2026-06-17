"""AI関連銘柄（インフラ含む）の定義とカテゴリ分類。"""

AI_STOCKS = {
    # --- AI半導体・製造装置 ---
    "6857": {"name": "アドバンテスト", "category": "半導体検査装置", "theme": "GPU検査需要"},
    "8035": {"name": "東京エレクトロン", "category": "半導体製造装置", "theme": "AI半導体製造"},
    "6146": {"name": "ディスコ", "category": "半導体加工装置", "theme": "GPU向け研削"},
    "6920": {"name": "レーザーテック", "category": "半導体検査装置", "theme": "EUV検査"},
    "6526": {"name": "ソシオネクスト", "category": "半導体設計", "theme": "カスタムAIチップ"},
    "6723": {"name": "ルネサスエレクトロニクス", "category": "半導体", "theme": "エッジAI"},
    "6963": {"name": "ローム", "category": "半導体", "theme": "パワー半導体"},
    "6981": {"name": "村田製作所", "category": "電子部品", "theme": "AI端末向け部品"},
    "6762": {"name": "TDK", "category": "電子部品", "theme": "データセンター向け"},
    "6594": {"name": "日本電産", "category": "モーター", "theme": "DC冷却ファン"},

    # --- AIインフラ・データセンター ---
    "9984": {"name": "ソフトバンクグループ", "category": "AI投資", "theme": "ARM/AI投資"},
    "9434": {"name": "ソフトバンク", "category": "通信・DC", "theme": "AI-DC構築"},
    "4689": {"name": "Zホールディングス", "category": "プラットフォーム", "theme": "LLM活用"},
    "3778": {"name": "さくらインターネット", "category": "クラウド・DC", "theme": "政府クラウド・GPU"},
    "9613": {"name": "NTTデータグループ", "category": "SIer", "theme": "企業向けAI導入"},
    "9432": {"name": "NTT", "category": "通信・DC", "theme": "IOWN/光AI"},
    "4755": {"name": "楽天グループ", "category": "プラットフォーム", "theme": "AI活用EC"},

    # --- AI電力インフラ ---
    "9501": {"name": "東京電力HD", "category": "電力", "theme": "DC向け電力需要"},
    "9502": {"name": "中部電力", "category": "電力", "theme": "DC向け電力"},
    "9503": {"name": "関西電力", "category": "電力", "theme": "DC向け電力"},
    "1605": {"name": "INPEX", "category": "エネルギー", "theme": "LNG/DC電源"},
    "6501": {"name": "日立製作所", "category": "重電", "theme": "送配電・DC構築"},
    "6502": {"name": "東芝", "category": "重電", "theme": "電力インフラ"},

    # --- AIソフトウェア・サービス ---
    "4385": {"name": "メルカリ", "category": "テック", "theme": "AI活用EC"},
    "3993": {"name": "PKSHA Technology", "category": "AIスタートアップ", "theme": "自然言語AI"},
    "4382": {"name": "HEROZ", "category": "AIスタートアップ", "theme": "将棋AI/BtoB-AI"},
    "5765": {"name": "AI CROSS", "category": "AIスタートアップ", "theme": "AIメッセージング"},
    "4259": {"name": "エクサウィザーズ", "category": "AIスタートアップ", "theme": "企業向けAI"},
    "5765": {"name": "AI CROSS", "category": "AIスタートアップ", "theme": "AIメッセージング"},
    "4169": {"name": "ENECHANGE", "category": "エネルギーテック", "theme": "EV充電AI"},
    "3655": {"name": "ブレインパッド", "category": "データ分析", "theme": "企業向けAI分析"},
    "4056": {"name": "ニューラルポケット", "category": "AIスタートアップ", "theme": "画像認識AI"},
    "5765": {"name": "AI CROSS", "category": "AIスタートアップ", "theme": "AIメッセージング"},
    "4414": {"name": "フレクト", "category": "IoT/AI", "theme": "IoT×AI"},

    # --- AIロボティクス ---
    "6954": {"name": "ファナック", "category": "FA・ロボット", "theme": "AIロボット"},
    "6861": {"name": "キーエンス", "category": "センサー・FA", "theme": "AI画像検査"},
    "6506": {"name": "安川電機", "category": "ロボット", "theme": "AIロボット制御"},
    "6324": {"name": "ハーモニック・ドライブ", "category": "精密減速機", "theme": "ロボット部品"},

    # --- AI自動運転 ---
    "7203": {"name": "トヨタ自動車", "category": "自動車", "theme": "自動運転AI"},
    "7267": {"name": "ホンダ", "category": "自動車", "theme": "自動運転AI"},
    "6758": {"name": "ソニーグループ", "category": "テック", "theme": "画像センサー/AI"},
    "7735": {"name": "SCREENホールディングス", "category": "半導体製造装置", "theme": "AI半導体洗浄"},
}

AI_CATEGORIES = sorted(set(s["category"] for s in AI_STOCKS.values()))

def get_ai_codes() -> list[str]:
    return sorted(AI_STOCKS.keys())

def get_ai_codes_by_category(category: str) -> list[str]:
    return sorted(code for code, info in AI_STOCKS.items() if info["category"] == category)
