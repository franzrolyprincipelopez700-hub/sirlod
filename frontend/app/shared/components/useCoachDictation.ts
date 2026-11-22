import { useCallback, useEffect, useRef, useState } from "react";

type DictationPhase = "idle" | "preparing" | "listening" | "finishing";
type LanguageStatus = "available" | "downloadable" | "downloading" | "unavailable";
type LanguageOptions = { langs: string[]; processLocally: true };

interface DictationResult {
  isFinal: boolean;
  0?: { transcript: string };
}

interface LocalRecognition {
  lang: string;
  processLocally: boolean;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: { results: ArrayLike<DictationResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface LocalRecognitionConstructor {
  new (): LocalRecognition;
  available(options: LanguageOptions): Promise<LanguageStatus>;
  install(options: LanguageOptions): Promise<boolean>;
}

const spanishLocales = ["es-PE", "es-MX", "es-ES", "es-US"];
const preparationMessage = "Preparando el dictado local… La primera vez puede descargar el español.";
const errors: Record<string, string> = {
  "not-allowed": "El navegador necesita permiso para usar el micrófono.",
  "service-not-allowed": "El navegador no permite usar el dictado local.",
  "audio-capture": "No se encontró un micrófono disponible.",
  "no-speech": "No se detectó voz. Intenta dictar de nuevo.",
  "language-not-supported": "El español local no está disponible en este navegador.",
};

function localRecognition(): LocalRecognitionConstructor | undefined {
  const browser = window as Window & {
    SpeechRecognition?: LocalRecognitionConstructor;
    webkitSpeechRecognition?: LocalRecognitionConstructor;
  };
  const engine = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
  if (engine && "processLocally" in engine.prototype &&
    typeof engine.available === "function" && typeof engine.install === "function") return engine;
}

async function getLocalLanguage(engine: LocalRecognitionConstructor): Promise<string | undefined> {
  const options = (lang: string): LanguageOptions => ({ langs: [lang], processLocally: true });
  const checks = await Promise.all(spanishLocales.map(async (lang) => {
    try {
      return { lang, status: await engine.available(options(lang)) };
    } catch {
      return { lang, status: "unavailable" as const };
    }
  }));
  const installed = checks.find(({ status }) => status === "available");
  if (installed) return installed.lang;

  const candidate = checks.find(({ status }) => status === "downloading" || status === "downloadable");
  if (!candidate) return;
  if (await engine.install(options(candidate.lang))) return candidate.lang;
}

export function useCoachDictation() {
  const [phase, setPhase] = useState<DictationPhase>("idle");
  const [notice, setNotice] = useState("");
  const recognizer = useRef<LocalRecognition | null>(null);
  const preparing = useRef(false);
  const run = useRef(0);
  const listeningTimer = useRef<number | undefined>(undefined);

  const cancel = useCallback(() => {
    run.current++;
    preparing.current = false;
    window.clearTimeout(listeningTimer.current);
    const active = recognizer.current;
    recognizer.current = null;
    active?.abort();
    setPhase("idle");
    setNotice("");
  }, []);

  useEffect(() => () => cancel(), [cancel]);

  function finish() {
    if (!recognizer.current || phase !== "listening") {
      cancel();
      return;
    }
    window.clearTimeout(listeningTimer.current);
    setPhase("finishing");
    setNotice("Terminando el dictado…");
    recognizer.current.stop();
  }

  async function start(prefix: string, write: (text: string) => void) {
    if (preparing.current || recognizer.current) return;
    const engine = localRecognition();
    if (!engine) {
      setNotice("Este navegador no admite dictado local en español. Puedes seguir escribiendo.");
      return;
    }

    const attempt = ++run.current;
    preparing.current = true;
    setPhase("preparing");
    setNotice(preparationMessage);
    let language: string | undefined;
    try {
      language = await getLocalLanguage(engine);
    } catch {
      // Algunos dispositivos impiden la descarga del paquete de idioma.
    }
    if (attempt !== run.current) return;
    if (!language) {
      preparing.current = false;
      setPhase("idle");
      setNotice("No se pudo preparar el español para el dictado local.");
      return;
    }

    const active = new engine();
    recognizer.current = active;
    preparing.current = false;
    active.processLocally = true;
    active.lang = language;
    active.continuous = false;
    active.interimResults = true;
    let heardFinal = false;
    const original = prefix.trimEnd();
    const writeTranscript = (transcript: string) => {
      const text = [original, transcript].filter(Boolean).join(" ");
      write(text.slice(0, 500));
    };
    active.onstart = () => {
      if (recognizer.current !== active) return;
      setPhase("listening");
      setNotice("Escuchando…");
      listeningTimer.current = window.setTimeout(() => {
        if (recognizer.current !== active) return;
        setPhase("finishing");
        setNotice("Terminando el dictado…");
        active.stop();
      }, 25_000);
    };
    active.onresult = (event) => {
      if (recognizer.current !== active) return;
      const results = Array.from(event.results);
      const final = results.filter((result) => result.isFinal);
      heardFinal = final.some((result) => !!result[0]?.transcript.trim());
      const transcript = results.map((result) => result[0]?.transcript.trim() ?? "").filter(Boolean).join(" ");
      writeTranscript(transcript);
    };
    active.onerror = ({ error }) => {
      if (recognizer.current !== active) return;
      recognizer.current = null;
      window.clearTimeout(listeningTimer.current);
      if (!heardFinal) write(original);
      setPhase("idle");
      setNotice(errors[error] ?? "No se pudo completar el dictado local. Puedes escribir tu consulta.");
    };
    active.onend = () => {
      if (recognizer.current !== active) return;
      recognizer.current = null;
      window.clearTimeout(listeningTimer.current);
      setPhase("idle");
      if (!heardFinal) write(original);
      setNotice(heardFinal ? "Revisa el texto y pulsa Enviar cuando esté listo." : "No se detectó voz. Intenta de nuevo.");
    };
    try {
      if (active.processLocally !== true) throw new Error("El navegador no activó el dictado local");
      active.start();
    } catch {
      cancel();
      setNotice("No se pudo iniciar el micrófono para el dictado local.");
    }
  }

  return { phase, notice, start, finish, cancel };
}
