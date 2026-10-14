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
# `model` is shown next to the on-screen citation so animal findings are always marked.
REFS = {
    "jackson": {
        "short": "Jackson & Bartek, Nature, 2009",
        "full": "Jackson SP, Bartek J. The DNA-damage response in human biology and disease. "
                "Nature. 2009;461(7267):1071-1078.",
        "doi": "10.1038/nature08467", "pmid": "19847258",
    },
    "cemazar": {
        "short": "Cemazar & Jurdana, Radiol Oncol, 2025 · 综述 review",
        "full": "Cemazar M, Jurdana M. Radiation-induced impairment of skeletal muscle regeneration. "
                "Radiol Oncol. 2025;59(3):293-300.",
        "doi": "10.2478/raon-2025-0048", "pmid": "40959925",
    },
    "scaramozza": {
        "short": "Scaramozza et al., Cell Stem Cell, 2019 · 小鼠 mouse",
        "full": "Scaramozza A, et al. Lineage tracing reveals a subset of reserve muscle stem cells "
                "capable of clonal expansion under stress. Cell Stem Cell. 2019;24(6):944-957.e5.",
        "doi": "10.1016/j.stem.2019.03.020", "pmid": "31006621",
    },
    "collao23": {
        "short": "Collao et al., J Cachexia Sarcopenia Muscle, 2023 · 小鼠 mouse",
        "full": "Collao N, et al. Radiation induces long-term muscle fibrosis and promotes a fibrotic "
                "phenotype in fibro-adipogenic progenitors. J Cachexia Sarcopenia Muscle. "
                "2023;14(5):2335-2349.",
        "doi": "10.1002/jcsm.13320", "pmid": "37671686",
    },
    "collao25": {
        "short": "Collao et al., Am J Physiol Cell Physiol, 2025 · 小鼠 mouse",
        "full": "Collao N, Johannsen EB, Just J, De Lisio M. Single-cell transcriptomic analysis "
                "reveals alterations to cellular dynamics and paracrine signaling in radiation-induced "
                "muscle pathology. Am J Physiol Cell Physiol. 2025;328(6):C1995-C2012.",
        "doi": "10.1152/ajpcell.00115.2025", "pmid": "40316295",
    },
    "zhou": {
        "short": "Zhou et al., Radiat Oncol, 2018 · 大鼠 rat",
        "full": "Zhou Y, et al. Radiation-induced muscle fibrosis rat model: establishment and "
                "valuation. Radiat Oncol. 2018;13(1):160.",
        "doi": "10.1186/s13014-018-1104-0", "pmid": "30157899",
    },
    "lee": {
        "short": "Lee et al., Radiat Res, 2025 · 恒河猴 rhesus macaque",
        "full": "Lee J, et al. Persistent postirradiation skeletal muscle protein and insulin "
                "sensitivity changes in nonhuman primates. Radiat Res. 2025;204(4):311-319.",
        "doi": "10.1667/RADE-23-00223.1", "pmid": "40053841",
    },
    "stubblefield": {
        "short": "Stubblefield, PM&R, 2011 · 临床 patients",
        "full": "Stubblefield MD. Radiation fibrosis syndrome: neuromuscular and musculoskeletal "
                "complications in cancer survivors. PM R. 2011;3(11):1041-1054.",
        "doi": "10.1016/j.pmrj.2011.08.535", "pmid": "22108231",
    },
}
REF_ORDER = ("jackson", "cemazar", "scaramozza", "collao23", "collao25", "zhou", "lee",
             "stubblefield")

