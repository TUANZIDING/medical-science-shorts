# 辐射与骨骼肌：电离辐射如何损伤肌肉与它的微环境 / Ionizing radiation & skeletal muscle

A ~2¾-minute cinematic, bilingual (简体中文 + English captions) science-popularization short for
complete beginners, with a Mandarin neural-TTS voiceover. It explains how ionizing radiation
damages skeletal muscle **and its local microenvironment**, and lays out the underlying injury
cascade as a starting point for mechanism research. A small citation line appears on screen while
each cited finding is narrated, and a references card with DOIs closes the video.

Outputs:

- `radiation_muscle_bilingual_vo.mp4`: 1920×1080, 24 fps, H.264 + AAC 48 kHz stereo, voice
  normalized to -16 LUFS integrated, clean voice only (no music, no noise bed).
- `radiation_muscle_small.mp4` (not committed; built by `build.sh`): a chat-friendly copy under
  4 MB (1280×720, two-pass ~120 kbps video + 48 kbps audio).

> 本视频仅供科普，不构成医疗建议 / For education only. Not medical advice.

## How it is made

The pipeline is adapted from `exosomes/` (branch `cursor/exosomes-video-75f2`).

| File | Role |
| --- | --- |
| `script_data.py` | The narration script: scenes, lines (Chinese VO + zh/en captions), the visual cue per line, the optional `cite` key per line, an optional `say` override (TTS text when the caption contains symbols such as `→`), the verified reference list (`REFS`), voice, speaking rate and pause lengths. |
| `tts.py` | Synthesizes each line with **edge-tts** (`zh-CN-YunyangNeural`, rate -8%), resamples to 48 kHz (soxr), trims edge silence, de-clicks, levels every clip, places clips on a timeline, then masters to -16 LUFS (allpass phase rotation, 4×-oversampled lookahead limiter, static gain; true peak < -1.5 dBTP). Writes `build/voice.wav` and `build/timeline.json`. |
| `render.py` | Procedurally renders every frame (pycairo vector art + Pillow Noto CJK text): muscle cross-section with fibers, capillaries, satellite cells and fibroblasts; lengthwise myofibers with striations; wave-packet X/γ rays; atom ionization; DNA double helix with a double-strand break and repair proteins; ROS sparks; capillary endothelium undergoing apoptosis; capillary rarefaction/hypoxia/inflammation; fibroblast activation and collagen build-up; the 5-step cascade; research-direction cards; then a filmic grade, bloom, vignette and grain. Renders in parallel chunks with libx264. Writes `build/video.mp4`. |
| `build.sh` | Runs everything, muxes the final MP4, prints ffprobe info and measured loudness, then makes the < 4 MB 720p copy. |

Captions and citation lines are driven by the same `timeline.json` as the audio, so they stay in
sync with the narration by construction.

## Rebuild

