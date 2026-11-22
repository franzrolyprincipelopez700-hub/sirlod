import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  FaArrowRight, FaBolt, FaCalendarAlt, FaHandPaper, FaPaperPlane, FaRegFilePdf,
  FaRegTrashAlt, FaRunning, FaTimes, FaVolleyballBall,
} from "react-icons/fa";
import { API_BASE_URL } from "~/lib/constants";
import type { CoachMotion, CoachPose } from "./coach-scene";
import "./losabot.css";

type Topic = "general" | "horarios" | "reservas" | "documentos" | "permisos" | "losas" | "pausa" | "saludo";
interface Message {
  id: string;
  sender: "bot" | "user" | "error";
  text: string;
  topic?: Topic;
  source?: string;
}
interface HistoryEntry {
  role: "user" | "model";
  parts: { text: string }[];
}

const portrait = "/images/losabot-entrenador.webp";
const welcome: Message = {
  id: "welcome", sender: "bot",
  text: "¡Hola! Soy LosaBot. Te ayudo a encontrar un horario, elegir una losa o preparar tu permiso.",
};

const shortcuts = [
  { label: "Ver horarios", text: "¿Cuáles son los horarios de las losas?", icon: FaCalendarAlt },
  { label: "Cómo reservar", text: "¿Cómo hago una reserva?", icon: FaVolleyballBall },
  { label: "Permiso especial", text: "¿Qué PDF requiere el permiso especial?", icon: FaRegFilePdf },
  { label: "Pausa activa", text: "¿Me guías en una pausa activa?", icon: FaRunning },
];

const userLinks: Partial<Record<Topic, [label: string, href: string]>> = {
  horarios: ["Consultar horarios", "/horario"],
  reservas: ["Buscar un horario", "/horario"],
  permisos: ["Mis permisos", "/permiso"],
  losas: ["Explorar losas", "/losas"],
};
const adminLinks: typeof userLinks = {
  horarios: ["Ver horarios configurados", "/dashboard/configuracion"],
  reservas: ["Ver reservas", "/dashboard/detalle-permisos"],
  documentos: ["Abrir revisión automática", "/dashboard/revision-ia"],
  permisos: ["Ver solicitudes", "/dashboard/permisos"],
  losas: ["Ver losas deportivas", "/dashboard/losas"],
};

function CoachAvatar({ pose, wave }: CoachMotion) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const motion = useRef<CoachMotion>({ pose, wave });

  useEffect(() => { motion.current = { pose, wave }; }, [pose, wave]);

  useEffect(() => {
    let mounted = true;
    let dispose: (() => void) | undefined;
    void import("./coach-scene").then(({ mountCoach }) => {
      if (!mounted || !canvas.current) return;
      const surface = canvas.current;
      dispose = mountCoach(surface, () => motion.current);
      surface.dataset.ready = "true";
    }).catch(() => {
      if (mounted && canvas.current) canvas.current.dataset.ready = "false";
    });
    return () => {
      mounted = false;
      dispose?.();
    };
  }, []);

  return (
    <div className="losabot-avatar-stage" aria-hidden="true">
      <img key={wave} src={portrait} className="losabot-avatar-still" data-greet={wave > 0} alt="" />
      <canvas ref={canvas} data-ready="false" />
    </div>
  );
}

function addMessage(sender: Message["sender"], text: string, details?: Pick<Message, "topic" | "source">): Message {
  return { id: crypto.randomUUID(), sender, text, ...details };
}

function richText(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part
  );
}

