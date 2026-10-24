// Capacidades de Transcribe tal como las entrega el backend con get_config()["transcription"]
// (core/transcription/options.py). Fixture compartido por las pruebas de la vista.
export const TRANSCRIBE_CAPS = {
   model_sizes: ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"],
   devices: ["cuda", "cpu"],
   compute_types: { cuda: ["float16", "int8_float16", "int8"], cpu: ["float32", "int8"] },
   beam_sizes: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
   languages: [
      { code: "ja", label: "japanese" },
      { code: "zh", label: "chinese" },
   ],
   output_formats: ["srt", "vtt", "txt"],
   defaults: {
      model_size: "large-v3",
      device: "cuda",
      compute_type: "int8_float16",
      beam_size: 5,
      language: "ja",
      vad_filter: true,
      condition_on_previous_text: false,
      word_timestamps: true,
      output_format: "srt",
      initial_prompt: "prompt de config",
   },
};
