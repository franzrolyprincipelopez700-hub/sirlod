import { useCallback, useEffect, useRef, useState } from "react";
import type { DictationResult } from "./coach-dictation.worker";

type DictationPhase = "idle" | "preparing" | "listening" | "finishing";

interface Recording {
  stream?: MediaStream;
  recorder?: MediaRecorder;
  timer?: number;
}

const modelError = "No se pudo cargar o ejecutar el dictado local. Intenta nuevamente.";
const noVoice = "No se obtuvo texto. Prueba hablando más cerca del micrófono.";

function stopTracks(recording: Recording) {
  recording.stream?.getTracks().forEach((track) => track.stop());
}

async function decodeAudio(clip: Blob) {
  // decodeAudioData also resamples the recording to Whisper's 16 kHz input.
  const context = new OfflineAudioContext(1, 1, 16_000);
  const decoded = await context.decodeAudioData(await clip.arrayBuffer());
  const audio = new Float32Array(decoded.length);
  for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
    const samples = decoded.getChannelData(channel);
    for (let i = 0; i < samples.length; i++) {
      audio[i] += samples[i] / decoded.numberOfChannels;
    }
  }
  return audio;
}

function hasSpeechInput(samples: Float32Array): boolean {
  if (samples.length < 4800) return false;
  // Whisper can produce words on silence. Check that at least one window has a signal first.
  const windowSize = 3200;
  for (let start = 0; start + windowSize <= samples.length; start += windowSize) {
    let energy = 0;
    for (let i = start; i < start + windowSize; i++) energy += samples[i] ** 2;
    if (energy / windowSize >= 0.000008) return true;
  }
  return false;
}

function accessError(error: unknown) {
  const name = error instanceof Error ? error.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Permite el micrófono para SIRLOD en el navegador y vuelve a intentarlo.";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "Conecta o activa un micrófono y vuelve a intentarlo.";
    case "NotReadableError":
    case "TrackStartError":
      return "No se pudo acceder al micrófono. Revisa si otra aplicación lo está usando.";
    default:
      return "No se pudo iniciar la grabación. Revisa el micrófono o escribe la consulta.";
  }
}

export function useCoachDictation() {
  const [phase, setPhase] = useState<DictationPhase>("idle");
  const [notice, setNotice] = useState("");
  const active = useRef<Recording | null>(null);
  const worker = useRef<Worker | null>(null);

  const cancel = useCallback(() => {
    const request = active.current;
    active.current = null;
    if (request) {
      window.clearTimeout(request.timer);
      if (request.recorder?.state === "recording") request.recorder.stop();
      stopTracks(request);
      worker.current?.terminate();
      worker.current = null;
    }
    setPhase("idle");
    setNotice("");
  }, []);

  useEffect(() => () => {
    cancel();
    worker.current?.terminate();
    worker.current = null;
  }, [cancel]);

  function finish() {
    if (active.current?.recorder?.state === "recording") {
      active.current.recorder.stop();
      setPhase("finishing");
      setNotice("Preparando la transcripción…");
    } else {
      cancel();
    }
  }

  async function start(prefix: string, write: (text: string) => void) {
    if (active.current) return;
    if (!navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder !== "function" || typeof OfflineAudioContext !== "function" || typeof Worker !== "function") {
      setNotice("Este navegador no permite grabar y transcribir localmente. Puedes escribir tu consulta.");
      return;
    }

    const request: Recording = {};
    active.current = request;
    setPhase("preparing");
    setNotice("Activando el micrófono…");

    function settle(message: string) {
      if (active.current !== request) return;
      active.current = null;
      window.clearTimeout(request.timer);
      stopTracks(request);
      setPhase("idle");
      setNotice(message);
    }

    function failModel() {
      if (active.current !== request) return;
      worker.current?.terminate();
      worker.current = null;
      settle(modelError);
    }

    async function transcribe(clip: Blob) {
      let samples: Float32Array<ArrayBuffer>;
      try {
        if (!clip.size) {
          settle(noVoice);
          return;
        }
        samples = await decodeAudio(clip);
      } catch {
        settle("No se pudo leer la grabación. Vuelve a intentarlo.");
        return;
      }
      if (active.current !== request) return;
      if (!hasSpeechInput(samples)) {
        settle(noVoice);
        return;
      }

      try {
        const engine = worker.current ??= new Worker(
          new URL("./coach-dictation.worker.ts", import.meta.url),
          { type: "module" },
        );
        engine.onmessage = ({ data }: MessageEvent<DictationResult>) => {
          if (active.current !== request) return;
          switch (data.type) {
            case "loading":
              setNotice("Descargando el modelo de español para el dictado local…");
              break;
            case "transcribing":
              setNotice("Transcribiendo en este dispositivo…");
              break;
            case "result":
              if (data.text) {
                write([prefix.trimEnd(), data.text].filter(Boolean).join(" ").slice(0, 500));
                settle("Revisa el texto y pulsa Enviar cuando esté listo.");
              } else {
                settle(noVoice);
              }
              break;
            case "error":
              failModel();
          }
        };
        engine.onerror = failModel;
        request.timer = window.setTimeout(failModel, 110_000);
        engine.postMessage(samples, [samples.buffer]);
      } catch {
        failModel();
      }
    }

    try {
      request.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false });
      if (active.current !== request) {
        stopTracks(request);
        return;
      }

      const recorder = new MediaRecorder(request.stream);
      request.recorder = recorder;
      const chunks: Blob[] = [];
      recorder.ondataavailable = ({ data }) => {
        if (data.size) chunks.push(data);
      };
      recorder.onerror = () => settle("El micrófono se desconectó. Intenta grabar de nuevo.");
      recorder.onstop = () => {
        window.clearTimeout(request.timer);
        stopTracks(request);
        if (active.current !== request) return;
        setPhase("finishing");
        setNotice("Preparando la transcripción…");
        void transcribe(new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type }));
      };
      recorder.start();
      request.timer = window.setTimeout(() => {
        if (active.current === request && recorder.state === "recording") recorder.stop();
      }, 25_000);
      setPhase("listening");
      setNotice("Grabando… pulsa el micrófono otra vez para transcribir.");
    } catch (error) {
      settle(accessError(error));
    }
  }

  return { phase, notice, start, finish, cancel };
}