export function ChatbotWidget({ canUseAi = false, sessionId }: { canUseAi?: boolean; sessionId?: string }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([welcome]);
  const [pending, setPending] = useState(false);
  const [useAiNext, setUseAiNext] = useState(false);
  const [wave, setWave] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [greeting, setGreeting] = useState(false);
  const [loadedSession, setLoadedSession] = useState<string | undefined>(undefined);
  const storageKey = sessionId ? "losabot:" + sessionId : undefined;

  const launcher = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const request = useRef<AbortController | null>(null);
  const speechTimer = useRef<number | undefined>(undefined);
  const greetingTimer = useRef<number | undefined>(undefined);
  const aiHistory = useRef<HistoryEntry[]>([]);
  const links = canUseAi ? adminLinks : userLinks;
  const pose: CoachPose = pending ? "thinking" : speaking ? "speaking" : "idle";

  useEffect(() => {
    if (!storageKey) return;
    try {
      const saved: unknown = JSON.parse(window.sessionStorage.getItem(storageKey) ?? "null");
      if (Array.isArray(saved) && saved.length > 0) setMessages((saved as Message[]).slice(-48));
    } catch {
      // El chat sigue disponible si el navegador restringe el almacenamiento.
    }
    setLoadedSession(storageKey);
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey || loadedSession !== storageKey) return;
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // Los mensajes aún quedan disponibles durante la sesión del panel.
    }
  }, [loadedSession, messages, storageKey]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [messages, pending, open]);

  useEffect(() => () => {
    request.current?.abort();
    window.clearTimeout(speechTimer.current);
    window.clearTimeout(greetingTimer.current);
  }, []);

  function close() {
    setOpen(false);
    setUseAiNext(false);
    window.requestAnimationFrame(() => launcher.current?.focus());
  }

  function greet() {
    setWave((value) => value + 1);
    setGreeting(true);
    window.clearTimeout(greetingTimer.current);
    greetingTimer.current = window.setTimeout(() => setGreeting(false), 1800);
  }

  function reset() {
    request.current?.abort();
    request.current = null;
    aiHistory.current = [];
    setDraft("");
    setMessages([welcome]);
    setPending(false);
    setUseAiNext(false);
    setSpeaking(false);
    input.current?.focus();
  }

  function append(message: Message) {
    setMessages((items) => [...items.slice(-47), message]);
  }

  async function send(text: string, askAi = false) {
    const message = text.trim();
    if (!message || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setSpeaking(false);
    setUseAiNext(false);
    append(addMessage("user", message));
    setDraft("");
    try {
      const endpoint = askAi ? "consulta-ia" : "";
      const response = await fetch(API_BASE_URL + "/chatbot/" + endpoint, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          ...(askAi ? { history: aiHistory.current } : {}),
        }),
        signal: controller.signal,
      });
      if (response.redirected) throw new Error("Tu sesión venció. Vuelve a iniciar sesión.");
      const payload = await response.json() as { reply?: string; message?: string; topic?: Topic; source?: string };
      if (!response.ok || !payload.reply) {
        throw new Error(payload.message || "LosaBot no pudo responder. Intenta otra vez.");
      }
      if (controller.signal.aborted) return;
      append(addMessage("bot", payload.reply, {
        source: askAi && payload.source === "local" ? "fallback" : payload.source,
        topic: payload.topic,
      }));
      if (askAi && payload.source && payload.source !== "local") {
        aiHistory.current = [
          ...aiHistory.current,
          { role: "user", parts: [{ text: message }] } as HistoryEntry,
          { role: "model", parts: [{ text: [...payload.reply].slice(0, 1000).join("") }] } as HistoryEntry,
        ].slice(-4);
      }
      setSpeaking(true);
      window.clearTimeout(speechTimer.current);
      speechTimer.current = window.setTimeout(() => setSpeaking(false), 1200);
    } catch (error) {
      if (!controller.signal.aborted) {
        append(addMessage("error", error instanceof Error ? error.message : "LosaBot no está disponible."));
      }
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }

  return (
    <div className="losabot-widget" onKeyDown={(event) => {
      if (open && event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    }}>
      {!open && (
        <button type="button" ref={launcher} className="losabot-launcher" id="losabot-open-btn"
          aria-label="Abrir LosaBot" aria-expanded={false} onClick={() => { setOpen(true); greet(); }}>
          <span className="losabot-launcher-portrait" aria-hidden="true"><img src={portrait} alt="" /></span>
          <span>LosaBot</span>
          <span className="losabot-launcher-status" aria-hidden="true" />
        </button>
      )}
      {open && (
        <section className="losabot-panel" role="dialog" aria-labelledby="losabot-title">
          <div className="losabot-hero">
            <div className="losabot-court" aria-hidden="true" />
            <div className="losabot-tools">
              <button type="button" onClick={reset} aria-label="Borrar conversación" title="Borrar conversación">
                <FaRegTrashAlt aria-hidden="true" />
              </button>
              <button type="button" onClick={close} aria-label="Cerrar LosaBot" title="Cerrar LosaBot">
                <FaTimes aria-hidden="true" />
              </button>
            </div>
            <div className="losabot-intro">
              <h2 id="losabot-title">LosaBot</h2>
              <p>Tu entrenador de cancha</p>
              <button type="button" onClick={greet} className="losabot-wave">
                <FaHandPaper aria-hidden="true" /> Saludar
              </button>
              <span className="sr-only" role="status">{greeting ? "LosaBot te devuelve el saludo." : ""}</span>
            </div>
            <CoachAvatar pose={pose} wave={wave} />
          </div>

          <div className="losabot-chat" ref={scroll} role="log" aria-label="Conversación con LosaBot">
            {messages.map((message) => {
              const action = message.topic ? links[message.topic] : undefined;
              return (
                <div key={message.id} className={"losabot-message losabot-message--" + message.sender}>
                  <div className="losabot-bubble">
                    <span className="sr-only">{message.sender === "user" ? "Tú: " : "LosaBot: "}</span>
                    <p>{richText(message.text)}</p>
                    {message.source === "fallback" && <small>DeepSeek no respondió. Se usó la guía local.</small>}
                    {message.source && !["local", "fallback"].includes(message.source) && (
                      <small className="losabot-reply-source"><FaBolt aria-hidden="true" /> Respuesta con IA</small>
                    )}
                    {action && <Link to={action[1]} onClick={close}>{action[0]} <FaArrowRight aria-hidden="true" /></Link>}
                  </div>
                </div>
              );
            })}
            {pending && <p className="losabot-wait"><span aria-hidden="true" /> LosaBot está preparando la respuesta…</p>}
          </div>

          <div className="losabot-shortcuts" aria-label="Consultas rápidas">
            {shortcuts.map(({ label, text, icon: Icon }) => (
              <button key={label} type="button" onClick={() => void send(text)} disabled={pending}>
                <Icon aria-hidden="true" /> {label}
              </button>
            ))}
          </div>
          <div className="losabot-composer">
            {canUseAi && (
              <div className="losabot-modes">
                <span>{useAiNext ? "La próxima consulta usará DeepSeek y puede consumir saldo." : "Guía local · Sin tokens"}</span>
                <button type="button" onClick={() => setUseAiNext(!useAiNext)} disabled={pending} aria-pressed={useAiNext}>
                  <FaBolt aria-hidden="true" /> Usar IA
                </button>
              </div>
            )}
            <form onSubmit={(event) => { event.preventDefault(); void send(draft, useAiNext); }}>
              <input id="losabot-input" ref={input} value={draft} maxLength={500}
                onChange={(event) => setDraft(event.target.value)} aria-label="Mensaje para LosaBot"
                placeholder={useAiNext ? "Consulta a DeepSeek sin datos personales" : "Escribe una consulta…"} />
              <button type="submit" id="losabot-send-btn" aria-label="Enviar mensaje" disabled={!draft.trim() || pending}>
                <FaPaperPlane aria-hidden="true" />
              </button>
            </form>
          </div>
        </section>
      )}
    </div>
  );
}
