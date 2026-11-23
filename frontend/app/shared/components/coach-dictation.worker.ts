import { env, pipeline } from "@huggingface/transformers";
import type { AutomaticSpeechRecognitionPipeline } from "@huggingface/transformers";

export type DictationResult =
  | { type: "loading" | "transcribing" | "error" }
  | { type: "result"; text: string };

const model = "onnx-community/whisper-tiny";
const revision = "ff4177021cc41f7db950912b73ea4fdf7d01d8e7";

// The CDN distributes the pinned engine and the model weights. It never receives audio.
env.allowLocalModels = false;
env.useBrowserCache = true;
if (env.backends.onnx.wasm) {
  env.backends.onnx.wasm.numThreads = 1;
  env.backends.onnx.wasm.wasmPaths =
    "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0-dev.20250409-89f8206ba4/dist/";
}

const createRecognizer = pipeline as unknown as (
  task: "automatic-speech-recognition",
  name: string,
  options: { revision: string; device: "wasm"; dtype: "q8" },
) => Promise<AutomaticSpeechRecognitionPipeline>;
let recognizer: Promise<AutomaticSpeechRecognitionPipeline> | undefined;

function notify(message: DictationResult) {
  self.postMessage(message);
}

self.addEventListener("message", async (event: MessageEvent<Float32Array>) => {
  try {
    if (!recognizer) {
      notify({ type: "loading" });
      recognizer = createRecognizer("automatic-speech-recognition", model, {
        revision,
        device: "wasm",
        dtype: "q8",
      });
    }
    const transcribe = await recognizer;
    notify({ type: "transcribing" });
    const result = await transcribe(event.data, {
      language: "spanish",
      task: "transcribe",
      return_timestamps: false,
    });
    notify({ type: "result", text: (Array.isArray(result) ? result[0]?.text : result.text)?.trim() ?? "" });
  } catch (error) {
    if (import.meta.env.DEV) console.warn("Local dictation failed", error);
    recognizer = undefined;
    notify({ type: "error" });
  }
});
