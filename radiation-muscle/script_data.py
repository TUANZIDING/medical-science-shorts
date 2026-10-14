"""Narration script: scenes -> lines (Chinese voiceover + bilingual captions).

Each line is synthesized as one TTS clip; its measured duration drives both
the audio timeline and the caption timing, so captions stay in sync.
`cue` selects the illustration shown while the line is spoken; `cite` is a key
into REFS and puts a citation line on screen while that line is spoken.
`say` (optional) overrides the text sent to TTS when the caption contains
symbols that should not be read literally.
"""

VOICE = "zh-CN-YunyangNeural"
RATE = "-8%"

# Every entry verified against Crossref and PubMed (title, journal, year, DOI, PMID).
REFS = {
    "jackson": {
        "short": "Jackson & Bartek, Nature, 2009",
        "full": "Jackson SP, Bartek J. The DNA-damage response in human biology and disease. "
                "Nature. 2009;461(7267):1071-1078.",
        "doi": "10.1038/nature08467", "pmid": "19847258",
    },
    "azzam": {
        "short": "Azzam et al., Cancer Lett, 2012",
        "full": "Azzam EI, Jay-Gerin JP, Pain D. Ionizing radiation-induced metabolic oxidative "
                "stress and prolonged cell injury. Cancer Lett. 2012;327(1-2):48-60.",
        "doi": "10.1016/j.canlet.2011.12.012", "pmid": "22182453",
    },
    "paris": {
        "short": "Paris et al., Science, 2001 · 小鼠肠道 mouse intestine",
        "full": "Paris F, et al. Endothelial apoptosis as the primary lesion initiating intestinal "
                "radiation damage in mice. Science. 2001;293(5528):293-297.",
        "doi": "10.1126/science.1060191", "pmid": "11452123",
    },
    "bentzen": {
        "short": "Bentzen, Nat Rev Cancer, 2006",
        "full": "Bentzen SM. Preventing or reducing late side effects of radiation therapy: "
                "radiobiology meets molecular pathology. Nat Rev Cancer. 2006;6(9):702-713.",
        "doi": "10.1038/nrc1950", "pmid": "16929324",
    },
    "stubblefield": {
        "short": "Stubblefield, PM&R, 2011",
        "full": "Stubblefield MD. Radiation fibrosis syndrome: neuromuscular and musculoskeletal "
                "complications in cancer survivors. PM R. 2011;3(11):1041-1054.",
        "doi": "10.1016/j.pmrj.2011.08.535", "pmid": "22108231",
    },
}
REF_ORDER = ("jackson", "azzam", "paris", "bentzen", "stubblefield")