Requirements: Python 3.10+, ffmpeg/ffprobe, network access (edge-tts uses Microsoft's online TTS).

```bash
sudo apt-get install -y ffmpeg fonts-noto-cjk python3-cairo
pip install edge-tts pillow numpy        # add --break-system-packages on Debian/Ubuntu

cd radiation-muscle
./build.sh                               # -> radiation_muscle_bilingual_vo.mp4 + radiation_muscle_small.mp4
TTS_ARGS=--force ./build.sh              # also re-synthesize cached TTS clips
python3 render.py --stills 30,60,100     # preview frames -> build/stills/
```

A full render takes roughly 10 minutes on 4 cores. `build/` holds intermediates and is not committed.

## Scenes

1. **Hook**: irradiated muscle fibers turn grey and fibrotic: 放疗之后很久…… 又僵 · 又弱 (stiff · weak).
2. **Title**: 辐射与骨骼肌, over a muscle cross-section (fibers, capillaries, satellite cells, fibroblasts).
3. **01 什么是电离辐射**: an X/γ ray knocks an electron out of an atom (ionization); DNA double-strand
   break and the DNA-damage response *[Jackson & Bartek, Nature 2009]*; water radiolysis → ROS that
   keep oxidative injury going after exposure *[Azzam et al., Cancer Lett 2012]*.
4. **02 肌纤维与卫星细胞**: myofibers lose striations; satellite cells (muscle stem cells) dim,
   "regeneration impaired"; zoom out to the niche (microvessels, fibroblasts, immune cells).
5. **03 周围的微环境**: capillary endothelial cells undergo apoptosis *[Paris et al., Science 2001,
   labelled on screen "mouse · intestine, not muscle · analogy for microvascular injury"]*;
   capillary loss → hypoxia → lingering inflammation; fibroblast activation (TGF-β signal), collagen
   deposition and a stiffness gauge (fibrosis); early damage → long remodeling → lasting change
   *[Bentzen, Nat Rev Cancer 2006]*; radiation fibrosis syndrome in survivors: stiffness, weakness,
   limited movement *[Stubblefield, PM&R 2011]*.
6. **04 底层逻辑**: the five-node cascade, lit node by node in sync with the voice: DNA & oxidative
   injury → cell death or senescence → stem-cell niche disrupted → vascular & inflammatory
   remodeling → fibrosis & lasting dysfunction.
7. **05 对机制研究的启示**: one fiber vs. the whole microenvironment; candidate research directions
   (oxidative stress, vascular repair, anti-fibrosis, stem-cell niche protection), labelled
   "research directions, not medical advice".
8. **06 理性看待**: dose, fractionation, irradiated volume and time since exposure change the
   outcome; animal ≠ human.
9. **End card**: 伤的是细胞，更是它的环境 + 本视频仅供科普 / For education only.
10. **References card**: the five citations below with DOI and PMID.

## Narration (中文旁白)

1. 放疗结束很久以后，有人发现照射过的肌肉，还是又僵又弱。这是为什么？
2. 今天用几分钟，讲清电离辐射怎样伤到骨骼肌，以及它周围的小环境。
3. 电离辐射，比如X射线、伽马射线，能量很高，能把分子里的电子打飞。
4. 结果之一，是DNA双链断裂；《自然》杂志上的综述强调，细胞必须启动一整套损伤应答来应对。
5. 同时，辐射还会产生大量活性氧，让氧化损伤拖得更久。
6. 对肌肉来说，肌纤维本身会受伤；负责修补肌肉的卫星细胞，再生能力也会变差。
7. 但故事不只发生在肌肉细胞里。
8. 周围的微血管内皮也可能先受损。《科学》上的小鼠实验提示：内皮细胞凋亡，可以成为辐射损伤的早期关键环节。
9. 毛细血管变少，局部缺氧，炎症拖着不走。
10. 成纤维细胞被激活，胶原越积越多，组织变硬，这就是纤维化。
11. 《自然·癌症评论》的综述把这类晚期副作用，概括成：早期损伤，经过漫长的组织重塑，留下永久改变。
12. 肿瘤幸存者里，辐射纤维化综合征可表现为肌肉僵硬、无力和活动受限。
13. 所以，底层逻辑可以记成一条链条：DNA与氧化损伤 → 细胞死亡或衰老 → 干细胞微环境被打乱 → 血管与炎症重塑 → 纤维化与长期功能障碍。
    (spoken as: …DNA与氧化损伤，导致细胞死亡或衰老，再到干细胞微环境被打乱，再到血管与炎症重塑，最后是纤维化与长期功能障碍。)
14. 以后做机制研究，不能只盯着一条肌纤维，而要看整个微环境。
15. 方向包括：氧化应激、血管修复、抗纤维化，以及干细胞龛的保护。
16. 要注意：剂量、分割方式、照射范围和伤后时间，都会改变结果；动物实验也不能简单等同于人体。
17. 一句话：电离辐射伤肌肉，伤的是细胞，更是它赖以生存的周围环境。本视频仅供科普。
18. 文中提到的研究，参考文献见屏幕。

## References

Each entry was checked against Crossref (title, journal, year, volume/pages, DOI) and PubMed (PMID,
abstract). The narration only states what each paper reports.

1. Jackson SP, Bartek J. The DNA-damage response in human biology and disease. *Nature*.
   2009;461(7267):1071-1078. doi:[10.1038/nature08467](https://doi.org/10.1038/nature08467). PMID 19847258.
   Used for: DNA double-strand breaks and the cellular DNA-damage response (general review, not
   radiation- or muscle-specific).
2. Azzam EI, Jay-Gerin JP, Pain D. Ionizing radiation-induced metabolic oxidative stress and
   prolonged cell injury. *Cancer Lett*. 2012;327(1-2):48-60.
   doi:[10.1016/j.canlet.2011.12.012](https://doi.org/10.1016/j.canlet.2011.12.012). PMID 22182453.
   Used for: water radiolysis and ROS; oxidative changes that persist after exposure.
3. Paris F, et al. Endothelial apoptosis as the primary lesion initiating intestinal radiation
   damage in mice. *Science*. 2001;293(5528):293-297.
   doi:[10.1126/science.1060191](https://doi.org/10.1126/science.1060191). PMID 11452123.
   **Animal-only (mouse), intestinal tissue, not muscle.** Used as an analogy for microvascular
   endothelial injury as an early, initiating lesion; the narration says "小鼠实验" and the screen
   says "mouse · intestine, not muscle".
4. Bentzen SM. Preventing or reducing late side effects of radiation therapy: radiobiology meets
   molecular pathology. *Nat Rev Cancer*. 2006;6(9):702-713.
   doi:[10.1038/nrc1950](https://doi.org/10.1038/nrc1950). PMID 16929324.
   Used for: late normal-tissue effects understood as damage recognition and tissue remodelling
   rather than only initial damage.
5. Stubblefield MD. Radiation fibrosis syndrome: neuromuscular and musculoskeletal complications in
   cancer survivors. *PM R*. 2011;3(11):1041-1054.
   doi:[10.1016/j.pmrj.2011.08.535](https://doi.org/10.1016/j.pmrj.2011.08.535). PMID 22108231.
   Used for: clinical radiation fibrosis syndrome in human survivors (muscle weakness and
   dysfunction, stiffness, restricted movement).

Statements without an on-screen citation (satellite cells as muscle stem cells with impaired
regeneration after irradiation, capillary loss and hypoxia, chronic inflammation, fibroblast
activation with TGF-β signalling and collagen deposition, the role of dose/fractionation/volume/time,
animal-to-human gaps) are general radiobiology knowledge, phrased conservatively. The "TGF-β" label
in the fibrosis scene reflects TGF-β1's well-established role as a central driver of radiation
fibrosis.
