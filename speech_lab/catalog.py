"""The page's fixed choices: the test sentences, suggested instructions to start from, OmniVoice's voice attributes, and the recognizer's languages."""

TEST_SENTENCES = {
    "English": "Xi Jinping is playing in the World Series against Giannis Antetokounmpo and Nikola Jokic for $200,000 at the Superdome on CBS News, sponsored by NVidia.",
    "Mixed": "习近平在World Series上对阵Giannis Antetokounmpo和Nikola Jokic，奖金二十万美元，比赛在Superdome举行，由CBS News转播，NVidia赞助。",
    "Chinese": "习近平正在超级巨蛋参加世界大赛，与扬尼斯·阿德托昆博和尼古拉·约基奇争夺二十万美元奖金，比赛由哥伦比亚广播公司新闻台转播，英伟达赞助。",
}
STYLE_SUGGESTIONS = [
    "Very happy and excited.",
    "Calm, slow and soothing.",
    "A serious evening news anchor.",
    "Shouting like an excited sports announcer calling the final play.",
    "Whispering, as if telling a secret.",
    "Sad and tired, almost sighing.",
    "Dry and sarcastic.",
    "用新闻主播的语气，正式而清晰。",
]
VOICE_DESCRIPTIONS = [
    "A middle-aged man with a thick Scottish accent, warm and gravelly.",
    "A young woman with a crisp British RP accent, reading the news like a BBC presenter.",
    "An older man with a slow, easygoing Texas drawl.",
    "A young Australian woman, upbeat and friendly.",
    "An energetic American sports commentator, loud and fast.",
    "A soft-spoken Irish grandmother telling a bedtime story.",
    "A fast-talking, brash New York cab driver.",
    "A friendly young man with an Indian English accent.",
    "一位声音浑厚的中年男性新闻主播，普通话标准，语速平稳。",
    "一位活泼的年轻女性，带着轻微的台湾口音。",
]
# OmniVoice understands only these attributes, at most one from each category. English accents apply to English text and Chinese dialects to
# Chinese text.
OMNIVOICE_ATTRIBUTES = {
    "gender": ["male", "female"],
    "age": ["child", "teenager", "young adult", "middle-aged", "elderly"],
    "pitch": ["very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"],
    "style": ["whisper"],
    "English accent": [
        "american accent",
        "british accent",
        "australian accent",
        "canadian accent",
        "indian accent",
        "chinese accent",
        "korean accent",
        "japanese accent",
        "portuguese accent",
        "russian accent",
    ],
    "Chinese dialect": ["河南话", "陕西话", "四川话", "贵州话", "云南话", "桂林话", "济南话", "石家庄话", "甘肃话", "宁夏话", "青岛话", "东北话"],
}
OMNIVOICE_NONVERBAL_TAGS = [
    "[laughter]",
    "[sigh]",
    "[confirmation-en]",
    "[question-en]",
    "[question-ah]",
    "[question-oh]",
    "[question-ei]",
    "[question-yi]",
    "[surprise-ah]",
    "[surprise-oh]",
    "[surprise-wa]",
    "[surprise-yo]",
    "[dissatisfaction-hnn]",
]
OMNIVOICE_LANGUAGES = {"": "detect", "en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "de": "German", "fr": "French", "es": "Spanish", "ru": "Russian"}
RECOGNIZER_LANGUAGES = [
    "Chinese",
    "English",
    "Cantonese",
    "Arabic",
    "German",
    "French",
    "Spanish",
    "Portuguese",
    "Indonesian",
    "Italian",
    "Korean",
    "Russian",
    "Thai",
    "Vietnamese",
    "Japanese",
    "Turkish",
    "Hindi",
    "Malay",
    "Dutch",
    "Swedish",
    "Danish",
    "Finnish",
    "Polish",
    "Czech",
    "Filipino",
    "Persian",
    "Greek",
    "Romanian",
    "Hungarian",
    "Macedonian",
]


def catalog() -> dict:
    return {
        "test_sentences": TEST_SENTENCES,
        "style_suggestions": STYLE_SUGGESTIONS,
        "voice_descriptions": VOICE_DESCRIPTIONS,
        "omnivoice_attributes": OMNIVOICE_ATTRIBUTES,
        "omnivoice_nonverbal_tags": OMNIVOICE_NONVERBAL_TAGS,
        "omnivoice_languages": OMNIVOICE_LANGUAGES,
        "recognizer_languages": RECOGNIZER_LANGUAGES,
    }
