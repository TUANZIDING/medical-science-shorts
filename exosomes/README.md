# 细胞外囊泡与外泌体：细胞之间的“快递包裹” / Extracellular vesicles & exosomes

A ~2¾-minute cinematic, bilingual (简体中文 + English captions) science-popularization
short for complete beginners, with a Mandarin neural-TTS voiceover. Key findings are backed
by peer-reviewed papers; a small citation line appears on screen while each one is narrated,
and a references card with DOIs closes the video.

Outputs:

- `exosomes_bilingual_vo.mp4`: 1920×1080, 24 fps, H.264 + AAC 48 kHz stereo, voice
  normalized to -16 LUFS integrated, clean voice only (no music, no noise bed).
- `exosomes_small.mp4` (not committed; built by `build.sh`): a chat-friendly copy under 4 MB
  (1280×720, two-pass ~120 kbps video + 48 kbps audio).

> 本视频仅供科普 / For education only.

## How it is made

The pipeline is the same as `tetanus-shot/`.

| File | Role |
| --- | --- |
| `script_data.py` | The narration script: scenes, lines (Chinese VO + zh/en captions), the visual cue per line, the optional `cite` key per line, the verified reference list (`REFS`), voice, speaking rate and pause lengths. Edit this to change the content. |
| `tts.py` | Synthesizes each line with **edge-tts** (`zh-CN-YunyangNeural`), resamples to 48 kHz (soxr), trims edge silence, de-clicks, levels every clip to the same loudness, places clips on a timeline, then masters to -16 LUFS (allpass phase rotation, 4×-oversampled lookahead limiter, static gain; true peak < -1.5 dBTP). Writes `build/voice.wav` and `build/timeline.json`. |
| `render.py` | Procedurally renders every frame (pycairo vector art + Pillow Noto CJK text): graded gradient backgrounds with drifting bokeh and dust motes, glowing line-art cells and vesicles (lipid bilayer, multivesicular body fusion, organ icons), soft wipe text reveals, light-leak scene transitions, then a filmic grade (S-curve + split tone), bloom, vignette and film grain. Renders in parallel chunks and encodes with libx264. Writes `build/video.mp4`. |
| `build.sh` | Runs everything, muxes the final MP4, prints ffprobe info and measured loudness, then makes the < 4 MB 720p copy. |

Captions and citation lines are driven by the same `timeline.json` as the audio (each one
appears with its own TTS clip), so they stay in sync with the narration by construction.

## Rebuild

Requirements: Python 3.10+, ffmpeg/ffprobe, network access (edge-tts calls Microsoft's
online neural TTS service).

```bash
sudo apt-get install -y ffmpeg fonts-noto-cjk python3-cairo
pip install edge-tts pillow numpy        # add --break-system-packages on Debian/Ubuntu

cd exosomes
./build.sh                               # -> exosomes_bilingual_vo.mp4 + exosomes_small.mp4
TTS_ARGS=--force ./build.sh              # also re-synthesize cached TTS clips
```

Preview individual frames without a full render:

```bash
python3 tts.py                           # needed once for build/timeline.json
python3 render.py --stills 5,30,87,160   # -> build/stills/t_XXX.XX.png
```

A full render takes roughly 10–15 minutes on 4 cores. `build/` holds intermediates and is not committed.

## Scenes

1. **Title**: 细胞外囊泡 与外泌体：细胞之间的“快递包裹”. Two cells pass vesicles back and forth.
2. **01 什么是细胞外囊泡**: a cell sheds membrane bubbles; size comparison (cell ≥ ~10 µm vs. exosome
   ~30–150 nm, zoom callout); biogenesis animation (vesicles form inside a multivesicular body,
   which moves to and fuses with the plasma membrane) *[Kalluri & LeBleu, Science 2020]*; the EV
   family (exosomes, microvesicles, apoptotic bodies); MISEV umbrella term "EV" *[Welsh et al.,
   JEV 2024]*.
3. **02 包裹里装了什么**: vesicle cutaway with lipid bilayer, membrane proteins and RNA; one cell's
   vesicle delivers RNA that works in a receiving cell *[Valadi et al., Nat Cell Biol 2007]*;
   "a letter between cells".
4. **03 它们做什么**: immune signaling and tissue repair; tumor exosomes and organotropic metastasis
   (integrins steering lung vs. liver, in mice) *[Hoshino et al., Nature 2015]*.
5. **04 科学家为什么关注**: liquid biopsy from blood/urine; GPC1-positive exosomes and early
   pancreatic cancer, with the "later studies mixed, needs validation" caveat *[Melo et al.,
   Nature 2015]*; targeted exosomes delivering siRNA to the mouse brain *[Alvarez-Erviti et al.,
   Nat Biotechnol 2011]*; stem-cell-derived EVs for regeneration research.
6. **05 理性看待**: most therapies are still at the lab or clinical-trial stage; many "exosome"
   beauty/anti-aging products are not approved; isolation, measurement and standardization are
   still open problems.
7. **End card**: 一句话总结：细胞之间的“快递包裹” + 本视频仅供科普 / For education only.
8. **References card**: the six citations below with DOI and PMID.

## Narration (中文旁白)

