"""Multilingual stopwords for topic detection.

Contains common words in multiple languages that should be ignored
when tracking potential new topics. These are high-frequency words
that don't provide meaningful insights.
"""

from typing import FrozenSet

# English stopwords
ENGLISH_STOPWORDS = frozenset({
    # Articles and determiners
    "a", "an", "the", "this", "that", "these", "those",
    # Pronouns
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "who", "whom", "whose", "which", "what",
    # Prepositions
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "up", "down", "into", "out", "over", "under", "through",
    "about", "above", "below", "between", "around", "after", "before",
    # Conjunctions
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
    "not", "only", "also", "just", "than", "then", "when", "while",
    # Verbs (common)
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "could", "should", "may", "might", "must", "shall",
    "can", "need", "want", "get", "got", "make", "made", "let",
    "go", "going", "went", "gone", "come", "came", "coming",
    "see", "saw", "seen", "know", "knew", "known", "think", "thought",
    "say", "said", "tell", "told", "ask", "asked",
    # Adverbs
    "here", "there", "where", "when", "why", "how",
    "very", "really", "too", "more", "most", "less", "least",
    "now", "always", "never", "sometimes", "often", "usually",
    "still", "already", "again", "even", "ever",
    # Common words
    "yes", "no", "yeah", "yep", "nope", "okay", "ok", "sure",
    "well", "like", "just", "good", "bad", "new", "old",
    "some", "any", "all", "each", "every", "many", "much", "few",
    "other", "another", "same", "different",
    "one", "two", "three", "four", "five", "first", "last",
    "people", "person", "thing", "things", "time", "times",
    "way", "day", "days", "week", "month", "year",
    # Discord/chat specific
    "lol", "lmao", "lmfao", "rofl", "haha", "hehe", "hihi",
    "omg", "omfg", "wtf", "wth", "brb", "afk", "gtg", "ttyl",
    "idk", "idc", "imo", "imho", "tbh", "ngl", "smh", "fyi",
    "thanks", "thank", "thx", "please", "pls", "plz",
    "sorry", "hello", "hi", "hey", "bye", "goodbye", "cya",
    "nice", "cool", "awesome", "great", "wow", "damn", "dang",
})

# Japanese stopwords (hiragana particles and common words)
JAPANESE_STOPWORDS = frozenset({
    # Particles
    "は", "が", "を", "に", "へ", "で", "と", "の", "や", "か",
    "も", "ね", "よ", "な", "わ", "さ", "ぞ", "ぜ", "ば", "けど",
    # Common words
    "これ", "それ", "あれ", "この", "その", "あの",
    "ここ", "そこ", "あそこ", "どこ",
    "だれ", "なに", "いつ", "どう", "なぜ",
    "です", "ます", "だ", "である",
    "ある", "いる", "なる", "する", "できる",
    "ない", "ません",
    "という", "ように", "ために",
    "もう", "まだ", "また", "いつも", "たまに",
    "とても", "すごく", "ちょっと", "少し",
    "今", "今日", "明日", "昨日",
    # Chat expressions
    "うん", "ううん", "はい", "いいえ", "うーん",
    "ありがとう", "すみません", "ごめん",
    "おはよう", "こんにちは", "こんばんは", "おやすみ",
    "笑", "草", "ワロタ",
})

# Korean stopwords
KOREAN_STOPWORDS = frozenset({
    # Particles and endings
    "은", "는", "이", "가", "을", "를", "에", "에서", "로", "으로",
    "와", "과", "의", "도", "만", "부터", "까지",
    # Pronouns
    "나", "너", "저", "우리", "그", "그녀", "그것",
    "이것", "저것", "그것", "여기", "거기", "저기",
    # Common words
    "있다", "없다", "하다", "되다", "보다", "가다", "오다",
    "알다", "모르다", "같다", "다르다",
    "좋다", "나쁘다", "크다", "작다",
    "그리고", "하지만", "그러나", "또는", "그래서",
    "정말", "진짜", "너무", "많이", "조금",
    "지금", "오늘", "내일", "어제",
    # Chat expressions
    "네", "아니", "응", "ㅋㅋ", "ㅋㅋㅋ", "ㅎㅎ", "ㅎㅎㅎ",
    "ㅠㅠ", "ㅜㅜ", "감사", "고마워", "미안",
    "안녕", "안녕하세요",
})

