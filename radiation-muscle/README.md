# 辐射与骨骼肌：电离辐射如何损伤肌肉与它的微环境 / Ionizing radiation & skeletal muscle

A ~2½-minute cinematic, bilingual (简体中文 + English captions) science-popularization short for
complete beginners, with a Mandarin neural-TTS voiceover. It explains how ionizing radiation
damages skeletal muscle **and its local microenvironment**, and lays out the underlying injury
cascade (DNA damage & ROS → death or senescence → satellite-cell & FAP niche imbalance →
vascular & inflammatory remodeling → fibrosis) as a starting point for mechanism research.
Animal findings are labelled on screen with their model (mouse, rat, rhesus macaque). A small citation line appears on screen while
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
| `render.py` | Procedurally renders every frame (pycairo vector art + Pillow Noto CJK text): muscle cross-section niche; DNA double helix with a double-strand break, ROS sparks and repair proteins; cell fate (death vs. senescence with SASP); myofibers with satellite cells; reserve satellite cell clonally refilling the pool; FAP senescence and fibrotic shift; senescent-FAP secretome blocking myoblast fusion; scRNA-seq UMAP with p21 badges; macrophage → TGF-β → FAP → scar matrix; swollen mitochondria and a leaky capillary; rhesus-macaque 4-year timeline; radiation fibrosis syndrome; the 5-step cascade; mechanism cards; then a filmic grade, bloom, vignette and grain. Renders in parallel chunks with libx264. Writes `build/video.mp4`. |
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

1. **Title**: 辐射与骨骼肌 over a muscle cross-section (fibers, capillaries, satellite cells, FAPs).
2. **01 DNA损伤与活性氧**: a ray breaks both DNA strands, ROS spread, repair proteins gather
   *[Jackson & Bartek, Nature 2009]*; damaged cells either die or become senescent and keep releasing
   pro-inflammatory, pro-fibrotic signals.
3. **02 卫星细胞**: satellite cells on myofibers decline in number and function *[Cemazar & Jurdana,
   Radiol Oncol 2025, review]*; a reserve satellite cell with lower ROS survives and clonally refills the
   pool *[Scaramozza et al., Cell Stem Cell 2019, mouse lineage tracing]*.
4. **03 成纤维脂肪祖细胞**: FAPs turn senescent and fibrotic after irradiation (mouse, one hindlimb 16 Gy,
   fibrosis by day 56); their secretome blocks satellite-cell differentiation and fusion
   *[Collao et al., J Cachexia Sarcopenia Muscle 2023, mouse]*.
5. **04 衰老与纤维化**: scRNA-seq UMAP where every muscle-resident cluster gains a persistent p21
   badge; macrophage TGF-β drives FAPs to lay down scar matrix *[Collao et al., Am J Physiol Cell
   Physiol 2025, mouse]*.
6. **05 血管与线粒体**: swollen mitochondria and a leaky capillary under EM *[Zhou et al., Radiat Oncol
   2018, rat]*; insulin resistance and mitochondrial abnormalities ~4 years after whole-body
   irradiation *[Lee et al., Radiat Res 2025, rhesus macaque]*; radiation fibrosis syndrome in
   patients *[Stubblefield, PM&R 2011]*.
7. **06 底层逻辑**: the five-node cascade, lit node by node in sync with the voice.
8. **07 对机制研究的启示**: reserve satellite-cell pool, FAP senescence, macrophage–TGF-β–FAP axis,
   long-term mitochondrial/metabolic change ("research directions, not medical advice"); end card
   "理解这条链，是后续干预和实验设计的起点" with the cascade chips and 本视频仅供科普.
9. **References card**: the eight citations below with DOI and PMID.

## Narration (中文旁白)

1. 电离辐射打到骨骼肌，损伤不只在肌纤维，更在它周围的微环境。
2. 射线先损伤DNA，并产生大量活性氧，启动细胞的损伤应答。
3. 扛不住的细胞会死亡；扛住的往往进入衰老，长期分泌促炎、促纤维化信号。
4. 肌肉里的卫星细胞是再生的种子。辐射后，多数卫星细胞数量和功能下降。
5. 但有一小群储备卫星细胞，活性氧更低、更能扛过照射，还能重新补齐干细胞池。
6. 成纤维脂肪祖细胞（FAP）本应帮助修复；照射后它们更容易衰老，并转向纤维化表型。
7. 衰老的FAP释放的物质，还会抑制卫星细胞分化和融合，再生被卡住。
8. 单细胞测序发现：照射后长时间内，各类肌内细胞都带着p21衰老标记。
9. 巨噬细胞通过TGF-β信号推着FAP铺开瘢痕基质，纤维化由此固化。
10. 电镜下还能看到线粒体肿胀、内皮细胞损伤，血管通透性升高。
11. 在恒河猴里，全身照射约四年后，肌肉仍有胰岛素抵抗和线粒体异常。
12. 临床上，这对应辐射纤维化综合征：僵硬、无力、活动受限。
13. 底层逻辑可以记成一条链：DNA与活性氧 → 死亡或衰老 → 干细胞与FAP龛位失衡 → 血管炎症重塑 → 纤维化。
    (spoken as: …DNA与活性氧，导致死亡或衰老，再到干细胞与FAP龛位失衡，再到血管炎症重塑，最后是纤维化。)
