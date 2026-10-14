"""Narration script: scenes -> lines (Chinese voiceover + bilingual captions).

Each line is synthesized as one TTS clip; its measured duration drives both
the audio timeline and the caption timing, so captions stay in sync.
`cue` selects the illustration shown while the line is spoken; `cite` is a key
into REFS and puts a citation line on screen while that line is spoken.
"""

VOICE = "zh-CN-YunyangNeural"
RATE = "-4%"

# Every entry verified against Crossref and PubMed (title, journal, year, DOI).
REFS = {
    "kalluri": {
        "short": "Kalluri & LeBleu, Science, 2020",
        "full": "Kalluri R, LeBleu VS. The biology, function, and biomedical applications of "
                "exosomes. Science. 2020;367(6478):eaau6977.",
        "doi": "10.1126/science.aau6977", "pmid": "32029601",
    },
    "welsh": {
        "short": "Welsh et al., J Extracell Vesicles, 2024 (MISEV2023)",
        "full": "Welsh JA, et al. Minimal information for studies of extracellular vesicles "
                "(MISEV2023): From basic to advanced approaches. J Extracell Vesicles. "
                "2024;13(2):e12404.",
        "doi": "10.1002/jev2.12404", "pmid": "38326288",
    },
    "valadi": {
        "short": "Valadi et al., Nat Cell Biol, 2007",
        "full": "Valadi H, et al. Exosome-mediated transfer of mRNAs and microRNAs is a novel "
                "mechanism of genetic exchange between cells. Nat Cell Biol. 2007;9(6):654-659.",
        "doi": "10.1038/ncb1596", "pmid": "17486113",
    },
    "hoshino": {
        "short": "Hoshino et al., Nature, 2015",
        "full": "Hoshino A, et al. Tumour exosome integrins determine organotropic metastasis. "
                "Nature. 2015;527(7578):329-335.",
        "doi": "10.1038/nature15756", "pmid": "26524530",
    },
    "melo": {
        "short": "Melo et al., Nature, 2015",
        "full": "Melo SA, et al. Glypican-1 identifies cancer exosomes and detects early "
                "pancreatic cancer. Nature. 2015;523(7559):177-182.",
        "doi": "10.1038/nature14581", "pmid": "26106858",
    },
    "alvarez": {
        "short": "Alvarez-Erviti et al., Nat Biotechnol, 2011",
        "full": "Alvarez-Erviti L, et al. Delivery of siRNA to the mouse brain by systemic "
                "injection of targeted exosomes. Nat Biotechnol. 2011;29(4):341-345.",
        "doi": "10.1038/nbt.1807", "pmid": "21423189",
    },
}
REF_ORDER = ("kalluri", "welsh", "valadi", "hoshino", "melo", "alvarez")