1. 你知道吗？我们身体里的细胞，一直在互相“寄快递”。
2. 这些小包裹，就叫细胞外囊泡。
3. 细胞外囊泡，简称EV，是细胞释放的、裹着一层膜的微小泡泡，几乎所有细胞都会释放。
4. 外泌体是其中较小的一类，直径大约三十到一百五十纳米，比细胞小上百倍。
5. 《科学》杂志上的一篇综述介绍：外泌体先在细胞内的“多囊泡体”里形成，再随它与细胞膜融合，被释放出去。
6. 另外，还有从细胞膜直接鼓出来的微囊泡，和细胞凋亡时产生的凋亡小体。
7. 它们很难彼此分开，所以国际指南MISEV建议，统一使用“细胞外囊泡”这个总称。
8. 包裹里装着蛋白质、脂质，还有各种RNA，比如微小RNA。
9. 2007年，《自然·细胞生物学》上的一项研究发现，外泌体能把RNA送进另一个细胞，并在那里继续发挥作用。
10. 就像一封信，把消息从一个细胞带给另一个细胞。
11. 在健康的身体里，它们参与免疫信号的传递，也帮助组织修复。
12. 但在疾病中，它们也可能被肿瘤利用，为癌细胞的扩散铺路。
13. 《自然》杂志上的一项研究，在小鼠实验中发现：肿瘤外泌体表面的“整合素”，会影响癌细胞更容易转移到肺还是肝。
14. 囊泡带着来源细胞的“身份信息”，科学家希望从血液、尿液里找到它们来发现疾病，这叫“液体活检”。
15. 《自然》上的一项研究报道，带有GPC1蛋白的外泌体或许能提示早期胰腺癌；但后续研究结果不一，仍需验证。
16. 它们还可能成为送药的“快递车”：2011年《自然·生物技术》上的研究，给外泌体装上“导航标签”，把药物分子送进了小鼠大脑。
17. 此外，干细胞来源的囊泡，也正在被研究用于组织再生。
18. 不过要冷静：大多数治疗用途，还停留在实验室研究或临床试验阶段。
19. 市面上打着“外泌体”旗号的美容、抗衰老项目，很多并未获得监管批准，要多加小心。
20. 而且，怎样分离、测量、统一标准，至今仍是这个领域的难题。
21. 一句话总结：细胞外囊泡，就是细胞之间传递消息的“快递包裹”。本视频仅供科普。
22. 文中提到的研究，参考文献见屏幕。

## References

Each entry was checked against Crossref (title, journal, year, volume/pages, DOI) and PubMed (PMID).
The narration only states what each paper reports, and says where results come from mouse
experiments.

1. Kalluri R, LeBleu VS. The biology, function, and biomedical applications of exosomes.
   *Science*. 2020;367(6478):eaau6977. doi:[10.1126/science.aau6977](https://doi.org/10.1126/science.aau6977). PMID 32029601.
   Used for: exosome biogenesis via multivesicular bodies; contents; overview.
2. Welsh JA, et al. Minimal information for studies of extracellular vesicles (MISEV2023): From
   basic to advanced approaches. *J Extracell Vesicles*. 2024;13(2):e12404.
   doi:[10.1002/jev2.12404](https://doi.org/10.1002/jev2.12404). PMID 38326288.
   Used for: recommending "extracellular vesicle" as the generic term when subtype/biogenesis
   can't be established.
3. Valadi H, et al. Exosome-mediated transfer of mRNAs and microRNAs is a novel mechanism of
   genetic exchange between cells. *Nat Cell Biol*. 2007;9(6):654-659.
   doi:[10.1038/ncb1596](https://doi.org/10.1038/ncb1596). PMID 17486113.
   Used for: exosomes carry mRNA/microRNA; transferred mRNA was translated in recipient cells.
4. Hoshino A, et al. Tumour exosome integrins determine organotropic metastasis. *Nature*.
   2015;527(7578):329-335. doi:[10.1038/nature15756](https://doi.org/10.1038/nature15756). PMID 26524530.
   Used for: exosomal integrins (α6β4/α6β1 → lung, αvβ5 → liver) influence metastatic
   organotropism, mainly shown in mouse models.
5. Melo SA, et al. Glypican-1 identifies cancer exosomes and detects early pancreatic cancer.
   *Nature*. 2015;523(7559):177-182. doi:[10.1038/nature14581](https://doi.org/10.1038/nature14581). PMID 26106858.
   Used for: GPC1-positive circulating exosomes as a candidate early pancreatic cancer marker.
   Context for the "results mixed" caveat (not shown on screen): later work reported weaker
   diagnostic performance, e.g. Lai X, et al. *Cancer Lett*. 2017;393:86-93,
   doi:[10.1016/j.canlet.2017.02.019](https://doi.org/10.1016/j.canlet.2017.02.019).
6. Alvarez-Erviti L, et al. Delivery of siRNA to the mouse brain by systemic injection of targeted
   exosomes. *Nat Biotechnol*. 2011;29(4):341-345. doi:[10.1038/nbt.1807](https://doi.org/10.1038/nbt.1807). PMID 21423189.
   Used for: exosomes engineered with a brain-targeting (RVG) peptide delivered siRNA to the
   mouse brain after intravenous injection.

Not used on screen, though verified: van Niel G, D'Angelo G, Raposo G. Shedding light on the cell
biology of extracellular vesicles. *Nat Rev Mol Cell Biol*. 2018;19(4):213-228,
doi:10.1038/nrm.2017.125 (overlaps with reference 1).

Statements without a citation (size range ~30–150 nm, "released by almost all cells", immune
signaling/tissue repair, stem-cell EV research, regulatory status of cosmetic "exosome" products,
standardization challenges) are general field knowledge, phrased conservatively.
