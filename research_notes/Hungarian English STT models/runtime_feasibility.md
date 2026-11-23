# Runtime feasibility of candidate STT models on RX 6700 10GB / i7-6700 (as of 2026-10-31)

Labels used throughout:
- **MEASURED** = a published number on the stated hardware. None were taken on an RX 6700 or i7-6700, apart from the user's own baselines.
- **EXTRAPOLATED** = my estimate, with the arithmetic shown. It is not a measurement.

Extrapolation method, used wherever "RX 6700 est." appears:
1. Take transcribe.cpp's published 4750U Vulkan (Radeon RADV RENOIR iGPU) latency on the 11.0 s and 35.3 s samples and scale it proportionally to a 5 s clip.
2. Divide by an assumed RX 6700 vs 4750U iGPU speedup of **2.5x to 8x**.
   - The 2.5x low end comes from: turbo on the iGPU took 4400 ms, versus the user's 470 ms at audio_ctx 400 scaled linearly to a full 1500 ctx (about 1760 ms). This assumes transcribe.cpp runs full ctx, which I did not verify.
   - The 8x high end is my judgement of the raw compute gap between the two GPUs. It is not sourced.
3. The result ignores fixed per-run overhead and host-side decoder time on the slower-threaded i7-6700, so treat it as optimistic for short clips.

## Candidates: how each could run here (runtime, backend, latency, memory, licence, maturity)

### Takeaway
A single new runtime, **transcribe.cpp** (MIT, ggml, with a Vulkan backend), changes the picture: Canary 1B v2, Parakeet v3 and Qwen3-ASR now have a Vulkan path on AMD. Canary 1B v2 and Parakeet v3 are the only candidates found that combine confirmed Hungarian, a usable Hungarian score and an estimated latency inside budget. The Whisper turbo fine-tune stays the known-working fallback.

### Cited Findings
**transcribe.cpp runtime**
- It offers ggml speech-to-text for 16 transcription families and 60+ variants, with CPU, Metal, Vulkan (`-DTRANSCRIBE_VULKAN=ON`), CUDA and HIP/ROCm (`-DTRANSCRIBE_HIP=ON -DAMDGPU_TARGETS=gfx1201`, ROCm 6.1+) backends. It is MIT-licensed, at a 0.2 release with 573 commits and 2.1k stars — [transcribe.cpp README](https://github.com/handy-computer/transcribe.cpp)
- The README gives no model-specific Vulkan limitations — [transcribe.cpp README](https://github.com/handy-computer/transcribe.cpp)

**Published latency on an AMD iGPU (MEASURED: Ryzen 7 PRO 4750U, mean of 3 runs after 1 warmup, compute only, not an RX 6700)**

| Model | Quant | Vulkan 11 s | Vulkan 35.3 s | CPU 11 s | Source |
|---|---|---|---|---|---|
| Parakeet TDT 0.6B v3 | Q8_0 | 453 ms | 1.37 s | 729 ms | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/parakeet-tdt-0.6b-v3.md) |
| Canary 1B v2 | Q8_0 | 759 ms | 2.57 s | 1.15 s | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/canary-1b-v2.md) |
| Canary 1B v2 | Q4_K_M | 732 ms | 2.41 s | 1.15 s | same |
| Qwen3-ASR 0.6B | Q4_K_M | 908 ms | 3.55 s | 1.67 s | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/qwen3-asr-0.6b.md) |
| Qwen3-ASR 0.6B | Q8_0 | 1.03 s | 4.07 s | 1.86 s | same |
| Qwen3-ASR 1.7B | Q4_K_M | 2.02 s | 7.89 s | 3.51 s | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/qwen3-asr-1.7b.md) |
| Qwen3-ASR 1.7B | Q8_0 | 2.47 s | 9.49 s | 4.10 s | same |
| Whisper large-v3-turbo | Q8_0 | 4.40 s | 9.59 s | 9.85 s | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/whisper-large-v3-turbo.md) |
| SenseVoice Small | Q8_0 | ~395 ms | not fetched | not fetched | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/sensevoice-small.md) |
| Voxtral Mini 4B Realtime | Q4_K_M | 13.17 s | 39.16 s | 16.39 s | [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/voxtral-realtime.md) |