SCENES = [
    {
        "id": "intro", "tag_zh": "", "tag_en": "", "palette": "dusk",
        "lines": [
            {"cue": "title",
             "zh": "你知道吗？我们身体里的细胞，一直在互相“寄快递”。",
             "en": "Did you know? The cells in your body are always \"sending packages\" to each other."},
            {"cue": "title",
             "zh": "这些小包裹，就叫细胞外囊泡。",
             "en": "These little parcels are called extracellular vesicles."},
        ],
    },
    {
        "id": "what", "tag_zh": "什么是细胞外囊泡", "tag_en": "What are EVs", "num": "01",
        "palette": "night",
        "lines": [
            {"cue": "bubble",
             "zh": "细胞外囊泡，简称EV，是细胞释放的、裹着一层膜的微小泡泡，几乎所有细胞都会释放。",
             "en": "Extracellular vesicles (EVs) are tiny membrane-wrapped bubbles released by almost all cells."},
            {"cue": "scale",
             "zh": "外泌体是其中较小的一类，直径大约三十到一百五十纳米，比细胞小上百倍。",
             "en": "Exosomes are one small type: about 30–150 nm across, over a hundred times smaller than a cell."},
            {"cue": "mvb", "cite": "kalluri",
             "zh": "《科学》杂志上的一篇综述介绍：外泌体先在细胞内的“多囊泡体”里形成，再随它与细胞膜融合，被释放出去。",
             "en": "A review in Science describes how exosomes form inside multivesicular bodies, then get released when these fuse with the cell membrane."},
            {"cue": "types",
             "zh": "另外，还有从细胞膜直接鼓出来的微囊泡，和细胞凋亡时产生的凋亡小体。",
             "en": "There are also microvesicles, which bud straight off the cell membrane, and apoptotic bodies from dying cells."},
            {"cue": "misev", "cite": "welsh",
             "zh": "它们很难彼此分开，所以国际指南MISEV建议，统一使用“细胞外囊泡”这个总称。",
             "en": "They're hard to tell apart, so the international MISEV guidelines recommend the umbrella term \"EV\"."},
        ],
    },
    {
        "id": "cargo", "tag_zh": "包裹里装了什么", "tag_en": "What's inside", "num": "02",
        "palette": "teal",
        "lines": [
            {"cue": "cargo",
             "zh": "包裹里装着蛋白质、脂质，还有各种RNA，比如微小RNA。",
             "en": "Inside are proteins, lipids, and many kinds of RNA, such as microRNA."},
            {"cue": "valadi", "cite": "valadi",
             "zh": "2007年，《自然·细胞生物学》上的一项研究发现，外泌体能把RNA送进另一个细胞，并在那里继续发挥作用。",
             "en": "A 2007 study in Nature Cell Biology found exosomes can deliver RNA into another cell, where it still works."},
            {"cue": "message",
             "zh": "就像一封信，把消息从一个细胞带给另一个细胞。",
             "en": "Like a letter carrying a message from one cell to another."},
        ],
    },
    {
        "id": "role", "tag_zh": "它们做什么", "tag_en": "What they do", "num": "03",
        "palette": "earth",
        "lines": [
            {"cue": "health",
             "zh": "在健康的身体里，它们参与免疫信号的传递，也帮助组织修复。",
             "en": "In a healthy body, they help relay immune signals and support tissue repair."},
            {"cue": "tumor",
             "zh": "但在疾病中，它们也可能被肿瘤利用，为癌细胞的扩散铺路。",
             "en": "But in disease, tumors can exploit them to pave the way for cancer spread."},
            {"cue": "hoshino", "cite": "hoshino",
             "zh": "《自然》杂志上的一项研究，在小鼠实验中发现：肿瘤外泌体表面的“整合素”，会影响癌细胞更容易转移到肺还是肝。",
             "en": "A Nature study in mice found that integrins on tumor exosomes influence whether cancer tends to spread to the lung or the liver."},
        ],
    },
    {
        "id": "why", "tag_zh": "科学家为什么关注", "tag_en": "Why researchers care", "num": "04",
        "palette": "night",
        "lines": [
            {"cue": "biopsy",
             "zh": "囊泡带着来源细胞的“身份信息”，科学家希望从血液、尿液里找到它们来发现疾病，这叫“液体活检”。",
             "en": "EVs carry their parent cell's \"ID\", so scientists hope to detect disease from EVs in blood or urine: a \"liquid biopsy\"."},
            {"cue": "melo", "cite": "melo",
             "zh": "《自然》上的一项研究报道，带有GPC1蛋白的外泌体或许能提示早期胰腺癌；但后续研究结果不一，仍需验证。",
             "en": "A Nature study reported GPC1-positive exosomes might flag early pancreatic cancer, but later studies were mixed; it still needs validation."},
            {"cue": "deliver", "cite": "alvarez",
             "zh": "它们还可能成为送药的“快递车”：2011年《自然·生物技术》上的研究，给外泌体装上“导航标签”，把药物分子送进了小鼠大脑。",
             "en": "They may also deliver drugs: a 2011 Nature Biotechnology study gave exosomes a \"homing tag\" and delivered siRNA into mouse brains."},
            {"cue": "stem",
             "zh": "此外，干细胞来源的囊泡，也正在被研究用于组织再生。",
             "en": "Stem-cell-derived EVs are also being studied for tissue regeneration."},
        ],
    },
    {
        "id": "reality", "tag_zh": "理性看待", "tag_en": "A reality check", "num": "05",
        "palette": "dawn",
        "lines": [
            {"cue": "trials",
             "zh": "不过要冷静：大多数治疗用途，还停留在实验室研究或临床试验阶段。",
             "en": "But stay level-headed: most therapeutic uses are still in lab research or clinical trials."},
            {"cue": "beauty",
             "zh": "市面上打着“外泌体”旗号的美容、抗衰老项目，很多并未获得监管批准，要多加小心。",
             "en": "Many \"exosome\" beauty and anti-aging treatments on the market are not approved by regulators. Be cautious."},
            {"cue": "standard",
             "zh": "而且，怎样分离、测量、统一标准，至今仍是这个领域的难题。",
             "en": "And how to isolate, measure and standardize EVs is still a challenge for the field."},
        ],
    },
    {
        "id": "end", "tag_zh": "", "tag_en": "", "palette": "dusk",
        "lines": [
            {"cue": "end",
             "zh": "一句话总结：细胞外囊泡，就是细胞之间传递消息的“快递包裹”。本视频仅供科普。",
             "en": "In one sentence: EVs are the parcels cells use to send messages. For education only."},
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
LEAD_IN = 2.6        # before the first line (title reveal)
GAP_LINE = 0.55      # between lines in the same scene
GAP_SCENE = 1.7      # between scenes (transition breathing room)
TAIL = 9.0           # after the last line (references card hold)
