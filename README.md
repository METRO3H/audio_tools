# Audio Tools

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Svelte](https://img.shields.io/badge/Svelte-5-FF3E00?logo=svelte&logoColor=white)](https://svelte.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)](https://vite.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![pywebview](https://img.shields.io/badge/pywebview-Desktop_App-5C3EE8)](https://pywebview.flowrl.com/)
[![faster-whisper](https://img.shields.io/badge/faster--whisper-Speech_to_Text-8A2BE2)](https://github.com/SYSTRAN/faster-whisper)
[![llama.cpp](https://img.shields.io/badge/llama.cpp-Local_LLMs-000000)](https://github.com/ggml-org/llama.cpp)

A Windows-focused desktop application for audio/video processing, transcription, and AI-assisted localization.  
The application combines a Python backend with a Svelte desktop UI through **pywebview**, while keeping the main processing pipeline local whenever possible.

## Overview

Audio Tools is built around a practical media-processing workflow:

- Process audio and video files with FFmpeg.
- Transcribe speech with **faster-whisper**.
- Translate subtitles, chapter titles, and filenames with local **GGUF LLMs** through `llama-cpp-python`.
- Validate generated translations and retry problematic lines automatically.
- Use an optional offline **NLLB-200** fallback for translations that still fail validation.
- Run transcription locally or delegate it to a compatible **LAN mediator server**.
- Stream progress, logs, generated text, and translation statistics directly to the UI.

The project is designed as a desktop application rather than a browser-hosted web service.

---

## Features

### Media processing

#### Merge
Merge multiple audio files into a single output file using FFmpeg concat.

The merge workflow can also generate embedded chapter metadata based on the source file names and durations.

#### Diverge
Split an audio or video file into multiple segments.

Supported workflows include:

- Fixed-length segments.
- Splitting according to embedded chapters.
- Multiple output formats for audio segmentation.
- Optional `audios/videos/parts` output organization.

#### Audio → Video
Convert audio tracks into MP4 video files.

The video track can use:

- A provided background image.
- A generated black background when no image is selected.

Supported video encoders include:

- CPU / `libx264`
- NVIDIA / `h264_nvenc`
- AMD / `h264_amf`
- Intel / `h264_qsv`

Audio can either be copied directly or encoded to AAC.

---

### Transcription

Speech-to-text is powered by **faster-whisper**.

Supported model sizes include:

`tiny`, `base`, `small`, `medium`, `large-v1`, `large-v2`, `large-v3`

Supported processing devices:

- CUDA
- CPU

The transcription pipeline supports:

- Automatic language detection.
- Explicit language selection.
- Voice activity detection.
- Beam size configuration.
- Word timestamps.
- Initial prompts.
- Sequential batch processing.
- Cancellation.
- Live progress and logs.

Transcription output can be written as:

- `.srt`
- `.vtt`
- `.txt`

### Remote transcription

Transcription can optionally be delegated to a separate machine on the local network.

The client discovers a compatible mediator through UDP broadcast and then communicates using:

- HTTP for status, job creation, and file uploads.
- WebSocket for live job events and cancellation.

This allows the desktop UI to remain on one machine while a dedicated machine handles Whisper inference.

The client currently targets the companion project:

[`METRO3H/ai_server`](https://github.com/METRO3H/ai_server)

If the remote server is unavailable, local transcription remains available.

---

### AI-assisted translation

Translation uses local **GGUF models** through `llama-cpp-python`.

The project has separate translation workflows for:

- SRT subtitle lines.
- Chapter titles embedded in media files.
- File and folder names.

Each workflow has its own prompts and glossary configuration.

#### Translation quality pipeline

The translation system does more than simply call the LLM once.

For block-based subtitle translation, the pipeline can:

1. Translate the block normally.
2. Detect output that appears to remain untranslated.
3. Retry the complete block when a large portion failed validation.
4. Otherwise retry only contiguous groups of problematic lines, using recent translated context.
5. Use an offline NLLB-200 fallback for lines that still fail validation.
6. Preserve the best available result when the fallback is unavailable.

This reduces unnecessary repeated LLM calls while providing an additional recovery path for problematic lines.

### Translation validation

The project uses two different language-detection strategies for different jobs:

- **langid** for quick source-language detection, especially filenames.
- **lingua** for validating whether generated translation text is actually English.

The validation logic also checks for:

- Remaining CJK characters.
- Short romaji-like output.
- Low English confidence in longer text.

### Filename translation safety

Filename translation includes a preview step before changes are applied.

The workflow is:

1. Scan files and directories.
2. Detect which names appear to require translation.
3. Generate a translation preview.
4. Apply only the renames confirmed by the user.

Windows-invalid filename characters are filtered from translated names before renaming.

---

## Architecture

```text
audio_tools/
├── main.py                 # pywebview entry point
├── api.py                  # Backend API exposed to the Svelte frontend
├── config.py               # Paths and processing configuration
├── go.py                   # Build/run helper
│
├── core/
│   ├── actions/
│   │   ├── merge_audio.py
│   │   ├── diverge_audio.py
│   │   └── audio_to_video.py
│   │
│   ├── network/
│   │   └── mediator_client.py
│   │
│   ├── transcription/
│   │   ├── whisper_runner.py
│   │   ├── remote_whisper_runner.py
│   │   └── transcribe_action.py
│   │
│   ├── translation/
│   │   ├── runner.py
│   │   ├── chapters_runner.py
│   │   ├── filenames_runner.py
│   │   ├── model_manager.py
│   │   ├── fallback_translator.py
│   │   ├── prompts.py
│   │   ├── srt.py
│   │   ├── stats.py
│   │   └── stats_db.py
│   │
│   ├── ffmpeg_runner.py
│   ├── hardware_info.py
│   ├── lang_detect.py
│   ├── media_info.py
│   └── models.py
│
├── ffmpeg/
│   ├── ffmpeg.exe
│   ├── ffplay.exe
│   └── ffprobe.exe
│
├── models/                 # Local GGUF translation models
├── stats/                  # Translation statistics database
├── util/
│   └── image_optimizer.py
│
└── frontend/
    ├── src/
    │   ├── lib/
    │   │   ├── components/
    │   │   ├── stores/
    │   │   ├── views/
    │   │   └── utils.js
    │   ├── App.svelte
    │   ├── app.css
    │   └── main.js
    ├── package.json
    └── vite.config.js
```

### Application flow

```text
Svelte UI
   │
   │ pywebview JS bridge
   ▼
Python API (api.py)
   │
   ├── FFmpeg runner ──────────► FFmpeg
   │
   ├── Whisper runner ─────────► faster-whisper
   │
   ├── Remote Whisper runner ──► LAN mediator
   │
   └── Translation runners
          │
          ├── llama.cpp / GGUF
          ├── language validation
          ├── retry logic
          └── NLLB fallback
```

The backend sends progress and log events back to the Svelte frontend through `window.evaluate_js()` and browser `CustomEvent`s.

---

## Tech Stack

### Backend

- Python 3.11+
- pywebview
- FFmpeg
- faster-whisper
- llama-cpp-python
- langid
- lingua-language-detector
- Requests
- websocket-client
- Pillow
- SQLite

### Frontend

- Svelte 5
- Vite
- Tailwind CSS 4

### Translation fallback

- CTranslate2
- Transformers
- SentencePiece
- NLLB-200

---

## Requirements

This project is currently Windows-focused.

You will need:

- **Windows**
- **Python 3.11+**
- **Node.js + npm**
- FFmpeg binaries available under `ffmpeg/`
- Sufficient disk space and RAM/VRAM for the models you choose

GPU acceleration is optional for some workflows, but local Whisper and LLM inference can benefit substantially from a compatible GPU setup.

---

## Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/METRO3H/audio_tools.git
cd audio_tools
```

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
pip install pywebview faster-whisper llama-cpp-python lingua-language-detector langid Pillow
```

Install the frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

### Optional NLLB fallback

The NLLB fallback requires:

```bash
pip install ctranslate2 transformers sentencepiece
```

Then convert the NLLB checkpoint to CTranslate2 format:

```bash
ct2-transformers-converter ^
  --model facebook/nllb-200-distilled-600M ^
  --output_dir models/nllb-200-distilled-600M-ct2 ^
  --quantization int8
```

The application is configured to look for the converted model in:

```text
models/nllb-200-distilled-600M-ct2/
```

The tokenizer is loaded through Hugging Face Transformers and cached locally after its first download.

> The NLLB fallback is optional. If it is missing, the main translation pipeline can continue without it.

---

## Translation models

The translation model manager automatically discovers `.gguf` files inside:

```text
models/
```

For example:

```text
models/
├── Qwen3-8B-Q5_K_M.gguf
└── Sugoi-14B-Ultra-Q2_K.gguf
```

Because model files are large, they are excluded from Git by the project's `.gitignore`.

Place the GGUF models you intend to use inside `models/`.

### Translation configuration

Main translation settings are defined in `config.py`.

Important options include:

```python
TRANSLATION_MODELS_DIR
TRANSLATION_N_GPU_LAYERS
TRANSLATION_N_CTX
TRANSLATION_TEMPERATURE
TRANSLATION_BLOCK_SIZE
TRANSLATION_CONTEXT_LINES
TRANSLATION_MIN_ENGLISH_CONFIDENCE
```

Prompt files and glossaries are stored under:

```text
core/translation/prompts/
```

The frontend can read and save translation prompts and glossaries through the backend API.

---

## Running the application

From the project root:

### Run

```bash
python go.py
```

### Build the frontend, then run

```bash
python go.py --build
```

### Run with pywebview debug tools

```bash
python go.py --debug
```

### Build and run with debug tools

```bash
python go.py --build --debug
```

`go.py --build` runs `npm run build` in the `frontend/` directory and outputs the compiled desktop frontend to:

```text
dist_ui/
```

---

## Frontend development

The frontend is a standard Svelte + Vite project.

To start the Vite development server:

```bash
cd frontend
npm run dev
```

For a normal desktop run, however, the Python application loads the compiled frontend from `dist_ui/index.html`, so changes intended for the desktop shell should be built with:

```bash
npm run build
```

or:

```bash
python go.py --build
```

---

## Output structure

Many workflows organize generated files relative to the selected base folder.

A typical project folder can look like:

```text
project/
├── audios/
├── videos/
├── images/
├── transcriptions/
│   ├── <language>/
│   └── ...
└── ...
```

Specific tools may create additional folders such as:

```text
audios/parts/
videos/parts/
```

The exact output path depends on the selected tool and its configuration.

---

## Persistent data

Translation runs are tracked in:

```text
stats/translation_stats.db
```

The statistics system records information such as:

- Model used.
- Translation configuration.
- Source language.
- Number of processed blocks.
- Model load time.
- Translation time.
- Generated tokens.
- Number of model calls.
- Retry-related statistics.

This data is intended to make translation runs measurable and easier to compare over time.

---

## Project design principles

### Local-first processing

Whenever practical, processing stays on the local machine:

- FFmpeg runs locally.
- Local Whisper can run locally.
- Translation models are loaded locally.
- Translation statistics are stored locally.

Remote transcription is an optional extension rather than a requirement.

### Reuse loaded models

The transcription and translation managers reuse already-loaded models when their configuration has not changed. This avoids unnecessary model reloads between files.

### Explicit frontend/backend boundary

The frontend is responsible for UI state and interaction, while Python owns:

- File system operations.
- FFmpeg execution.
- Model inference.
- Translation pipelines.
- Remote transcription communication.
- Progress and logging events.

This keeps the desktop UI independent from the heavy processing logic.

### Cancellation-aware processing

Long-running operations expose cancellation methods through the backend API. The application also attempts to cancel active work when the pywebview window is closed.

---

## Project status

Audio Tools is a personal/experimental desktop application under active development.

The codebase is functional, but installation and model distribution are not yet packaged into a single installer. In particular:

- Large ML model files are not committed to Git.
- `requirements.txt` currently contains the remote mediator client dependencies, while the main application dependencies are installed separately.
- Some model setup steps, especially the optional NLLB fallback, are manual.

---

## Related project

Remote Whisper transcription can be provided by the companion mediator server:

[`METRO3H/ai_server`](https://github.com/METRO3H/ai_server)

---

## Author

[METRO3H](https://github.com/METRO3H)
