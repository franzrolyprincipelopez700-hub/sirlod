import { useCallback, useEffect, useRef, useState } from "react";
import type { CoachGesture, CoachSpeechBeat } from "./coach-scene";

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

const gestures: CoachGesture[] = ["offer-left", "offer-right", "explain", "point"];
function speechGesture(text: string, fallback: CoachGesture): CoachGesture {
  const words = text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
  if (/\b(primero|segundo|tercero|paso|despues|por ultimo)\b/.test(words)) return "count";
  if (/\b(equipo|vamos|bienvenido|perfecto|excelente)\b/.test(words)) return "cheer";
  if (/\b(horarios?|turno|cancha|fecha|consulta en|pulsa)\b/.test(words)) return "point";
  if (/\b(opciones|elige|alternativas|puedes|permiso|requisitos)\b/.test(words)) return "explain";
  return fallback;
}

export function useCoachVoice() {
  const [enabled, setEnabled] = useState(true);
  const [status, setStatus] = useState<VoiceStatus>("loading");
  const [speaking, setSpeaking] = useState(false);
  const enabledRef = useRef(true);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const queued = useRef<string | null>(null);
  const speechBeat = useRef<CoachSpeechBeat | null>(null);
  const gestureTimer = useRef<number | undefined>(undefined);

  const stop = useCallback(() => {
    queued.current = null;
    window.clearInterval(gestureTimer.current);
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
    let sequence = 0;
    let previous: CoachGesture | undefined;
    function nextGesture(text: string): CoachGesture {
      const fallback = gestures[sequence++ % gestures.length];
      const requested = speechGesture(text, fallback);
      const result = previous === requested
        ? gestures[(gestures.indexOf(requested) + 1) % gestures.length]
        : requested;
      previous = result;
      return result;
    }

    function speakPart(index: number) {
      const segment = segments[index];
      if (!segment || !voice) return;
      const spoken = new SpeechSynthesisUtterance(segment);
      utterance.current = spoken;
      spoken.voice = voice;
      spoken.lang = voice.lang;
      spoken.rate = 0.96;
      spoken.pitch = 1.04;
      let lastBoundaryAt = 0;
      spoken.onstart = () => {
        if (utterance.current !== spoken) return;
        const now = performance.now();
        speechBeat.current = {
          at: now, openness: 0.65, rounded: false, gesture: nextGesture(segment.slice(0, 55)), gestureAt: now,
        };
        setSpeaking(true);
        gestureTimer.current = window.setInterval(() => {
          if (utterance.current !== spoken) return;
          const active = speechBeat.current;
          const tick = performance.now();
          if (!active || tick - lastBoundaryAt < 1000 || tick - active.gestureAt < 1450) return;
          const position = Math.min(segment.length - 1, Math.floor((tick - now) / 75));
          speechBeat.current = {
            ...active,
            gesture: nextGesture(segment.slice(position, position + 38)),
            gestureAt: tick,
          };
        }, 350);
      };
      spoken.onboundary = (event) => {
        if (utterance.current !== spoken || event.name === "sentence") return;
        const word = segment.slice(event.charIndex).match(/^[^\s,.!?]+/)?.[0] ?? "";
        const vowel = word.normalize("NFD").toLowerCase().match(/[aeiou]/)?.[0] ?? "a";
        const now = performance.now();
        lastBoundaryAt = now;
        const active = speechBeat.current;
        const changeGesture = !active || now - active.gestureAt > 1130;
        speechBeat.current = {
          at: now,
          openness: vowel === "a" || vowel === "e" ? 1 : 0.66,
          rounded: vowel === "o" || vowel === "u",
          gesture: changeGesture ? nextGesture(segment.slice(event.charIndex, event.charIndex + 38)) : active.gesture,
          gestureAt: changeGesture ? now : active.gestureAt,
        };
      };
      const ended = () => {
        window.clearInterval(gestureTimer.current);
        utterance.current = null;
        speechBeat.current = null;
        setSpeaking(false);
      };
      spoken.onend = () => {
        if (utterance.current !== spoken) return;
        window.clearInterval(gestureTimer.current);
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
