# Published Hungarian speech-to-text accuracy, as of 31 Oct 2026

Baseline under evaluation: `sarpba/whisper-hu-large-v3-turbo-finetuned`.

Trust labels used below:
- **A**: paper with a per-language table, same evaluation across models.
- **B**: author-run comparison of several models on public data, method only partly documented.
- **C**: self-reported model-card or vendor figure, not reproducible as stated.

Lower is better. All figures are percentages. "Norm" means text-normalized scoring.

## What Hungarian WER/CER is published for each model?

### Takeaway
Only a few candidates have a like-for-like Hungarian figure that clearly beats the current model. On FLEURS, the current model scores 16.26 normalized WER. Published scores on the same dataset include SeamlessM4T-v2-large 11.38, Canary-1B-v2 12.90, benmajor27 large-v3 13.58, Whisper-large-v3 14.11-14.62 and BuzzASR 14.7, but these come from different papers and normalizers. On spontaneous speech, the best published results are from Fast Conformer models fine-tuned on Hungarian (about 13-14% WER), against 21-23% for zero-shot Whisper-large-v3. The current model has no published figure on any spontaneous-conversation set.

### Cited Findings

**Current model: `sarpba/whisper-hu-large-v3-turbo-finetuned`**

| Dataset | WER | CER | Norm WER | Norm CER | Trust |
|---|---|---|---|---|---|
| Unnamed "custom dataset" (card's final validation, step 34000) | 7.48 | not reported | not stated | not stated | C |
| Common Voice 17.0 | 12.67 | 2.42 | 10.59 | 1.95 | B |
| FLEURS | 22.07 | 7.00 | 16.26 | 5.90 | B |
| VoxPopuli | 18.69 | 6.98 | 14.03 | 6.20 | B |
| KTH single-speaker set | 29.04 | 6.04 | 13.95 | 2.85 | B |

- Sources: [model card](https://huggingface.co/sarpba/whisper-hu-large-v3-turbo-finetuned) for the 7.48 row, [sarpba test table](https://huggingface.co/sarpba/whisper-teszt-eredmenyek) for the rest.
- The card says training and evaluation data need "more information", so 7.48 cannot be compared with anything — [card](https://huggingface.co/sarpba/whisper-hu-large-v3-turbo-finetuned).
- The author warns that the quantized CTranslate2 version degrades badly, truncating output, possibly on clips of about 10 seconds or less. The F32 version works well but is slower — [card](https://huggingface.co/sarpba/whisper-hu-large-v3-turbo-finetuned). This matters for a voice assistant if the deployment uses CT2/faster-whisper.

**Whisper family, from the sarpba table (Norm WER / Norm CER, trust B)** — [source](https://huggingface.co/sarpba/whisper-teszt-eredmenyek)

| Model | CV 17.0 | FLEURS | VoxPopuli | KTH |
|---|---|---|---|---|
| benmajor27/whisper-large-v3-hu_full | **7.80** / 1.50 | **13.58** / 5.01 | 14.07 / 6.36 | 18.35 / 3.33 |
| sarpba/whisper-hu-large-v3-turbo-finetuned (current) | 10.59 / 1.95 | 16.26 / 5.90 | **14.03** / 6.20 | **13.95** / 2.85 |
| sarpba/whisper-large-v2-CV18-hu-cleaned | see note | 14.75 / 4.65 | 14.63 / 6.41 | 15.96 / 3.35 |
| openai/whisper-large-v3 | 18.07 / 4.95 | 14.62 / 3.73 | 16.47 / 8.41 | 16.29 / 3.38 |
| openai/whisper-large-v3-turbo | 19.45 / 4.85 | 16.05 / 4.00 | 108.92 / 71.77 | 17.28 / 3.63 |
| openai/whisper-large-v2 | 21.82 / 5.47 | 19.26 / 5.15 | 26.22 / 15.03 | 19.99 / 4.43 |
| openai/whisper-large | 26.20 / 8.04 | 26.67 / 9.57 | 24.83 / 12.98 | 22.38 / 4.85 |
| openai/whisper-medium | 30.63 / 8.05 | 27.97 / 8.34 | 25.43 / 11.77 | 26.28 / 5.88 |
| sarpba/whisper-hu-small-finetuned | 17.34 / 3.68 | 19.22 / 5.27 | 23.48 / 11.17 | 16.23 / 3.55 |
| openai/whisper-small | 52.20 / 15.62 | 45.54 / 14.40 | 51.52 / 23.59 | 41.63 / 10.43 |
| sarpba/whisper-hu-base-finetuned-V2 | 15.66 / 3.58 | 26.06 / 10.75 | 20.37 / 9.09 | 19.60 / 5.91 |
| sarpba/whisper-base-hungarian_v1 | 23.53 / 5.77 | 30.60 / 10.43 | 17.70 / 7.09 | 19.94 / 4.81 |
| openai/whisper-base | 93.67 / 38.51 | 86.61 / 37.75 | 70.56 / 30.51 | 64.75 / 21.40 |
| sarpba/whisper-hu-tiny-finetuned-V2 | 20.05 / 4.84 | 31.09 / 12.61 | 22.50 / 8.71 | 21.05 / 5.15 |
| sarpba/whisper-hu-tiny-finetuned | 26.63 / 6.60 | 33.99 / 11.33 | 21.35 / 8.18 | 23.61 / 6.38 |
| openai/whisper-tiny | 119.12 / 53.19 | 106.29 / 55.98 | 106.81 / 45.99 | 82.86 / 31.67 |

- Note: the page excludes the large-v2-CV18 CV-17 result as not relevant because that model trained on the full cleaned CV-18. It also says large-turbo, large, large-v2 and the small fine-tune hallucinated on VoxPopuli, which skews that column — [source](https://huggingface.co/sarpba/whisper-teszt-eredmenyek).
- benmajor27's own card reports WER 8.86 on the CV 17.0 test set, is Apache-2.0, and trained on CV 17.0 — [card](https://huggingface.co/benmajor27/whisper-large-v3-hu_full). Trust C.

**Benchmark with the most Hungarian-capable models: BuzzASR paper, Hungarian row, combined FLEURS + Common Voice 25 test (trust A-, Findings of EMNLP 2026)** — [paper Tables 7-8](https://arxiv.org/pdf/2609.09554), [venue per card](https://huggingface.co/BuzzASR/hungarian)

| Model | WER | CER | Scoring |
|---|---|---|---|
| BuzzASR FFT (Whisper fine-tune, full fine-tuning) | 10.21 | 2.71 | Norm |
| BuzzASR SFT (simple fine-tune; figures match the published card) | 12.78 | 2.68 | Norm |
| BuzzASR SFT + MTL | 16.41 | 3.76 | Norm |
| Whisper-large-v3 zero-shot | 15.06 | 3.59 | Norm |
| Omnilingual 7B | 12.78 | 2.62 | Norm |
| Omnilingual 1B | 19.66 | 3.87 | Norm |
| MMS | 19.75 | 3.90 | Norm |
| Qwen3-ASR | 43.02 | 13.52 | **Raw** |
| Cohere Transcribe 2B | 133.65 | 81.08 | **Raw** |

- Caveat: I extracted these from PDF text in which some numbers run together, then split them by the table's column order. The SFT column matches the model card, and the table itself states that Qwen3 and Cohere scores are raw — [paper](https://arxiv.org/pdf/2609.09554). The identical 12.78 for SFT and Omni 7B is as printed.
- `BuzzASR/hungarian` card: FLEURS 14.7 WER / 3.7 CER, Common Voice 25 10.45 WER / 2.0 CER, combined 12.78 WER / 2.68 CER, normalized. Whisper-large-v3 zero-shot CER is 3.57 / 3.68 / 3.59 on the same sets. So on FLEURS its CER is no better than zero-shot. MIT-tagged, about 2B parameters, based on large-v3 — [card](https://huggingface.co/BuzzASR/hungarian).

**NVIDIA paper, FLEURS Hungarian column (trust A; vendor-run, on one dataset)** — [Table 11](https://arxiv.org/pdf/2509.14128)

| Model | WER |
|---|---|
| seamless-m4t-v2-large | 11.38 |
| Canary-1B-v2 | 12.90 |
| whisper-large-v3 | 14.11 |
| Parakeet-TDT-0.6B-v3 | 15.72 |
| seamless-m4t-medium | 24.09 |
| Voxtral-Mini-3B-2507, Phi-4-multimodal | no Hungarian figure |

- Hungarian appears only in the Fleurs column for ASR, not MLS or CoVoST2 — [paper Table 1](https://arxiv.org/pdf/2509.14128).

**Fleurs-SLU (COLM 2025)**
- The Hungarian row of Table 8 shows Whisper-v3-Large "5.2 12.8" and SeamlessM4Tv2-Large "8.5 11.3", pooled over train, dev and test splits. It is average CER per the caption, but my extraction lost the two sub-column labels, so the row should not be quoted without checking the PDF — [paper](https://arxiv.org/pdf/2501.06117).

**Omnilingual ASR (Meta)**
- `hun_Latn`: **CER 1.6**, 356.2 training hours, 7B-LLM-ASR — [Meta per-language CSV](https://raw.githubusercontent.com/facebookresearch/omnilingual-asr/main/per_language_results_table_7B_llm_asr.csv). The CSV does not name its test set. Trust C for comparison.
- BuzzASR's independent evaluation measures the same model family at CER 2.62 and WER 12.78 on FLEURS + CV25 — [paper](https://arxiv.org/pdf/2609.09554). Trust that one over 1.6.

**Conversational Hungarian research models (BME/ELTE; trust A, preprints)**

| Model | Corpus / subset | WER | CER | Source |
|---|---|---|---|---|
| f_conformer_ctc, train-114 + train-293 (about 245 h) | BEA-Large eval, repeated | 4.80 | 1.20 | [2511.13529](https://arxiv.org/html/2511.13529v2) |
| same | BEA-Large eval, spontaneous | 14.18 | 4.56 | same |
| whisper-large-v3, zero-shot | BEA-Large eval, repeated | 13.73 | 2.83 | same |
| whisper-large-v3, zero-shot | BEA-Large eval, spontaneous | 21.28 | 9.31 | same |
| whisper-large-v2, zero-shot | BEA-Large eval, spontaneous | 32.56 | 18.61 | same |
| whisper-medium, zero-shot | BEA-Large eval, spontaneous | 39.19 | 21.71 | same |
| fc_hu_xl, fine-tuned | BEA-Dialogue eval | 13.03 | 6.65 | [2605.31469](https://arxiv.org/html/2605.31469v1) |
| fc_hu_xl, zero-shot | BEA-Dialogue eval | 15.48 | 7.47 | same |
| whisper-large-v3, zero-shot | BEA-Dialogue eval | 22.21 | 12.27 | same |
| fc_hu_xl, fine-tuned | BEA-Dialogue+ eval | 13.59 | 7.34 | same |
| fc_hu_l, fine-tuned | BEA-Dialogue+ eval | 15.19 | 7.95 | same |
| whisper-large-v3, zero-shot | BEA-Dialogue+ eval | 23.27 | 13.34 | same |
| whisper-large-v2, zero-shot | BEA-Dialogue+ eval | 25.48 | 14.68 | same |

- The BEA-Dialogue+ paper does not mention a public release of the trained models. It says the corpus is available for research — [paper](https://arxiv.org/html/2605.31469v1).

**wav2vec2 and related Hungarian models**
- `jonatasgrosman/wav2vec2-large-xlsr-53-hungarian`: WER 31.40 on Common Voice test. CER is listed as 10.49 in a later revision and 6.20 in an earlier comparison table. Conflict unresolved — [commit](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-hungarian/commit/1271f9559ba026a27c6c07b569dc520340d6d249), [earlier README](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-hungarian/blob/77b5aa02adf7577dc92a6e31856438b043b24000/README.md).
- BEA-Base (LREC 2022), wav2vec2-large transfer learning with fine-tuning on Hungarian. Best row "Mega" scores 6.16/2.39 and 15.61/5.11 on the last two column pairs, which I read as eval-repeated and eval-spontaneous. "Multi » Hungarian" scores 5.60/2.63 and 17.00/5.45 — [paper](https://arxiv.org/pdf/2202.00601). Trust A. These were retrained on BEA, so they are not the off-the-shelf card models.

**Other Whisper fine-tunes, seen only in search snippets (cards not opened; trust C)**
- `sgangireddy/whisper-medium-hu`: about 19.8 WER on CV 11 — [card](https://huggingface.co/sgangireddy/whisper-medium-hu).
- `DrishtiSharma/whisper-large-v2-hungarian`: 17.45 WER on CV 11 — [card](https://huggingface.co/DrishtiSharma/whisper-large-v2-hungarian).

**Models with no Hungarian-specific figure found**
- Qwen3-ASR's own README has none. Hungarian is only inside an aggregate "Fleurs††" of 10 extra languages: 1.7B 12.60, 0.6B 21.80, Whisper-large-v3 8.16 — [README](https://github.com/QwenLM/Qwen3-ASR). The only per-language figure I found is BuzzASR's raw score above.
- Voxtral 3 publishes macro-averages only, with no per-language WER — [Mistral](https://mistral.ai/news/voxtral-3/).
- No Hungarian figure was found for Nemotron 3.5 ASR.

**Cloud, for comparison only (trust C: vendor-run, method undisclosed, FLEURS)** — [Speechmatics](https://www.speechmatics.com/speech-to-text/hungarian)
- Speechmatics Enhanced 6.67, Amazon Transcribe 11.02, Azure 13.52, Whisper-large-v3 16.32, Google Chirp 2 20.66, Deepgram Nova-2 30.05.
- The same page's FAQ claims "up to 96%" accuracy, which does not match its own table.
- No Hungarian figure was found for ElevenLabs Scribe or OpenAI's hosted transcription models. They were not specifically searched in depth.

### Inferences
- **The current model is not clearly ahead of vanilla large-v3.** In the sarpba table it beats large-v3 on CV, VoxPopuli and KTH, but loses on FLEURS (16.26 vs 14.62 WER; CER 5.90 vs 3.73). It also shows no gain over vanilla turbo on FLEURS (16.26 vs 16.05). The much higher CER on FLEURS deserves a look in your own tests.
- **Strongest self-hostable candidates to test, in order:**
  1. `benmajor27/whisper-large-v3-hu_full`: wins CV and FLEURS, ties VoxPopuli, loses clearly on KTH. Heavier than turbo (about 2B vs 0.8B parameters).
  2. Canary-1B-v2: 12.90 on FLEURS, and not a Whisper architecture.
  3. `BuzzASR/hungarian` and Omnilingual 7B: both near 12.8 on the combined test. The published BuzzASR card matches SFT rather than the 10.21 FFT variant.
  4. SeamlessM4T-v2-large: lowest open-model FLEURS WER at 11.38, but this rests on one dataset and on a vendor paper that was benchmarking its own rival models. Check the license first.
- **Fast Conformer fine-tunes have the best conversational numbers,** but no checkpoint is confirmed public. Training your own on BEA would depend on research access.
- **Parakeet v3 (15.72) does not look like an accuracy win** over the current model on FLEURS (16.26). The 0.5-point gap is smaller than the spread between measurements of the same model. Its case would have to rest on speed.
- **Qwen3's 43.02 is likely inflated by raw scoring,** but a 13.52 raw CER and its aggregate results do not suggest it would win.

### Gaps
- No published figure compares the current model with Canary, Seamless, Omnilingual or BuzzASR on one identical pipeline.
- No published figure for the current model on BEA or any casual-speech Hungarian corpus.
- No figure for short voice-assistant commands, smart-home vocabulary or far-field audio on any Hungarian model.
- CER and WER for turbo-based fine-tunes other than sarpba's were not found.
- BuzzASR's FFT Hungarian checkpoint: I could not confirm whether it is published. The card describes simple fine-tuning.
- Licenses for SeamlessM4T v2, Omnilingual and Canary were not checked in this research.

## Which models do not officially support Hungarian?

### Takeaway
Granite Speech, Moonshine and the released SenseVoiceSmall do not support Hungarian. Parakeet v3, Canary-1B-v2, Qwen3-ASR (1.7B and 0.6B) and Omnilingual do. Voxtral 3 appears to, but open-weight availability is unconfirmed.

### Cited Findings

| Model | Hungarian? | Evidence |
|---|---|---|
| Granite 4.0 1B Speech | **No** (English, French, German, Spanish, Portuguese, Japanese) | [card](https://huggingface.co/ibm-granite/granite-4.0-1b-speech) |
| Moonshine | **No** (10 languages listed) | [docs](https://moonshine-voice.readthedocs.io/en/latest/models/available-models/) |
| SenseVoiceSmall | **No** (Mandarin, Cantonese, English, Japanese, Korean; "50+" refers to wider research) | [README](https://github.com/FunAudioLLM/SenseVoice) |
| Qwen3-ASR 1.7B / 0.6B | Yes (30 languages); forced aligner no | [README](https://github.com/QwenLM/Qwen3-ASR) |
| Parakeet-TDT-0.6B-v3, Canary-1B-v2 | Yes (evaluated on hu) | [paper](https://arxiv.org/pdf/2509.14128) |
| Omnilingual ASR | Yes (`hun_Latn`) | [CSV](https://raw.githubusercontent.com/facebookresearch/omnilingual-asr/main/per_language_results_table_7B_llm_asr.csv) |
| SeamlessM4T v2 | Evaluated on hu | [paper](https://arxiv.org/pdf/2509.14128) |
| Voxtral 3 (Mistral) | HU is named in the 45-language FLEURS benchmark. Transcription docs give language counts, not a list | [news](https://mistral.ai/news/voxtral-3/), [docs](https://docs.mistral.ai/studio/audio/specs-and-limits/languages) |
| Voxtral-Mini-3B-2507 (open, 2025) | No Hungarian figure in the NVIDIA table | [paper](https://arxiv.org/pdf/2509.14128) |

- A search snippet suggesting Hungarian was absent from the Voxtral 3 transcription list conflicts with Mistral's own benchmark list, which includes HU. I weighted Mistral's page.

### Inferences
- Cohere Transcribe's 133.65 WER and 81.08 CER on Hungarian look like a model that does not handle the language, but I did not verify its official language list.

### Gaps
- Nemotron 3.5 ASR covers about 40 locales per secondary sources, but Hungarian could not be confirmed. The one card I tried returned 401 — [mirror](https://huggingface.co/aoiandroid/nemotron-3.5-asr-streaming-0.6b).
- Whether Voxtral 3 transcription weights are downloadable: Mistral's page mentions self-deployment but gives no license or weights detail — [news](https://mistral.ai/news/voxtral-3/).
- Cohere Transcribe's official language list was not checked.

## Which datasets were used, and are the figures comparable?

### Takeaway
Figures are comparable only within one table. Same-model spread on the same dataset is about 2 WER points, and moving from read to spontaneous speech adds 7-8 points or more. Most "good" Hungarian numbers come from read or repeated speech, which is an optimistic guide to casual use.

### Cited Findings

| Dataset | Speech type | Used by |
|---|---|---|
| Common Voice (17.0, 25, older) | Crowd-recorded read sentences | sarpba table, benmajor27, BuzzASR, wav2vec2 cards |
| FLEURS | Read sentences (Hungarian size: see Fleurs-SLU) | NVIDIA, sarpba table, BuzzASR, Speechmatics |
| VoxPopuli | Not described on the sarpba page | sarpba table |
| KTH | Single-speaker TTS set, per my fetch summary of the sarpba page (unconfirmed) | sarpba table |
| BEA-Large | 255 h, 433 speakers; spontaneous plus repeated subsets | [2511.13529](https://arxiv.org/html/2511.13529v2) |
| BEA-Dialogue | 85 h natural dialogues | [2605.31469](https://arxiv.org/html/2605.31469v1) |
| BEA-Dialogue+ | About 200 h; harder for models without fine-tuning | [2605.31469](https://arxiv.org/html/2605.31469v1) |
| BEA-Base | Mostly spontaneous, 140 speakers | [2202.00601](https://arxiv.org/pdf/2202.00601) |

- Same model, same dataset, three figures: Whisper-large-v3 on FLEURS Hungarian is 14.11 ([NVIDIA](https://arxiv.org/pdf/2509.14128)), 14.62 normalized and 19.77 raw ([sarpba](https://huggingface.co/sarpba/whisper-teszt-eredmenyek)), and 16.32 ([Speechmatics](https://www.speechmatics.com/speech-to-text/hungarian)).
- Normalization shifts results heavily: the current model on KTH is 29.04 raw vs 13.95 normalized, and on FLEURS 22.07 vs 16.26 — [sarpba](https://huggingface.co/sarpba/whisper-teszt-eredmenyek).
- Read vs spontaneous for Whisper-large-v3: 13.73 repeated vs 21.28 spontaneous, BEA-Large eval. The Fast Conformer goes from 4.80 to 14.18 — [paper](https://arxiv.org/html/2511.13529v2).
- Common Voice versions and splits differ across sources: CV 17.0 in the sarpba table, CV 25 in BuzzASR. Omnilingual's CSV does not name a set.
- BEA papers remove hesitations, laughter and non-verbal events before scoring and do not explicitly describe text normalization — [2605.31469](https://arxiv.org/html/2605.31469v1). The sarpba page labels "Norm" columns without defining them — [source](https://huggingface.co/sarpba/whisper-teszt-eredmenyek). BuzzASR scores Qwen3 and Cohere raw and others normalized — [paper](https://arxiv.org/pdf/2609.09554).

### Inferences
- Treat differences under about 2 WER points across different sources as noise.
- Raw WER is not usable for ranking on Hungarian, because casing, punctuation and numbers dominate some sets.
- CV-based wins may be partly contamination: benmajor27 trained on CV 17.0 and the current model's "custom dataset" is undisclosed, so overlap with test data cannot be ruled out.
- The 7.48 headline figure for the current model should be disregarded for comparison. On public data the same model scores 10.59-16.26 normalized.

### Gaps
- No HUSpeech result turned up. It may exist, but none appeared in my searches.
- The exact normalizer used by sarpba's table is undocumented.
- Whether fine-tunes tested on CV 17.0 had seen those test utterances could not be verified.
- The description of VoxPopuli and KTH content is not stated on the sarpba page. The KTH label comes from the search result's reading of that page, not a dataset card I opened.

## Are there independent benchmarks?

### Takeaway
No fully independent Hungarian-specific leaderboard covering current models was found. The closest are the BuzzASR paper, the BME/ELTE BEA papers and NVIDIA's FLEURS table, and each has an interest in at least one of the models it tests.

### Cited Findings
- **sarpba/whisper-teszt-eredmenyek:** the broadest Hungarian Whisper table (four datasets, 60+ rows), but run by the author of many tested models, undated, and Whisper-only — [source](https://huggingface.co/sarpba/whisper-teszt-eredmenyek).
- **BuzzASR (EMNLP 2026 Findings):** Hungarian row across Whisper, Omnilingual, MMS, Qwen3 and Cohere. Authors built BuzzASR, so baselines are the competition — [paper](https://arxiv.org/pdf/2609.09554).
- **NVIDIA Sekoyan et al.:** FLEURS Hungarian row, vendor comparing its own models — [paper](https://arxiv.org/pdf/2509.14128).
- **BEA papers:** academic and Hungarian-focused, but only zero-shot Whisper and their own Fast Conformers — [2511.13529](https://arxiv.org/html/2511.13529v2), [2605.31469](https://arxiv.org/html/2605.31469v1). No Whisper fine-tune, Canary, Parakeet or Qwen3 is included.
- **Open ASR Leaderboard:** the paper excerpt I saw shows multilingual columns for German, French, Italian, Spanish and Portuguese only, with no Hungarian — [arXiv 2510.06961](https://arxiv.org/html/2510.06961v4). I did not open the live leaderboard.
- **Blog figures:** a Whisper Notes post repeats Parakeet 15.7 and Whisper-large-v3 14.1, which is NVIDIA's table rather than new testing — [post](https://whispernotes.app/blog/parakeet-v3-default-mac-model).

### Inferences
- No published source answers the question directly. A small in-house test on your own recordings, with a single normalizer, is needed to decide. The repo's `bench.py` may be a starting point (not inspected).

### Gaps
- MSZNY: my searches returned no MSZNY paper with Hungarian ASR figures, which does not prove none exist. The conference proceedings were not browsed directly.
- "Best data is more supervised data – even for Hungarian ASR" (SPECOM 2025) was seen only as a citation; its results were not read — [citing paper](https://arxiv.org/pdf/2606.03957).
- An alphaXiv summary claims 7.29% WER for a fine-tuned Fast Conformer XLarge, and a search snippet gives 19.24 / 7.93 for BEA-Dialogue eval, against 20.56 / 9.11 in the v2 HTML I read. I could not reconcile these and did not rely on them. They may reflect other paper versions or subsets.