14. 做机制研究时，值得盯住：卫星细胞储备群、FAP衰老、巨噬细胞–TGF-β–FAP轴，以及长期线粒体与代谢改变。
15. 理解这条链，是后续干预和实验设计的起点。
16. 本视频仅供科普，参考文献见屏幕。

## References

Each entry was checked against Crossref (title, journal, year, volume/pages, DOI) and PubMed (PMID).
Animal-only findings are marked.

1. Jackson SP, Bartek J. The DNA-damage response in human biology and disease. *Nature*.
   2009;461(7267):1071-1078. doi:[10.1038/nature08467](https://doi.org/10.1038/nature08467). PMID 19847258.
   Used for: DNA damage and the cellular DNA-damage response (general review).
2. Cemazar M, Jurdana M. Radiation-induced impairment of skeletal muscle regeneration. *Radiol Oncol*.
   2025;59(3):293-300. doi:[10.2478/raon-2025-0048](https://doi.org/10.2478/raon-2025-0048). PMID 40959925.
   Review. Used for: radiation lowers satellite-cell number and function.
3. Scaramozza A, et al. Lineage tracing reveals a subset of reserve muscle stem cells capable of clonal
   expansion under stress. *Cell Stem Cell*. 2019;24(6):944-957.e5.
   doi:[10.1016/j.stem.2019.03.020](https://doi.org/10.1016/j.stem.2019.03.020). PMID 31006621.
   **Mouse.** Used for: a minor Mx1+ reserve satellite-cell subset (low ROS, Pax3-high) that tolerates
   radiation and clonally repopulates the niche.
4. Collao N, et al. Radiation induces long-term muscle fibrosis and promotes a fibrotic phenotype in
   fibro-adipogenic progenitors. *J Cachexia Sarcopenia Muscle*. 2023;14(5):2335-2349.
   doi:[10.1002/jcsm.13320](https://doi.org/10.1002/jcsm.13320). PMID 37671686.
   **Mouse (juvenile, one hindlimb, 16 Gy).** Used for: fibrosis by day 56; loss of endothelial cells,
   FAPs and satellite cells; senescent, fibrotic FAPs whose secretome inhibits satellite-cell
   differentiation/fusion.
5. Collao N, Johannsen EB, Just J, De Lisio M. Single-cell transcriptomic analysis reveals alterations to
   cellular dynamics and paracrine signaling in radiation-induced muscle pathology. *Am J Physiol Cell
   Physiol*. 2025;328(6):C1995-C2012. doi:[10.1152/ajpcell.00115.2025](https://doi.org/10.1152/ajpcell.00115.2025).
   PMID 40316295. **Mouse, scRNA-seq.** Used for: persistent Cdkn1a (p21) senescence signature across
   muscle-resident cells; macrophage TGF-β → TGF-βR2 on FAPs, FAPs as the main ECM source.
6. Zhou Y, et al. Radiation-induced muscle fibrosis rat model: establishment and valuation. *Radiat
   Oncol*. 2018;13(1):160. doi:[10.1186/s13014-018-1104-0](https://doi.org/10.1186/s13014-018-1104-0).
   PMID 30157899. **Rat.** Used for: EM evidence of mitochondrial swelling, endothelial damage and
   increased vascular permeability (alongside rising TGF-β1 and fibrosis).
7. Lee J, et al. Persistent postirradiation skeletal muscle protein and insulin sensitivity changes in
   nonhuman primates. *Radiat Res*. 2025;204(4):311-319.
   doi:[10.1667/RADE-23-00223.1](https://doi.org/10.1667/RADE-23-00223.1). PMID 40053841.
   **Rhesus macaque (whole-body irradiation, ~4-year follow-up).** Used for: long-term muscle insulin
   resistance and mitochondrial dynamics changes.
8. Stubblefield MD. Radiation fibrosis syndrome: neuromuscular and musculoskeletal complications in
   cancer survivors. *PM R*. 2011;3(11):1041-1054.
   doi:[10.1016/j.pmrj.2011.08.535](https://doi.org/10.1016/j.pmrj.2011.08.535). PMID 22108231.
   **Human clinical review.** Used for: radiation fibrosis syndrome (stiffness, weakness, limited movement).

Removed from the previous version: Paris et al., Science 2001 (intestine, not muscle) and Azzam et al.,
Cancer Lett 2012; their roles are now covered by muscle-specific studies (refs 4–7). Bentzen, Nat Rev
Cancer 2006 is no longer cited on screen.
