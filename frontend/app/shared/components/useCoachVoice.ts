import { useCallback, useEffect, useRef, useState } from "react";
import type { CoachSpeechBeat } from "./coach-scene";

const preferenceKey = "losabot:voz";
type VoiceStatus = "loading" | "ready" | "unavailable";

function spanishVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  const spanish = voices.filter(({ localService, lang }) => localService && /^es(?:[-_]|$)/i.test(lang));
  return spanish.find(({ lang }) => /^es[-_]pe$/i.test(lang))
    ?? spanish.find(({ name }) => /^Microsoft (Raul|Pablo)\b/i.test(name))
    ?? spanish.find(({ default: preferred }) => preferred)
    ?? spanish.find(({ lang }) => /^es[-_](mx|us|co|ar|cl)$/i.test(lang))
    ?? spanish[0];
}

function speechText(text: string): string {
  const date = new Intl.DateTimeFormat("es-PE", { month: "long", day: "numeric", timeZone: "UTC" });
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[*_\x60#]/g, "")
    .replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (value) => {
      const parsed = new Date(value + "T12:00:00Z");
      return Number.isNaN(parsed.getTime()) ? value : date.format(parsed);
    })
    .replace(/\b(\d{1,2}):(\d{2})\b/g, (_, hours, minutes) =>
      minutes === "00" ? String(Number(hours)) + " en punto" : Number(hours) + " y " + Number(minutes)
    )
    .replace(/\bMB\b/g, "megabytes")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1400);
}

export function useCoachVoice() {
  const [enabled, setEnabled] = useState(true);
  const [status, setStatus] = useState<VoiceStatus>("loading");
  const [speaking, setSpeaking] = useState(false);
  const enabledRef = useRef(true);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const queued = useRef<string | null>(null);
  const speechBeat = useRef<CoachSpeechBeat | null>(null);

  const stop = useCallback(() => {
    queued.current = null;
    if (utterance.current) {
      utterance.current = null;
      window.speechSynthesis.cancel();
    }
    speechBeat.current = null;
    setSpeaking(false);
  }, []);

  const play = useCallback((text: string) => {
    if (!enabledRef.current || !("speechSynthesis" in window)) return;
    const synthesis = window.speechSynthesis;
    const voices = synthesis.getVoices();
    const voice = spanishVoice(voices);
    if (!voice) {
      if (!voices.length) queued.current = text;
      setStatus(voices.length ? "unavailable" : "loading");
      return;
    }
    const words = speechText(text);
    if (!words) return;

    stop();
    setStatus("ready");
    const segments = (words.match(/.{1,175}(?=\s|$)|.{1,175}/g) ?? [])
      .map((part) => part.trim()).filter(Boolean);
    function speakPart(index: number) {
      const segment = segments[index];
      if (!segment || !voice) return;
      const spoken = new SpeechSynthesisUtterance(segment);
      utterance.current = spoken;
      spoken.voice = voice;
      spoken.lang = voice.lang;
      spoken.rate = 0.96;
      spoken.pitch = 1.04;
      spoken.onstart = () => {
        if (utterance.current !== spoken) return;
        speechBeat.current = { at: performance.now(), openness: 0.65, rounded: false };
        setSpeaking(true);
      };
      spoken.onboundary = (event) => {
        if (utterance.current !== spoken || event.name === "sentence") return;
        const word = segment.slice(event.charIndex).match(/^[^\s,.!?]+/)?.[0] ?? "";
        const vowel = word.normalize("NFD").toLowerCase().match(/[aeiou]/)?.[0] ?? "a";
        speechBeat.current = {
          at: performance.now(),
          openness: vowel === "a" || vowel === "e" ? 1 : 0.66,
          rounded: vowel === "o" || vowel === "u",
        };
      };
      const ended = () => {
        utterance.current = null;
        speechBeat.current = null;
        setSpeaking(false);
      };
      spoken.onend = () => {
        if (utterance.current !== spoken) return;
        if (index + 1 < segments.length) speakPart(index + 1);
        else ended();
      };
      spoken.onerror = () => {
        if (utterance.current === spoken) ended();
      };
      synthesis.speak(spoken);
    }
    speakPart(0);
  }, [stop]);

  useEffect(() => {
    try {
      enabledRef.current = localStorage.getItem(preferenceKey) !== "muted";
      setEnabled(enabledRef.current);
    } catch {
      // La preferencia se puede cambiar aunque el navegador bloquee el almacenamiento.
    }
    if (!("speechSynthesis" in window)) {
      setStatus("unavailable");
      return;
    }
    const synthesis = window.speechSynthesis;
    const refresh = () => {
      const voices = synthesis.getVoices();
      if (spanishVoice(voices)) {
        setStatus("ready");
        const text = queued.current;
        if (text) play(text);
      } else if (voices.length) {
        setStatus("unavailable");
        queued.current = null;
      }
    };
    refresh();
    synthesis.addEventListener("voiceschanged", refresh);
    const initialization = window.setTimeout(() => {
      if (!spanishVoice(synthesis.getVoices())) {
        queued.current = null;
        setStatus("unavailable");
      }
    }, 1800);
    return () => {
      window.clearTimeout(initialization);
      synthesis.removeEventListener("voiceschanged", refresh);
      stop();
    };
  }, [play, stop]);

  function toggle() {
    const next = !enabledRef.current;
    enabledRef.current = next;
    setEnabled(next);
    if (!next) stop();
    try {
      localStorage.setItem(preferenceKey, next ? "enabled" : "muted");
    } catch {
      // El estado todavía se mantiene mientras el panel siga abierto.
    }
    return next;
  }

  return { enabled, status, speaking, speechBeat, play, stop, toggle };
}