# Chinese stopwords
CHINESE_STOPWORDS = frozenset({
    # Particles
    "的", "了", "和", "是", "在", "有", "不", "这", "那", "你",
    "我", "他", "她", "它", "们", "什么", "怎么", "为什么",
    # Common words
    "好", "很", "太", "也", "都", "就", "会", "能", "可以",
    "要", "想", "知道", "觉得", "看", "说", "做", "去", "来",
    "没有", "没", "还", "又", "再", "但是", "因为", "所以",
    "现在", "今天", "明天", "昨天",
    # Chat expressions
    "哈哈", "呵呵", "嘿嘿", "哦", "啊", "嗯", "好的", "谢谢",
    "不客气", "对不起", "没关系",
})

# Spanish stopwords
SPANISH_STOPWORDS = frozenset({
    # Articles and determiners
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    # Pronouns
    "yo", "tu", "usted", "el", "ella", "nosotros", "ustedes", "ellos", "ellas",
    "me", "te", "le", "nos", "les", "se",
    "mi", "tu", "su", "nuestro", "vuestro",
    "que", "quien", "cual", "donde", "cuando", "como", "porque",
    # Prepositions
    "de", "a", "en", "por", "para", "con", "sin", "sobre", "entre",
    # Conjunctions
    "y", "o", "pero", "sino", "aunque", "porque", "si", "ni",
    # Verbs (common)
    "ser", "estar", "tener", "hacer", "poder", "decir", "ir", "ver",
    "soy", "eres", "es", "somos", "son",
    "estoy", "estas", "esta", "estamos", "estan",
    "tengo", "tienes", "tiene", "tenemos", "tienen",
    "hay", "haber", "sido", "hecho",
    # Adverbs
    "no", "si", "muy", "mas", "menos", "bien", "mal",
    "ya", "todavia", "nunca", "siempre", "ahora", "hoy",
    # Common words
    "todo", "todos", "toda", "todas", "algo", "nada", "mucho", "poco",
    "otro", "otra", "otros", "otras", "mismo", "misma",
    # Chat expressions
    "jaja", "jajaja", "jejeje", "hola", "adios", "gracias", "porfa",
    "bueno", "vale", "ok", "claro",
})

# Portuguese stopwords
PORTUGUESE_STOPWORDS = frozenset({
    # Articles and determiners
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "este", "esta", "estes", "estas", "esse", "essa", "esses", "essas",
    # Pronouns
    "eu", "tu", "voce", "ele", "ela", "nos", "voces", "eles", "elas",
    "me", "te", "lhe", "nos", "vos", "lhes", "se",
    "meu", "teu", "seu", "nosso", "vosso",
    "que", "quem", "qual", "onde", "quando", "como", "porque",
    # Prepositions
    "de", "em", "por", "para", "com", "sem", "sobre", "entre", "ate",
    # Conjunctions
    "e", "ou", "mas", "porem", "embora", "porque", "se", "nem",
    # Verbs (common)
    "ser", "estar", "ter", "fazer", "poder", "dizer", "ir", "ver",
    "sou", "es", "e", "somos", "sao",
    "estou", "estas", "esta", "estamos", "estao",
    "tenho", "tens", "tem", "temos", "tem",
    "ha", "haver", "sido", "feito",
    # Adverbs
    "nao", "sim", "muito", "mais", "menos", "bem", "mal",
    "ja", "ainda", "nunca", "sempre", "agora", "hoje",
    # Common words
    "tudo", "todos", "toda", "todas", "algo", "nada", "muito", "pouco",
    "outro", "outra", "outros", "outras", "mesmo", "mesma",
    # Chat expressions
    "kkk", "kkkk", "haha", "hehe", "oi", "ola", "tchau", "obrigado", "brigado",
    "bom", "legal", "beleza", "blz",
})

# Combine all stopwords
STOPWORDS: FrozenSet[str] = (
    ENGLISH_STOPWORDS
    | JAPANESE_STOPWORDS
    | KOREAN_STOPWORDS
    | CHINESE_STOPWORDS
    | SPANISH_STOPWORDS
    | PORTUGUESE_STOPWORDS
)


def is_stopword(word: str) -> bool:
    """Check if a word is a stopword.

    Args:
        word: The word to check (will be lowercased).

    Returns:
        True if the word is a stopword, False otherwise.
    """
    return word.lower() in STOPWORDS
