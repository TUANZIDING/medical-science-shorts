"""Narration script: scenes -> lines (Chinese voiceover + bilingual captions).

Each line is synthesized as one TTS clip; its measured duration drives both
the audio timeline and the caption timing, so captions stay in sync.
`cue` selects the illustration shown while the line is spoken.
"""

VOICE = "zh-CN-YunyangNeural"
RATE = "-7%"

SCENES = [
    {
        "id": "intro",
        "tag_zh": "",
        "tag_en": "",
        "palette": "dusk",
        "lines": [
            {"cue": "title",
             "zh": "不小心被生锈的钉子扎了一下，要不要去打一针破伤风？",
             "en": "Stepped on a rusty nail? Do you need a tetanus shot?"},
            {"cue": "title",
             "zh": "今天，用两分钟，把这件事说清楚。",
             "en": "Let's make it clear in two minutes."},
        ],
    },
    {
        "id": "what",
        "tag_zh": "什么是破伤风",
        "tag_en": "What is tetanus",
        "num": "01",
        "palette": "earth",
        "lines": [
            {"cue": "bacteria",
             "zh": "破伤风，是由一种叫破伤风梭菌的细菌引起的。",
             "en": "Tetanus is caused by a bacterium called Clostridium tetani."},
            {"cue": "sources",
             "zh": "它常藏在泥土、灰尘和生锈的物品上，会通过伤口进入身体。",
             "en": "It lives in soil, dust and on rusty objects, and enters the body through wounds."},
            {"cue": "nerves",
             "zh": "细菌产生的毒素会攻击神经，可能引起牙关紧闭和肌肉痉挛。",
             "en": "Its toxin attacks the nerves, and can cause lockjaw and muscle spasms."},
            {"cue": "wash",
             "zh": "破伤风并不常见，但后果严重。而且，光把伤口洗干净，有时并不够。",
             "en": "It's uncommon but serious. And cleaning the wound alone is sometimes not enough."},
        ],
    },
    {
        "id": "when",
        "tag_zh": "什么时候该打",
        "tag_en": "When to consider a shot",
        "num": "02",
        "palette": "night",
        "lines": [
            {"cue": "wounds1",
             "zh": "哪些情况，成年人应该考虑打一针呢？",
             "en": "So when should adults consider a shot?"},
            {"cue": "wounds2",
             "zh": "又深又脏的扎伤，比如被钉子、木刺扎进去；",
             "en": "Deep or dirty puncture wounds, like from nails or splinters;"},
            {"cue": "wounds3",
             "zh": "沾了泥土或铁锈的伤口；被动物咬伤；还有烧伤和烫伤。",
             "en": "wounds with soil or rust; animal bites; and burns."},
            {"cue": "timeline",
             "zh": "另外，还要看上一次打加强针是什么时候。",
             "en": "It also depends on when you had your last booster."},
            {"cue": "timeline10",
             "zh": "一般来说，成年人大约每十年加强一次；",
             "en": "Generally, adults get a routine booster about every 10 years;"},
            {"cue": "timeline5",
             "zh": "如果是较脏的伤口，距离上次已超过约五年，医生通常会建议补打。",
             "en": "for a dirty wound, if it's been more than ~5 years, doctors often advise one."},
            {"cue": "doctor",
             "zh": "从没打过、或者记不清的，也要告诉医生。具体请以当地医生的判断为准。",
             "en": "Never had it, or can't remember? Tell your doctor. Follow local medical advice."},
        ],
    },
    {
        "id": "why",
        "tag_zh": "为什么要打",
        "tag_en": "Why it matters",
        "num": "03",
        "palette": "teal",
        "lines": [
            {"cue": "shield",
             "zh": "疫苗能让身体提前产生抗体，预防破伤风毒素引起的疾病。",
             "en": "The vaccine helps your body make antibodies ahead of time, preventing disease from the toxin."},
            {"cue": "curve",
             "zh": "但这种保护会随时间慢慢减弱，加强针能让它保持在可靠的水平。",
             "en": "That protection fades over time; boosters keep it at a reliable level."},
            {"cue": "clock",
             "zh": "遇到高风险的伤口，及时处理、及时接种，才是关键。",
             "en": "After a high-risk wound, prompt care and a timely shot are what matter."},
        ],
    },
    {
        "id": "tips",
        "tag_zh": "注意事项",
        "tag_en": "Things to keep in mind",
        "num": "04",
        "palette": "dawn",
        "lines": [
            {"cue": "tip0",
             "zh": "最后，记住几个注意事项。",
             "en": "Finally, a few things to keep in mind."},
            {"cue": "tip1",
             "zh": "第一，受伤后，先用流动的清水冲洗伤口。",
             "en": "One: first rinse the wound under clean running water."},
            {"cue": "tip2",
             "zh": "第二，伤口深或者很脏，要尽快就医。",
             "en": "Two: deep or dirty wounds need prompt medical care."},
            {"cue": "tip3",
             "zh": "第三，记下自己上一次打针的时间。",
             "en": "Three: keep a record of when you last had the shot."},
            {"cue": "tip4",
             "zh": "第四，被动物咬伤，还要同时考虑狂犬病的预防。",
             "en": "Four: animal bites also need rabies consideration."},
            {"cue": "tip5",
             "zh": "第五，打针后局部酸痛或者轻微发热，是常见反应。",
             "en": "Five: soreness at the site or a mild fever is a common reaction."},
            {"cue": "tip6",
             "zh": "第六，有过敏史或者正在怀孕，请提前告诉医生。",
             "en": "Six: tell your doctor if you have allergies or are pregnant."},
            {"cue": "tip7",
             "zh": "最重要的是，不要自己判断“不用打”，交给医生来决定。",
             "en": "Above all, don't decide on your own that you don't need it. Let a doctor decide."},
        ],
    },
    {
        "id": "end",
        "tag_zh": "",
        "tag_en": "",
        "palette": "dusk",
        "lines": [
            {"cue": "end",
             "zh": "小小一针，守护安心。本视频仅供科普，具体请遵医嘱。",
             "en": "A small shot for peace of mind. For education only; follow your clinician."},
        ],
    },
]

# Silence (seconds) inserted around clips.
LEAD_IN = 2.6        # before the first line (title reveal)
GAP_LINE = 0.62      # between lines in the same scene
GAP_SCENE = 1.9      # between scenes (transition breathing room)
TAIL = 4.6           # after the last line (end card hold)