**Feasibility matrix**

The latency columns are EXTRAPOLATED for a 5 s clip, not measured. CPU estimates are explained under the CPU question below.

| Candidate | Hungarian? | Best runtime path here | RX 6700 Vulkan est. (5 s) | i7-6700 CPU est. | Weights size on disk | Licence | Verdict |
|---|---|---|---|---|---|---|---|
| Canary 1B v2 | Yes; FLEURS 13.06% Q8_0 | transcribe.cpp Vulkan; onnx-asr CPU | ~40–145 ms | ~320–900 ms | Q8_0 1.14 GB, Q4_K_M 735 MB | CC-BY-4.0 (conflict below) | **Test first** |
| Parakeet TDT v3 | Yes; FLEURS 16.06% Q8_0 | Current ONNX CPU; transcribe.cpp Vulkan | ~25–80 ms | ~200 ms (user-measured) | Q8_0 740 MB, Q4_K_M 485 MB | CC-BY-4.0 | **Test on Vulkan** |
| Qwen3-ASR 1.7B | Yes; FLEURS 32.84% Q8_0 | transcribe.cpp Vulkan; chatllm.cpp Vulkan | Q4_K_M ~115–450 ms; Q8_0 ~140–540 ms | ~960–1120 ms | Q8_0 2.19 GB, Q4_K_M 1.32 GB | Apache-2.0 | Fits only on the optimistic end; accuracy score is weak |
| Qwen3-ASR 0.6B | Yes; FLEURS 56.24% Q8_0 | transcribe.cpp Vulkan; sherpa-onnx INT8 | ~50–200 ms | ~460–510 ms | Q8_0 850 MB, Q4_K_M 590 MB | Apache-2.0 | Fast, but that Hungarian score rules it out |
| Whisper turbo HU fine-tune | Yes | whisper.cpp Vulkan (already working) | 470–530 ms base-model baseline | Not viable | Q8_0 886 MB (base) | MIT per commit-page snippet | **Fallback** |
| Voxtral Mini 4B Realtime | No (13 languages) | transcribe.cpp Vulkan | ~0.7–2.4 s | Not viable | Q4_K_M 2.83 GB | Apache-2.0 | Reject |
| Voxtral Mini 3B / Small 24B | No (8 languages) | transcribe.cpp | Not estimated | Not estimated | Q8_0 5.00 GB / 25.81 GB | Apache-2.0 | Reject |
| Granite Speech 4.1 2B | No (6 languages) | llama.cpp or transcribe.cpp | Not estimated | Not estimated | Q4_K_M 1.60 GB | Apache-2.0 | Reject |
| Granite 5.0 TurboCTC | No (English only) | transcribe.cpp | Not estimated | Not estimated | Q8_0 506 MB | Apache or CC-BY-NC-SA variants | English-only option at most |
| SenseVoice Small | No (zh, yue, en, ja, ko) | transcribe.cpp; sherpa-onnx | ~20–70 ms | Not estimated | Q4_K_M 146 MB | FunASR custom | Reject |
| Moonshine | Not among listed languages | Moonshine library; transcribe.cpp | Not estimated | Not estimated | Not fetched | MIT, with legacy exceptions | Reject |
| Omnilingual ASR | Unconfirmed; check `hun_Latn` | PyTorch / fairseq2 only | See below; likely over budget | Not viable | 6.1 GiB+ FP32 | Apache-2.0 | Reject on runtime |
| SeamlessM4T v2 | Yes (speech input) | PyTorch; no port found | Not estimated | Not estimated | Not fetched | CC-BY-NC 4.0 | Low priority |
| wav2vec2 Hungarian | Yes; ~31% WER on Common Voice | onnx-asr (HF Wav2Vec2 CTC) | No data | No data | Not fetched | Apache-2.0 (some) | Reject on accuracy |