SCENES = [
    {
        "id": "intro", "tag_zh": "", "tag_en": "", "palette": "dusk",
        "lines": [
            {"cue": "title",
             "zh": "电离辐射打到骨骼肌，损伤不只在肌纤维，更在它周围的微环境。",
             "en": "When ionizing radiation hits skeletal muscle, the damage is not only in the fibers, "
                   "but in the microenvironment around them."},
        ],
    },
    {
        "id": "dna", "tag_zh": "DNA损伤与活性氧", "tag_en": "DNA damage & ROS", "num": "01",
        "palette": "night",
        "lines": [
            {"cue": "dnaros", "cite": "jackson",
             "zh": "射线先损伤DNA，并产生大量活性氧，启动细胞的损伤应答。",
             "en": "Radiation first damages DNA and generates reactive oxygen species (ROS), "
                   "triggering the cell's damage response."},
            {"cue": "fate",
             "zh": "扛不住的细胞会死亡；扛住的往往进入衰老，长期分泌促炎、促纤维化信号。",
             "en": "Cells that can't cope die; those that survive often become senescent, releasing "
                   "pro-inflammatory, pro-fibrotic signals for a long time."},
        ],
    },
    {
        "id": "stem", "tag_zh": "卫星细胞", "tag_en": "Satellite cells", "num": "02",
        "palette": "earth",
        "lines": [
            {"cue": "fibers", "cite": "cemazar",
             "zh": "肌肉里的卫星细胞是再生的种子。辐射后，多数卫星细胞数量和功能下降。",
             "en": "Satellite cells are the seeds of muscle regeneration. After radiation, most "
                   "decline in number and function."},
            {"cue": "reserve", "cite": "scaramozza",
             "zh": "但有一小群储备卫星细胞，活性氧更低、更能扛过照射，还能重新补齐干细胞池。",
             "en": "But a small reserve subset, with lower ROS, survives irradiation better and can "
                   "refill the stem-cell pool."},
        ],
    },
    {
        "id": "fap", "tag_zh": "成纤维脂肪祖细胞", "tag_en": "Fibro-adipogenic progenitors",
        "num": "03", "palette": "teal",
        "lines": [
            {"cue": "fap", "cite": "collao23",
             "zh": "成纤维脂肪祖细胞（FAP）本应帮助修复；照射后它们更容易衰老，并转向纤维化表型。",
             "en": "Fibro-adipogenic progenitors (FAPs) normally support repair; after irradiation "
                   "they are more prone to senescence and shift to a fibrotic phenotype."},
            {"cue": "secretome", "cite": "collao23",
             "zh": "衰老的FAP释放的物质，还会抑制卫星细胞分化和融合，再生被卡住。",
             "en": "Factors released by senescent FAPs also inhibit satellite-cell differentiation "
                   "and fusion, so regeneration stalls."},
        ],
    },
    {
        "id": "remodel", "tag_zh": "衰老与纤维化", "tag_en": "Senescence & fibrosis", "num": "04",
        "palette": "night",
        "lines": [
            {"cue": "scseq", "cite": "collao25",
             "zh": "单细胞测序发现：照射后长时间内，各类肌内细胞都带着p21衰老标记。",
             "en": "Single-cell sequencing found that long after irradiation, many types of muscle-"
                   "resident cells carry the p21 senescence signature."},
            {"cue": "tgfb", "cite": "collao25",
             "zh": "巨噬细胞通过TGF-β信号推着FAP铺开瘢痕基质，纤维化由此固化。",
             "say": "巨噬细胞通过TGF贝塔信号推着FAP铺开瘢痕基质，纤维化由此固化。",
             "en": "Macrophages, via TGF-β signaling, push FAPs to lay down scar matrix, locking "
                   "fibrosis in."},
        ],
    },
    {
        "id": "vessel", "tag_zh": "血管与线粒体", "tag_en": "Vessels & mitochondria", "num": "05",
        "palette": "teal",
        "lines": [
            {"cue": "mito", "cite": "zhou",
             "zh": "电镜下还能看到线粒体肿胀、内皮细胞损伤，血管通透性升高。",
             "en": "Electron microscopy also shows swollen mitochondria, damaged endothelial cells "
                   "and leakier blood vessels."},
            {"cue": "monkey", "cite": "lee",
             "zh": "在恒河猴里，全身照射约四年后，肌肉仍有胰岛素抵抗和线粒体异常。",
             "en": "In rhesus macaques, about four years after whole-body irradiation, muscle still "
                   "shows insulin resistance and mitochondrial abnormalities."},
            {"cue": "clinic", "cite": "stubblefield",
             "zh": "临床上，这对应辐射纤维化综合征：僵硬、无力、活动受限。",
             "en": "Clinically, this corresponds to radiation fibrosis syndrome: stiffness, weakness "
                   "and limited movement."},
        ],
    },
    {
        "id": "logic", "tag_zh": "底层逻辑", "tag_en": "The underlying logic", "num": "06",
        "palette": "night",
        "lines": [
            {"cue": "cascade",
             "zh": "底层逻辑可以记成一条链：DNA与活性氧 → 死亡或衰老 → 干细胞与FAP龛位失衡 → 血管炎症重塑 → 纤维化。",
             "say": "底层逻辑可以记成一条链：DNA与活性氧，导致死亡或衰老，再到干细胞与FAP龛位失衡，再到血管炎症重塑，最后是纤维化。",
             "en": "The underlying logic is a chain: DNA & ROS → death or senescence → stem-cell & "
                   "FAP niche imbalance → vascular & inflammatory remodeling → fibrosis."},
        ],
    },
    {
        "id": "research", "tag_zh": "对机制研究的启示", "tag_en": "For mechanism research", "num": "07",
        "palette": "dawn",
        "lines": [
            {"cue": "directions",
             "zh": "做机制研究时，值得盯住：卫星细胞储备群、FAP衰老、巨噬细胞–TGF-β–FAP轴，以及长期线粒体与代谢改变。",
             "say": "做机制研究时，值得盯住：卫星细胞储备群、FAP衰老、巨噬细胞、TGF贝塔、FAP这条轴，以及长期线粒体与代谢改变。",
             "en": "For mechanism research, watch: the reserve satellite-cell pool, FAP senescence, "
                   "the macrophage–TGF-β–FAP axis, and long-term mitochondrial and metabolic change."},
            {"cue": "end",
             "zh": "理解这条链，是后续干预和实验设计的起点。",
             "en": "Understanding this chain is the starting point for future interventions and "
                   "experimental design."},
        ],
    },
    {
        "id": "refs", "tag_zh": "", "tag_en": "", "palette": "night",
        "lines": [
            {"cue": "refs",
             "zh": "本视频仅供科普，参考文献见屏幕。",
             "en": "For education only. References are on screen."},
        ],
    },
]

# Silence (seconds) inserted around clips.
LEAD_IN = 3.0        # before the first line (title reveal)
GAP_LINE = 0.75      # between lines in the same scene
GAP_SCENE = 2.3      # between scenes (transition breathing room)
TAIL = 11.0          # after the last line (references card hold)