SCENES = [
    {
        "id": "intro", "tag_zh": "", "tag_en": "", "palette": "dusk",
        "lines": [
            {"cue": "hook",
             "zh": "放疗结束很久以后，有人发现照射过的肌肉，还是又僵又弱。这是为什么？",
             "en": "Long after radiotherapy ends, some people find the irradiated muscle still stiff and weak. Why?"},
            {"cue": "title",
             "zh": "今天用几分钟，讲清电离辐射怎样伤到骨骼肌，以及它周围的小环境。",
             "en": "In a few minutes: how ionizing radiation injures skeletal muscle and its local microenvironment."},
        ],
    },
    {
        "id": "what", "tag_zh": "什么是电离辐射", "tag_en": "Ionizing radiation", "num": "01",
        "palette": "night",
        "lines": [
            {"cue": "ionize",
             "zh": "电离辐射，比如X射线、伽马射线，能量很高，能把分子里的电子打飞。",
             "en": "Ionizing radiation, like X-rays and gamma rays, carries enough energy to knock electrons out of molecules."},
            {"cue": "dsb", "cite": "jackson",
             "zh": "结果之一，是DNA双链断裂；《自然》杂志上的综述强调，细胞必须启动一整套损伤应答来应对。",
             "en": "One result is DNA double-strand breaks; a Nature review stresses that cells must mount a whole damage response."},
            {"cue": "ros", "cite": "azzam",
             "zh": "同时，辐射还会产生大量活性氧，让氧化损伤拖得更久。",
             "en": "Radiation also generates reactive oxygen species (ROS), which prolong oxidative injury."},
        ],
    },
    {
        "id": "muscle", "tag_zh": "肌纤维与卫星细胞", "tag_en": "Fibers & satellite cells", "num": "02",
        "palette": "earth",
        "lines": [
            {"cue": "fibers",
             "zh": "对肌肉来说，肌纤维本身会受伤；负责修补肌肉的卫星细胞，再生能力也会变差。",
             "en": "In muscle, the fibers themselves are injured, and satellite cells, the muscle's repair stem cells, regenerate less well."},
            {"cue": "beyond",
             "zh": "但故事不只发生在肌肉细胞里。",
             "en": "But the story doesn't stop at the muscle cells."},
        ],
    },
    {
        "id": "niche", "tag_zh": "周围的微环境", "tag_en": "The microenvironment", "num": "03",
        "palette": "teal",
        "lines": [
            {"cue": "vessel", "cite": "paris",
             "zh": "周围的微血管内皮也可能先受损。《科学》上的小鼠实验提示：内皮细胞凋亡，可以成为辐射损伤的早期关键环节。",
             "en": "The surrounding microvascular endothelium may be hit early. A Science study in mice suggests endothelial apoptosis can be a key early step in radiation injury."},
            {"cue": "hypoxia",
             "zh": "毛细血管变少，局部缺氧，炎症拖着不走。",
             "en": "Capillaries thin out, the tissue becomes hypoxic, and inflammation lingers."},
            {"cue": "fibrosis",
             "zh": "成纤维细胞被激活，胶原越积越多，组织变硬，这就是纤维化。",
             "en": "Fibroblasts activate, collagen piles up and the tissue stiffens. That is fibrosis."},
            {"cue": "remodel", "cite": "bentzen",
             "zh": "《自然·癌症评论》的综述把这类晚期副作用，概括成：早期损伤，经过漫长的组织重塑，留下永久改变。",
             "en": "A Nature Reviews Cancer review frames such late effects as early damage followed by long tissue remodeling that leaves lasting change."},
            {"cue": "clinic", "cite": "stubblefield",
             "zh": "肿瘤幸存者里，辐射纤维化综合征可表现为肌肉僵硬、无力和活动受限。",
             "en": "In cancer survivors, radiation fibrosis syndrome can show up as muscle stiffness, weakness and limited movement."},
        ],
    },
    {
        "id": "logic", "tag_zh": "底层逻辑", "tag_en": "The underlying logic", "num": "04",
        "palette": "night",
        "lines": [
            {"cue": "cascade",
             "zh": "所以，底层逻辑可以记成一条链条：DNA与氧化损伤 → 细胞死亡或衰老 → 干细胞微环境被打乱 → 血管与炎症重塑 → 纤维化与长期功能障碍。",
             "say": "所以，底层逻辑可以记成一条链条：DNA与氧化损伤，导致细胞死亡或衰老，再到干细胞微环境被打乱，再到血管与炎症重塑，最后是纤维化与长期功能障碍。",
             "en": "So the logic is a chain: DNA & oxidative injury → cell death or senescence → stem-cell niche disrupted → vascular & inflammatory remodeling → fibrosis & lasting dysfunction."},
        ],
    },
    {
        "id": "research", "tag_zh": "对机制研究的启示", "tag_en": "For mechanism research", "num": "05",
        "palette": "dawn",
        "lines": [
            {"cue": "whole",
             "zh": "以后做机制研究，不能只盯着一条肌纤维，而要看整个微环境。",
             "en": "Mechanism research shouldn't look at a single fiber alone, but at the whole microenvironment."},
            {"cue": "directions",
             "zh": "方向包括：氧化应激、血管修复、抗纤维化，以及干细胞龛的保护。",
             "en": "Research directions include oxidative stress, vascular repair, anti-fibrosis, and protecting the stem-cell niche."},
        ],
    },
    {
        "id": "reality", "tag_zh": "理性看待", "tag_en": "A reality check", "num": "06",
        "palette": "earth",
        "lines": [
            {"cue": "reality",
             "zh": "要注意：剂量、分割方式、照射范围和伤后时间，都会改变结果；动物实验也不能简单等同于人体。",
             "en": "Note: dose, fractionation, irradiated volume and time since exposure all change the outcome, and animal results don't simply equal humans."},
        ],
    },
    {
        "id": "end", "tag_zh": "", "tag_en": "", "palette": "dusk",
        "lines": [
            {"cue": "end",
             "zh": "一句话：电离辐射伤肌肉，伤的是细胞，更是它赖以生存的周围环境。本视频仅供科普。",
             "en": "In one sentence: radiation injures not just muscle cells, but the environment they depend on. For education only."},
        ],
    },
    {
        "id": "refs", "tag_zh": "", "tag_en": "", "palette": "night",
        "lines": [
            {"cue": "refs",
             "zh": "文中提到的研究，参考文献见屏幕。",
             "en": "References for the studies mentioned are on screen."},
        ],
    },
]

# Silence (seconds) inserted around clips.
LEAD_IN = 3.0        # before the first line (title reveal)
GAP_LINE = 0.75      # between lines in the same scene
GAP_SCENE = 2.3      # between scenes (transition breathing room)
TAIL = 10.0          # after the last line (references card hold)
