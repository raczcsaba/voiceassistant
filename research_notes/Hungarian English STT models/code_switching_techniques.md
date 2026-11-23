# STT handling of code-switching and foreign named entities (English names inside Hungarian sentences), as of 31 Oct 2026

Scope note for the report writer: no source found evaluates Hungarian-English code-switching or suffixed English names ("Hey Jude-ot", "Massive Attacket"). Unless a line is marked **[Hungarian]**, the evidence comes from another language pair and is labelled as such. Items marked "(search snippet)" were seen only in a search-result summary, because the full text was not fetched (arxiv.org fetches failed intermittently). Check those before quoting them as firm.

## Which STT models explicitly support intra-sentence code-switching, and what is the measured evidence?

### Takeaway
No candidate has measured Hungarian-English code-switching evidence, and most local models claim only language detection, not intra-sentence switching. The best independent benchmark shows errors concentrating in the embedded English, on long sentences in four unrelated language pairs. A local bake-off on our own commands is therefore required.

### Cited Findings
- **ServiceNow benchmark (June 2026), the closest multi-model comparison. Pairs: Spanish, French, Canadian French and German with English; not Hungarian.** Tested AssemblyAI Universal-3 Pro, Deepgram Nova 3 Multilang, ElevenLabs Scribe V2, Gemini 3 Flash, Voxtral Small 24B-2507, Parakeet TDT 0.6b V3 and Whisper Large V3 Turbo — [ServiceNow](https://huggingface.co/blog/ServiceNow-AI/code-switching)
- That benchmark's limits matter for us: audio is synthetic (ElevenLabs Multilingual V2), utterances run 12-40 words, all models used auto-detect, entity and product names were not counted as switchable words, and entity-dominated utterances were excluded. Latency was not reported — [ServiceNow](https://huggingface.co/blog/ServiceNow-AI/code-switching)
- Whisper Large V3 Turbo WER ranged from 0.16 to 0.61, and its code-switching cost peaked at +0.85 on German-English relative to English. Errors concentrated in the English portions, which the authors call counterintuitive. The full per-model tables are images and were not extracted — [ServiceNow](https://huggingface.co/blog/ServiceNow-AI/code-switching)
- Among Parakeet, Voxtral and Nova-3, Parakeet is the weakest overall but outperforms Nova-3 and Voxtral on German-English (search snippet) — [ServiceNow](https://huggingface.co/blog/ServiceNow-AI/code-switching)
- **Parakeet TDT 0.6b v3 [Hungarian]:** Hungarian is one of 25 supported languages, with 15.72% WER on Fleurs (excluding punctuation and capitalization). The card says it auto-detects the audio language but makes no statement about code-switching — [NVIDIA model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- **Qwen3-ASR:** an aggregator summary reports LID across 52 languages and dialects, and TTFT as low as 92 ms for the 0.6B model. It mentions code-switched applicability only for the forced aligner, says code-switching evaluation remains a gap, and does not mention Hungarian. This is a secondary source; the primary report was not read — [ArxivLens summary](https://arxivlens.com/paperview/viewpdf/qwen3-asr-technical-report-232-4fcaadd0)
- **Fun-ASR (Mandarin-English):** the report describes intra-utterance Chinese-English switching and hotword customization, with recall above 0.97 on most technical-term topics (search snippet) — [Fun-ASR report](https://arxiv.org/pdf/2509.12508)
- **Qwen-Audio-3.0-ASR:** the report describes hierarchical hotword customization with weighted priority tiers (search snippet) — [Qwen-Audio-3.0-ASR report](https://arxiv.org/pdf/2609.07549)
- **Whisper Large (Mandarin-English):** with concatenated language tokens, Total MER was 20.9 on ASCEND test, beating the supervised state of the art of 25.0. It remained behind on SEAME (32.7 vs 16.6 on devman, 47.6 vs 23.3 on devsge) — [Peng et al.](https://arxiv.org/html/2305.11095)
- **Yoruba-English:** a study reports that training does not automatically confer strong code-switching capability (search snippet) — [CALCS 2025](https://aclanthology.org/2025.calcs-1.3.pdf). A 2026 switch-aware evaluation exists, but its text could not be extracted — [Okocha and Grant](https://arxiv.org/pdf/2609.11786)
- **MMS adapters (Arabic, Mandarin and Hindi with English):** one adapter-based method for code-switching exists, but no numbers were retrieved (search snippet) — [Yuvarraj/MASR](https://huggingface.co/Yuvarraj/MASR)
- **Omnilingual ASR:** covers 1,600+ languages under permissive licences, but the sources found give no code-switching evaluation — [VentureBeat](https://venturebeat.com/ai/meta-returns-to-open-source-ai-with-omnilingual-asr-models-that-can)
- **Hungarian baseline [Hungarian]:** a review of the BEA paper says a fine-tuned Fast Conformer consistently beat all zero-shot Whisper models on conversational Hungarian. It does not address English words or entities (secondary source) — [BEA review](https://www.themoonlight.io/review/toward-conversational-hungarian-speech-recognition-introducing-the-bea-large-and-bea-dialogue-datasets); [BEA-Dialogue+ abstract](https://arxiv.org/abs/2605.31469)
- A Hungarian model card notes that agglutination makes WER count one wrong suffix as a whole-word error, so CER may be fairer (search snippet) — [BuzzASR/hungarian](https://huggingface.co/BuzzASR/hungarian) or [SubZtep/whisper-small-hu](https://huggingface.co/SubZtep/whisper-small-hu) (the snippet did not make clear which)

### Inferences
- "Multilingual" and "auto-detect" do not mean intra-sentence switching. Parakeet v3's card is a clear example.
- Benchmark rankings may transfer poorly: they exclude entities, use long sentences and use clean synthetic speech, whereas our task is the reverse (short, entity-centred, Hungarian-accented pronunciation).
- For evaluation, score entity accuracy after normalization (library match) rather than WER, since "Jude-ot", "Judeot" and "Dzsúd-ot" could all resolve correctly downstream.

### Gaps
- No measured results for Hungarian-English code-switching on any model.
- No code-switching evaluation found for Canary, SenseVoice, Granite Speech or Omnilingual ASR. Granite search results held no code-switching data, and SenseVoice returned nothing relevant.
- Voxtral has numbers only in the unextracted ServiceNow table images.
- Whether Qwen3-ASR's 52 languages include Hungarian is unconfirmed; check the primary report and model card.

## How do language forcing and auto-detect affect mixed speech in Whisper?

### Takeaway
Forcing the matrix language tends to wreck the embedded language, and auto-detect commits to one language and is unreliable on short or accented audio. Concatenating both language tokens beat both on Mandarin-English, and is the cheapest thing to test on Hungarian-English.

### Cited Findings
Whisper Large, **Mandarin-English** validation sets — [Peng et al.](https://arxiv.org/html/2305.11095):

| Dataset | Prompt | Zh CER | En WER | Total MER |
|---|---|---|---|---|
| ASCEND | forced zh | 16.3 | 93.1 | 32.6 |
| ASCEND | forced en | 90.4 | 31.5 | 78.9 |
| ASCEND | auto | 17.0 | 31.8 | 22.1 |
| ASCEND | concat zh+en | 16.6 | 31.8 | 21.3 |
| SEAME | forced zh | 26.3 | 97.4 | 46.7 |
| SEAME | forced en | 99.3 | 33.8 | 82.2 |
| SEAME | auto | 27.1 | 85.5 | 45.3 |
| SEAME | concat zh+en | 25.9 | 44.7 | 36.9 |

- On test sets, concat vs default Total MER was 20.9 vs 22.8 (ASCEND), 32.7 vs 38.2 (SEAME devman) and 47.6 vs 65.0 (SEAME devsge) — [Peng et al.](https://arxiv.org/html/2305.11095)
- The same paper says each language token represents only one language, and that LID can be inaccurate, especially on accented speech — [Peng et al.](https://arxiv.org/pdf/2305.11095)
- Best prompt varies by data: an Interspeech 2025 paper found a single-language prompt best on one dataset and self-detection best on another (search snippet) — [Meyer et al.](https://www.isca-archive.org/interspeech_2025/meyer25_interspeech.pdf)
- Community reports of auto-detect failures: misclassification on short initial utterances — [millet PR #16](https://github.com/pretyflaco/millet/pull/16); translating rather than transcribing after wrong detection — [OpenAI forum](https://community.openai.com/t/whisper-3-detects-incorrect-language-translates-instead-of-transcribes/828870). These are anecdotes, not measurements.
- whisper.cpp detection reportedly always analyzed the first window regardless of offset; the proposed fix was reported as open (search snippet, via a mirror) — [whisper.cpp PR #3765 mirror](https://gh.r-mj.com/ggml-org/whisper.cpp/pull/3765)
- The ServiceNow authors did not test forced tokens or multi-language hints, so the benchmark gives no evidence here — [ServiceNow](https://huggingface.co/blog/ServiceNow-AI/code-switching)

### Inferences
- Expect `language=hu` to give Hungarian-spelled or wrong names, by analogy with the forced-zh English WER of 93-97. Hungarian uses Latin script, so the failure may be milder and more phonetic than Mandarin's script-level failure. That untested difference could help phonetic post-matching.
- Our commands usually start with Hungarian ("Játszd le..."), so auto-detect will probably pick `hu` and behave like forcing, while saving nothing. Forcing `hu` also removes detection instability.
- Concat `<|hu|><|en|>` requires modifying the decoder prompt. It adds one token and so should cost negligible latency. Whether faster-whisper or whisper.cpp expose this without patching was not verified.

### Gaps
- No Hungarian-English or other Latin-script small-language measurement of forced vs auto vs concat.
- No published measurement of LID accuracy on 1-5 s commands with an embedded name.

## Which methods work for named entities: boosting, biasing, KWS decoders, prompts, logit biasing, tries?

### Takeaway
Decoder-side biasing with a trie or phrase tree has the strongest numbers and low runtime cost, and beam search gains about twice what greedy does. All strong results are English or Mandarin, and none tests inflected foreign names, so suffix handling is the main open risk for us.

### Cited Findings
**NeMo GPU phrase boosting (TurboBias), English only** — [TurboBias](https://arxiv.org/html/2508.07014v2):

| Model / decoding | Boost off: F-score / WER (CSTalks) | Boost on: F-score / WER (CSTalks) |
|---|---|---|
| CTC greedy | 35.0 / 13.7 | 64.8 / 11.9 |
| CTC beam | 35.0 / 13.8 | 83.2 / 10.2 |
| RNN-T greedy | 42.5 / 12.8 | 70.4 / 10.7 |
| RNN-T beam | 44.2 / 12.8 | 82.9 / 9.6 |
| AED (Canary) greedy | 52.6 / 12.7 | 75.6 / 10.4 |
| AED (Canary) beam | 53.7 / 12.5 | 82.4 / 10.2 |

- Boosting slowed RTFx by 2-5%. Beam search was 11-20% slower than greedy, and all models were large FastConformer on an RTX A6000 at batch size 32 — [TurboBias](https://arxiv.org/html/2508.07014v2)
- Average gains were 8-10 F-score points in greedy and 17-23 in beam mode. At 20K phrases, F-score still reached 78.4% against a 44.2% baseline, but WER rose from 9.86% at zero phrases to 11.42%, showing a false-boost cost as lists grow — [TurboBias](https://arxiv.org/html/2508.07014v2)
- Precision fell slightly with boosting (e.g. 97 to 90 for CTC beam on CSTalks) — [TurboBias](https://arxiv.org/html/2508.07014v2)
- **CTC-WS:** a word spotter matches CTC log-probabilities against a context graph and replaces greedy output in matched intervals. Transducers need a hybrid Transducer-CTC model. It is in NeMo — [Andrusenko et al.](https://arxiv.org/abs/2406.07096). In greedy mode it beat TurboBias on F-score (79.8 vs 64.8) but ran about twice as slow — [TurboBias](https://arxiv.org/html/2508.07014v2)
- **sherpa-onnx hotwords:** only for transducers with `modified_beam_search`, with the greedy default ignoring them; matching and score are token-level — [sherpa docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html). BPE models need `bpe.vocab` — [sherpa docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html). Non-English users do report friction: tokenizing Korean hotwords (mirror) — [issue #1762](https://github.aipraa306.workers.dev/k2-fsa/sherpa-onnx/issues/1762), and a German streaming model where hotwords did not seem to work — [Kroko discussion](https://huggingface.co/Banafo/Kroko-ASR/discussions/8)
- **Trie for Whisper (English, LibriSpeech, Large-v3, beam 10, N=1000 distractors):** B-WER fell from 9.86 to 5.66 (test-clean) and 17.55 to 9.90 (test-other), with U-WER unchanged or slightly better. Uniform per-token rewards beat final-token-only rewards (6.11 vs 7.95) — [Liu et al.](https://arxiv.org/html/2508.17796v2)
- That method builds variants from 18 TTS utterances per hotword (3 engines, 3 voices, 2 templates) transcribed by Whisper. Without syllable filtering, noisy variants pushed WER to about 20-26%. Latency was not reported, and multilingual synthesis is future work — [Liu et al.](https://arxiv.org/html/2508.17796v2)
- **LOGIC logit biasing (speech LLM, 11 unnamed locales):** about 9% relative entity-WER reduction, +0.3% false alarms, about 2.8% runtime overhead, and 5% further entity-WER reduction when combined with prompting — [Wang et al.](https://arxiv.org/abs/2601.15397)
- **KWS-Whisper / CB-Whisper (Mandarin-English on internal sets):** OV-KWS plus a spoken-form prompt on frozen Large-v2 raised entity recall from 87.3% to 97.7% and 79.9% to 96.9%, and lowered MER from 4.4 to 2.9 and 5.6 to 3.6. It uses edge-tts entity features and a 0.2M-parameter CNN, and latency was not measured — [Li et al.](https://arxiv.org/html/2309.09552v4)
- **Prompt-aware fine-tuning:** an Interspeech 2024 paper reports substantial entity recall gains when Whisper is fine-tuned to expect entity prompts, suggesting plain prompting is weak partly because Whisper was not trained for it (search snippet) — [Interspeech 2024 listing](https://papers.cool/venue/wei24@interspeech_2024@ISCA)

### Inferences
- Our result that `initial_prompt` made things worse fits this picture: Whisper was not trained to use entity prompts, so it gets only soft guidance, and prompts can bias or hallucinate. KWS-gated prompting (only prompting entities spotted in the audio) is the published fix, rather than listing many names.
- Tries are spelling-based, and a Hungarian-pronounced "Massive Attack" may never be near the English token path under a Hungarian-context decoder. Liu et al.'s TTS-derived variants, generated with Hungarian-accented or Hungarian-TTS pronunciation, and including Hungarian-spelled forms ("Dzsúd"), are the natural adaptation. This is untested.
- Add a suffix approach: leave the trie open after the entity stem so Hungarian suffixes decode freely, or enumerate variants (-ot, -et, -t, -ból...). Enumeration multiplies phrases, and the TurboBias false-boost cost then applies.
- Likely 500-600 ms fit: Parakeet v3 with sherpa-onnx `modified_beam_search` or NeMo boosting. Runtime overhead looks small relative to the budget, but none of these numbers were measured on our hardware or on single short utterances.
- A Canary path exists in NeMo, but a Hungarian Canary model's availability was not checked.

### Gaps
- No biasing study on agglutinative inflection or on cross-language pronunciation of entities.
- Whether sherpa-onnx hotwords work with the exported Parakeet v3 multilingual transducer was not confirmed.
- Exact CTC-WS paper numbers were not retrieved, beyond the TurboBias comparison.
- No head-to-head of biasing and post-correction on the same data.

## What about post-correction: LLM correction with a catalog, phonetic matching, fuzzy retrieval?

### Takeaway
Retrieval from a catalog plus constrained selection gives large entity gains, and a small music library should be far easier than the published millions of entities. Latency is essentially unpublished, but the retrieval part alone looks feasible in our budget, while a local LLM step needs measuring. Non-LLM phonetic matching should be tried first.

### Cited Findings
- **Apple, music-query domain, closest to our use case (language not stated, appears English):** with a 2.6M-entity catalog, WER reductions were 32.6% (head), 35.3% (torso), 39.0% (tail) on synthetic sets and 7.7% on STOP. WER went from 6.98/7.68/7.98/4.53 to 4.70/4.97/4.87/4.18. It used a LoRA-adapted (rank 4) OpenLLaMA 7B — [Retrieval Augmented Correction paper](https://arxiv.org/html/2409.06062v1)
- Retrieval there: top-1/5/10 recall for head entities was 84.8/91.6/92.8 with orthographic Acoustic Neighbor Embeddings (40-dim), against 80.7/86.9/88.4 for T5 semantic embeddings and 53.5/71.2/74.6 for BM25. Latency was not reported — [same paper](https://arxiv.org/html/2409.06062v1)
- **RECOVER (English datasets):** constrained LLM selection with exact, fuzzy and phonetic top-K candidates and guardrails cut entity WER 14.5-45.7%, with entity recall gains up to about 21.5 points (Common Voice 59.26 to 80.79). WER did not rise on any dataset for GPT-4o, but GPT-4o-mini raised it on Earnings-21 (to 14.07%). Latency and hallucination rate were not reported, and the main model is cloud GPT-4o — [RECOVER](https://arxiv.org/html/2603.16411)
- **RASTAR:** three-stage pipeline of recognition, phonetic edit-distance retrieval and LLM correction, with no retrieved numbers (search snippet) — [RASTAR](https://arxiv.org/html/2602.12287)
- **Generative annotation** acknowledges possible latency problems with large datastores (secondary source) — [review](https://www.themoonlight.io/review/generative-annotation-for-asr-named-entity-correction)
- **PATCorrect** targets latency directly: non-autoregressive correction at tens of milliseconds (search snippet; general correction, not catalog) — [PATCorrect](https://arxiv.org/html/2302.05040v2)
- **Amazon entity retrieval:** 48.08% entity error reduction with an augmented Transformer (search snippet) — [Amazon Science](https://www.amazon.science/publications/asr-error-correction-with-augmented-transformer-for-entity-retrieval)
- Generative correction can produce hallucinated over-corrections, per the authors of a competing biasing method (so not neutral) — [LOGIC](https://arxiv.org/abs/2601.15397)

### Inferences
- Suggested pipeline for this project: strip the known Hungarian suffix, normalize spelling to Hungarian phonetics, then match with phonetic edit distance against the library plus a confidence threshold; invoke the LLM only below the threshold. A library of 10^3-10^5 names should match in low milliseconds on CPU (estimate, not measured).
- The closed-set property is a significant benefit: an output restricted to catalog entries cannot hallucinate a nonexistent artist. Wrong-entity selection remains possible.
- Hungarian orthography is close to phonemic, which should help; English names need a dual key (English G2P and Hungarian-reading spelling, e.g. "Massive" vs "Messzív").
- A correction step also fits an intent parser, because the voice assistant only needs the correct catalog entry, not a perfect transcript.

### Gaps
- No published end-to-end latency for local LLM plus catalog-scale phonetic retrieval.
- No Hungarian phonetic-matching or G2P evaluation for English names was found; this was not specifically searched in depth.

## Does fine-tuning on one user's own voice with small data help? How much data, time, and improvement? Does synthetic-TTS entity augmentation help?

### Takeaway
Some benefit is plausible, around 10-25% relative WER in group or anecdotal LoRA results, but no rigorous study covers one speaker with 50-500 sentences, and forgetting is a documented risk. It should come after biasing and retrieval, and be evaluated on held-out entities.

### Cited Findings
- **PI-Whisper (group profiles, not single speaker; Whisper-tiny):** a single LoRA cut WER from 24.51 to 20.23 on L2 Arctic and 13.03 to 10.27 on Common Voice (search snippet). Merged accent and gender profiles added up to 2.78 points (13.7% relative) on L2-Arctic and 1.03 points (10.0%) on Common Voice. LoRA ran 3 epochs on an A6000. Per-speaker data size and training time were not reported — [PI-Whisper](https://arxiv.org/html/2406.15668)
- PI-Whisper overhead is about 0.037 s per profile on a Raspberry Pi 5 and 0.023 s on Jetson Orin Nano, plus about 0.056 s for the classifier — [PI-Whisper](https://arxiv.org/html/2406.15668)
- **Quantised Whisper base.en:** LibriSpeech-SA WER went from 11.22 to 8.51 with LoRA pretraining plus NF4, while full FP32 fine-tuning reached 9.59. The search summary flagged that the paper's relative-reduction figures may not match this table — [Personalisation paper](https://arxiv.org/pdf/2309.09136)
- **Single-voice anecdote (German physiotherapy dictation, Whisper-small LoRA r=8, alpha=32):** WER 43.0% to 34.8% on just 10 held-out dictations; self-reported, possibly poor generalization (search snippet) — [whisper-physio-lora](https://huggingface.co/toniju98/whisper-physio-lora)
- **Single-lecturer fine-tuning:** 5-10 hours of audio helped, but validation error rose as training continued (search snippet) — [UIC paper](https://aseeilin2024.uic.edu/wp-content/uploads/sites/991/2024/03/less-is-more-efficiently-fine-tuning-whisper-foreducational-content.pdf)
- **Korean ASD speech:** LoRA beat full fine-tuning on Whisper-small, reported as CER (search snippet) — [Park et al.](https://www.isca-archive.org/interspeech_2025/park25g_interspeech.pdf)
- **Catastrophic forgetting:** KWS-Whisper fine-tuned on a small dataset had higher MER than base Whisper on real internal data; no forgetting measure was given, and domain mismatch was also cited — [Li et al.](https://arxiv.org/html/2309.09552v4)
- **Synthetic-only adaptation:** WER reductions of 2-30 points on low-resource languages with parameter-efficient fine-tuning, depending on Whisper version (search snippet) — [When Whisper Meets TTS](https://www.vicomtech.org/en/rdi-tangible/publications/publication/when-whisper-meets-tts-domain-adaptation-using-only-synthetic-speech-data)
- **TTS for entities without training:** see Liu et al. B-WER reductions of about 43-44% (English) — [Liu et al.](https://arxiv.org/html/2508.17796v2)

### Inferences
- LoRA looks safer than full fine-tuning for small data, but a voice-only adapter does not teach new names. Entity coverage in the training sentences will likely matter more than speaker adaptation, and held-out names are the honest test.
- A sensible starting experiment is 200-300 of the user's own commands mixed with TTS entity sentences and a Hungarian regularization set, with LoRA on a Whisper or similar model. These numbers are a suggestion, not a published finding.
- TTS engines may pronounce English names the English way, whereas we need the Hungarian way. Feeding respelled names ("Dzsúd") may be necessary; this is untested.
- Parakeet/NeMo fine-tuning at this scale has no evidence here.

### Gaps
- No rigorous study of one speaker with 50-500 sentences, so no data-improvement curve exists. Actual training time on our hardware is unknown.
- No personalisation or TTS-augmentation result for Hungarian or for suffixed foreign entities.