**Evidence per candidate**
- Canary 1B v2 covers 25 languages including Hungarian, with about 978M parameters. Its Hugging Face card gives CC-BY-4.0 and says it is ready for commercial and non-commercial use — [NVIDIA card](https://huggingface.co/nvidia/canary-1b-v2). The transcribe.cpp variant doc also says CC-BY-4.0 — [variant doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/canary-1b-v2.md); contradicted by the family doc, which says Apache-2.0 — [family doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/canary.md). Trust the NVIDIA card.
- `canary-1b-flash` and `canary-180m-flash` cover only en, de, es, fr, and `canary-1b` is CC-BY-NC-4.0 — [family doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/canary.md)
- Parakeet TDT v3 has about 0.6B parameters, is CC BY 4.0, and lists Hungarian at 15.72% FLEURS WER — [NVIDIA card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3). The GGUF Q8_0 scores 16.06% — [transcribe.cpp doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/parakeet-tdt-0.6b-v3.md). Parakeet v2 is English only — [onnx-asr](https://github.com/istupakov/onnx-asr)
- Qwen3-ASR lists Hungarian among 30 languages — [mirror of the model card](https://huggingface.co/yun196/Qwen3-ASR-1.7B). The official report and blog give Apache 2.0 — [arXiv](https://arxiv.org/pdf/2601.21337), [Alibaba Cloud blog](https://www.alibabacloud.com/blog/qwen3-asr-%26-qwen3-forcedaligner-is-now-open-sourced-robust-streaming-and-multilingual_602843)
- Qwen3-ASR Vulkan GGUF also exists via chatllm.cpp, and OpenVINO INT8 for CPU, in a Windows tool — [aggregator page on QwenASRMiniTool](https://www.sourcepulse.org/projects/27086002). A project listed by sherpa-onnx uses its INT8 export of the 0.6B — [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). I found no llama.cpp PR confirming Qwen3-ASR support.
- Voxtral Mini 4B Realtime has 13 languages, none of them Hungarian, in its FLEURS table. BF16 is stated to need a GPU with at least 16 GB, and vLLM is the recommended runtime. Untested community ports include voxtral.c and a Rust one — [Mistral card](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
- Voxtral 2507 lists 8 languages without Hungarian — [transcribe.cpp doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/voxtral.md)
- Granite Speech 4.1 2B covers en, fr, de, es, pt, ja under Apache 2.0 — [IBM card mirror](https://hugface-5b9.pages.dev/ibm-granite/granite-speech-4.1-2b). GGUF files are published, and a llama.cpp route is stated (`llama-server -hf ibm-granite/granite-speech-4.1-2b-GGUF:Q8_0`) — same source as reported by search, plus the [transcribe.cpp GGUF](https://huggingface.co/handy-computer/granite-speech-4.1-2b-gguf)
- Granite 5.0 TurboCTC is English only, about 473M parameters, with an Apache variant and a CC-BY-NC-SA `-nc` variant — [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/granite-speech-5.0-turboctc.md)
- SenseVoice covers zh, yue, en, ja, ko under the FunASR model licence — [doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/sensevoice-small.md)
- Moonshine's repo lists en, es, zh, ja, ko, vi, uk, ar. Its code and models are MIT by default, except non-English legacy non-streaming models under a non-commercial community licence — [Moonshine repo](https://github.com/moonshine-ai/moonshine)
- Omnilingual ASR is Apache-2.0 and built on fairseq2 with its own Python pipeline. MEASURED on an A100 in BF16 with 30 s audio: the 300M LLM variant uses about 5 GiB VRAM at RTF 0.090, and the 3B about 10 GiB at 0.093. No ONNX or ggml port is mentioned — [Meta card](https://huggingface.co/facebook/omniASR-LLM-3B/blob/main/README.md)
- SeamlessM4T v2 is CC-BY-NC 4.0 and lists Hungarian for speech input — [Meta card](https://huggingface.co/facebook/seamless-m4t-v2-large/blob/16579d41e2fd5ca128e348506767162142666271/README.md)
- wav2vec2 Hungarian: jonatasgrosman reports 31.40% WER — [card](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-hungarian). infinitejoy reports about 31% under Apache-2.0 — [card](https://huggingface.co/infinitejoy/wav2vec2-large-xls-r-300m-hungarian/blob/main/README.md). onnx-asr supports HF Wav2Vec2 CTC — [onnx-asr](https://github.com/istupakov/onnx-asr)
- Newer families also in transcribe.cpp: Cohere Transcribe, Fun-ASR-Nano, MOSS-Transcribe-Diarize, Nemotron streaming, and Parakeet variants `parakeet-ultra`, `orukeet`, `phonon-2` — [README](https://github.com/handy-computer/transcribe.cpp)

### Inferences
- FLEURS Hungarian order on the transcribe.cpp docs (Q8_0): Canary 13.06 < turbo 15.07 < Parakeet 16.06 < Qwen 1.7B 32.84 < Qwen 0.6B 56.24. The Qwen gap is large enough that it could reflect a language-handling problem in the evaluation rather than the model. Test it on your own clips before dismissing it. A single FLEURS score is thin evidence, and the sibling accuracy research should take precedence.
- Non-Whisper models scale with clip length, whereas Whisper pays for its encoder context regardless. On 1–5 s clips that favours Canary and Parakeet more than long-audio benchmarks suggest. The evidence: Parakeet goes 453 ms to 1.37 s between samples, near proportional, while turbo's 11 s sample already costs 4.4 s.
- Omnilingual: even an A100 at RTF 0.09 implies about 450 ms for 5 s if time scales with audio (EXTRAPOLATED). An RX 6700 under unofficial ROCm would almost certainly exceed the budget. The smallest variant's 5 GiB also leaves little VRAM for the LLM.
- VRAM planning (EXTRAPOLATED from file sizes): Canary or Parakeet should fit alongside an LLM on 10 GB; actual use exceeds file size by an unmeasured working-set amount.

### Gaps
- No published measurement of any candidate on an RX 6700 or other Navi 22 card. The extrapolated figures carry wide error; a one-hour bench on the actual card would replace them.
- No runtime VRAM or RAM figures on the transcribe.cpp pages; only file sizes.
- Hungarian coverage for Cohere Transcribe, Fun-ASR-Nano, MOSS and the newer Parakeet variants was not checked. Whether a Voxtral Transcribe 2 batch model has open weights was not confirmed.
- Omnilingual `hun_Latn` was not confirmed; the card links `lang_ids.py`.
- FunASR's MODEL_LICENSE text was not retrieved.

## AMD backends: Vulkan, ONNX Runtime, PyTorch ROCm, or CPU only? Navi 22 evidence

### Takeaway
ggml Vulkan is the only low-friction AMD GPU path. ONNX Runtime has no Vulkan execution provider, has removed its ROCm provider, and its remaining routes (MIGraphX, WebGPU) have no RX 6700 evidence. PyTorch-only models effectively mean ROCm with an override, which your LLM result already suggests is the slower route.

### Cited Findings
- ONNX Runtime's execution provider list has AMD ROCm, MIGraphX and Vitis AI entries plus WebGPU, but no Vulkan entry — [ORT docs](https://onnxruntime.ai/docs/execution-providers/)
- ORT v1.23.0 removed the ROCm EP from the source tree and recommends MIGraphX or Vitis AI. This comes from release notes reproduced in a Dependabot PR, so it is secondhand — [PR copy](https://github.com/jchunk-io/jchunk/pull/89)
- onnx-asr still lists ROCm and WebGPU among supported providers — [onnx-asr](https://github.com/istupakov/onnx-asr). This is in tension with the removal above; ROCm would presumably need an older ORT.
- A Vulkan tutorial describes ORT's WebGPU provider using Vulkan on Linux — [Vulkan docs](https://docs.vulkan.org/tutorial/latest/ML_Inference/Third_Party_Libraries/02_onnx_runtime.html). Microsoft marks the WebGPU EP experimental on Windows ML, and lists MIGraphX there as needing RDNA 3 or later — [Microsoft](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers?tabs=winml2). The RDNA 3 requirement is for Windows ML specifically, and the RX 6700 is RDNA 2.
- AMD's Whisper ONNX package validates MIGraphX in FP32 and FP16, with a one-time 30+ minute graph compile on first GPU run — [AMD on HF](https://huggingface.co/AMD-PAVS-AI/whisper)
- Community guidance for gfx1031 (RX 6700 XT, 6750 XT, 6700) is `HSA_OVERRIDE_GFX_VERSION=10.3.0`, and AMD's support matrix does not list the card — [community guide](https://localaimaster.com/blog/rocm-unsupported-gpu-hsa-override)
- transcribe.cpp HIP's documented target example is gfx1201 — [README](https://github.com/handy-computer/transcribe.cpp)
- A llama.cpp report on an RX 6800 XT describes a Vulkan segfault in llama-bench on RADV from build b139 — [llama.cpp #22992](https://github.com/ggml-org/llama.cpp/issues/22992)
- sherpa-onnx's README lists NPU backends and Jetson GPU, and does not mention Vulkan, AMD or ROCm — [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- CTranslate2: community sources conflict, with one gist claiming ROCm through CTranslate2 and another saying modified builds are required — [gist A](https://gist.github.com/danielrosehill/278b1719598093767126e52105ae076e), [gist B](https://gist.github.com/danielrosehill/f7ae5e659a02e32d056eb7887203b7a4). One project reports a source build on gfx1151 — [whisper-rocm](https://github.com/davidguttman/whisper-rocm)

### Inferences
- Treat faster-whisper / CTranslate2 as CPU-only here unless you accept an unofficial source build.
- Treat sherpa-onnx and onnx-asr as CPU-only here. WebGPU is a possible experiment, not a plan.
- Keep transcribe.cpp on Vulkan rather than HIP. HIP would likely need a custom gfx1031 or override build, and your LLM result suggests no gain.
- Pin known-good Mesa and transcribe.cpp commits, since Vulkan regressions on RDNA 2 do happen in the ggml ecosystem.

### Gaps
- I found no official statement of RDNA 2 support for MIGraphX on Linux, and no report of MIGraphX on an RX 6700.
- I found no issue reports specific to transcribe.cpp on RADV discrete cards, which may just mean limited search coverage.
- WebGPU EP on Linux with AMD has no latency figures in anything I found.

## Real-time factor and latency measurements for short clips on similar GPUs or a 4-core CPU

### Takeaway
No short-clip data exists on comparable hardware. The closest figures are 11 s samples on a Ryzen 4750U iGPU, and CPU figures on faster or smaller machines, so everything for 1–5 s clips here is extrapolated.

### Cited Findings
- 4750U figures are tabled above. They are compute-only (mel + encode + decode) — [Parakeet doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/parakeet-tdt-0.6b-v3.md)
- MEASURED on 9800X3D CPU: Parakeet v2/v3 36 RTFx, Canary v2 8 RTFx. On Cortex-A53: Parakeet 1.0 RTFx — [onnx-asr](https://github.com/istupakov/onnx-asr)
- MEASURED on 2 x86-64 vCPUs (one 16.78 s clip, single author, agent-run): ONNX FP32 via onnx-asr RTF 0.328 with 2,667 MB peak; HF Transformers BF16 RTF 0.519; parakeet.cpp GGUF Q6_K RTF 0.708 with 928 MB peak — [benchmark post](https://bittide.aicompass.dev/article/cf69f0e5-d5d9-4cf3-a36d-fc6800a4bff0)
- An academic report found ONNX Parakeet and Canary variants above 6x real time on CPU, with quantized slightly faster than FP32 — [arXiv 2604.14493](https://arxiv.org/pdf/2604.14493)

### Inferences
- **EXTRAPOLATED i7-6700 CPU estimates**, anchored on your measured Parakeet 200 ms and scaled by published ratios to Parakeet:
  - Canary: 1.58x per transcribe.cpp CPU, 4.5x per onnx-asr, so about 320–900 ms. The two sources disagree widely, so measure before relying on it.
  - Qwen 0.6B: 2.3–2.55x, so about 460–510 ms.
  - Qwen 1.7B: 4.8–5.6x, so about 960–1120 ms.
  - Turbo: 13.5x, about 2.7 s, which is not viable.
  - These mix ONNX and GGUF ratios, and clip length behind your 200 ms is taken as similar.
- For RAM, GGUF uses far less than ONNX FP32 in the one comparison, while ONNX is faster. Your int8 ONNX sits between; 8 GB LXC is fine for any Canary, Parakeet or 0.6B path, and 1.7B Q8_0 at 2.19 GB is probably fine too (EXTRAPOLATED).

### Gaps
- No RTF for SenseVoice or Moonshine on x86 CPU was found.
- No short-clip (1–5 s) latency data was found for anything; short clips may have proportionally higher fixed overhead than these proportional estimates assume.
- Your 200 ms Parakeet baseline's clip length was not stated.

## Can Whisper fine-tunes get faster here?

### Takeaway
Modest wins only. Sizing audio_ctx per clip is the most promising change, q8 vs q5 is unlikely to change speed on GPU, and encoder ONNX has no good AMD route. Expect perhaps 350–400 ms greedy on 5 s clips (EXTRAPOLATED), which would not catch Parakeet or Canary if those perform as estimated.

### Cited Findings
- On 4750U Vulkan, turbo Q8_0 vs Q4_K_M is 4.40 s vs 4.45 s; on M4 Metal 304 ms vs 291 ms — [turbo doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/whisper-large-v3-turbo.md)
- Community notes call Q8_0 a sweet spot with minor quality loss at nearly double speed, and Q5_0 the last acceptable quant — [Pomni quants](https://huggingface.co/Pomni/whisper-large-v3-turbo-ggml-allquants). A legacy i5-460M CPU test reached different conclusions on q5_0 vs q8_0 — [whisper.cpp #3752](https://github.com/ggml-org/whisper.cpp/discussions/3752). Neither concerns AMD Vulkan.
- The whisper.cpp README covers OpenVINO for x86 CPUs and Intel GPUs, Core ML and ANE paths, and a VitisAI cache for Ryzen AI NPUs, none of which accelerate a discrete Radeon; the only applicable GPU path is Vulkan — [whisper.cpp README](https://github.com/ggml-org/whisper.cpp/blob/master/README.md)
- `sarpba/whisper-hu-large-v3-turbo-finetuned` is the strongest Hungarian turbo option on the author's tests: Common Voice WER 12.67 vs base turbo 23.03; base turbo hallucinated on VoxPopuli (WER 111.51 vs 18.69). On FLEURS the base is marginally better (21.09 vs 22.07) — [sarpba results](https://huggingface.co/sarpba/whisper-teszt-eredmenyek). These are the fine-tune author's own results.
- I found no ggml conversion of that fine-tune; it would need converting — [HF repo](https://huggingface.co/sarpba/whisper-hu-large-v3-turbo-finetuned/tree/23d91f4bd8d8057127cad53dc342093240f391ce)
- Community reports link short clips to raised hallucination rates, and suggest fixing the language explicitly — [arXiv 2501.11378](https://arxiv.org/html/2501.11378v1), [guide](https://github.com/ffmpegkit-maintained/whisper/wiki/Getting-Good-Results)

### Inferences
- Whisper encodes about 50 context frames per second, so audio_ctx 400 covers 8 s. Your clips cap at 5 s, so 300 (6 s margin) should be safe, or set it per clip (EXTRAPOLATED: if cost scales linearly, 300 gives about 350–390 ms greedy).
- Q8 vs Q5 on GPU: choose on accuracy, since speed looks flat in the only same-backend data. That data is Q8_0 vs Q4_K_M, not Q5_0.
- Beam 5 costs about 60 ms in your baseline. Greedy on a fine-tune with a fixed language is the cheap saving.
- A language lock (or two-pass hu/en) avoids auto-detect time and errors, though that needs testing on mixed-language use.
- Encoder ONNX is not worth pursuing, given the backend findings above. A CPU OpenVINO encoder is very unlikely to beat Vulkan on this CPU.

### Gaps
- I found no published audio_ctx vs accuracy or latency data on Vulkan, so its accuracy risk is unquantified. Test it against your Hungarian clips, particularly at 300 and below.
- I did not search specifically for a Hungarian distil-Whisper. None surfaced in the Hungarian fine-tune search, so treat as "none found", not "none exists".

## Which licences block or restrict home use?

### Takeaway
None blocks private home use. The NC licences matter only if the project becomes commercial, and CC-BY models just need attribution when redistributed.

### Cited Findings
- Apache-2.0: Qwen3-ASR ([arXiv](https://arxiv.org/pdf/2601.21337)), Voxtral Realtime ([card](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)), Omnilingual ([card](https://huggingface.co/facebook/omniASR-LLM-3B/blob/main/README.md)), Granite 4.1 ([card mirror](https://hugface-5b9.pages.dev/ibm-granite/granite-speech-4.1-2b))
- CC-BY-4.0: Parakeet v3 ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)), Canary 1B v2 ([card](https://huggingface.co/nvidia/canary-1b-v2))
- Non-commercial: SeamlessM4T v2 CC-BY-NC 4.0 ([card](https://huggingface.co/facebook/seamless-m4t-v2-large/blob/16579d41e2fd5ca128e348506767162142666271/README.md)), `canary-1b` CC-BY-NC-4.0 ([doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/canary.md)), Granite 5.0 `-nc` CC-BY-NC-SA-4.0 ([doc](https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/docs/models/granite-speech-5.0-turboctc.md)), Moonshine legacy non-English non-streaming models ([repo](https://github.com/moonshine-ai/moonshine))
- Custom: SenseVoice's "other" tag links to FunASR's MODEL_LICENSE — [HF README](https://huggingface.co/FunAudioLLM/SenseVoiceSmall/raw/refs%2Fpr%2F1/README.md)
- Fine-tunes: `sarpba` turbo fine-tune shows MIT per a commit-page snippet — [HF](https://huggingface.co/sarpba/whisper-hu-large-v3-turbo-finetuned/commits/23d91f4bd8d8057127cad53dc342093240f391ce/.gitattributes). The Maxdorger29 LoRA is MIT and notes OpenAI's terms for the base model — [HF](https://huggingface.co/Maxdorger29/whisper-large-v3-hungarian-lora)
- transcribe.cpp and its vendored ggml are MIT — [README](https://github.com/handy-computer/transcribe.cpp)

### Inferences
- My reading, not legal advice: a self-hosted personal assistant is non-commercial use, so even CC-BY-NC does not block it. Licence should not drive this choice. Keep NC models out if you ever plan to sell the system.

### Gaps
- FunASR MODEL_LICENSE terms were not read, and the jonatasgrosman wav2vec2 licence was not confirmed. The `sarpba` licence should be confirmed on the model card. GGUF repacks' own licence files were not checked.
