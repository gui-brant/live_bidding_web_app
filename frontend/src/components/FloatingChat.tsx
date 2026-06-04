import { useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage } from "../api/auctions";
import { formatLocalDateTime } from "../utils/datetime";

type FloatingChatProps = {
  title?: string;
  statusText?: string;
  messages: ChatMessage[];
  currentUserId?: string | null;
  onSend: (content: string) => Promise<void>;
  disabled?: boolean;
  initialOpen?: boolean;
};

type Point = { x: number; y: number };

const BUTTON_SIZE = 56;
const MARGIN = 16;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const getPointer = (event: MouseEvent | TouchEvent) => {
  if ("touches" in event) {
    const touch = event.touches[0] || event.changedTouches[0];
    return touch ? { x: touch.clientX, y: touch.clientY } : { x: 0, y: 0 };
  }
  return { x: event.clientX, y: event.clientY };
};

const FloatingChat = ({
  title = "Live Chat",
  statusText = "Online",
  messages,
  currentUserId,
  onSend,
  disabled = false,
  initialOpen = false
}: FloatingChatProps) => {
  const [isOpen, setIsOpen] = useState(initialOpen);
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState<Point>(() => ({
    x: window.innerWidth - BUTTON_SIZE - MARGIN,
    y: window.innerHeight - BUTTON_SIZE - MARGIN
  }));
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [windowPos, setWindowPos] = useState<Point>({ x: 0, y: 0 });

  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef({
    dragging: false,
    moved: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0
  });

  useEffect(() => {
    const handleResize = () => {
      setViewport({ width: window.innerWidth, height: window.innerHeight });
      setPosition((prev) => ({
        x: clamp(prev.x, MARGIN, window.innerWidth - BUTTON_SIZE - MARGIN),
        y: clamp(prev.y, MARGIN, window.innerHeight - BUTTON_SIZE - MARGIN)
      }));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen]);

  const windowSize = useMemo(() => {
    const width = Math.min(360, viewport.width - MARGIN * 2);
    const height = Math.min(520, viewport.height - 120);
    return { width, height };
  }, [viewport]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const preferredTop = position.y - windowSize.height - 12;
    let top = preferredTop;
    if (preferredTop < MARGIN) {
      top = position.y + BUTTON_SIZE + 12;
    }
    if (top + windowSize.height > viewport.height - MARGIN) {
      top = clamp(top, MARGIN, viewport.height - windowSize.height - MARGIN);
    }
    const preferredLeft = position.x + BUTTON_SIZE - windowSize.width;
    const left = clamp(preferredLeft, MARGIN, viewport.width - windowSize.width - MARGIN);
    setWindowPos({ x: left, y: top });
  }, [isOpen, position, viewport, windowSize]);

  const handlePointerDown = (event: React.MouseEvent | React.TouchEvent) => {
    if ("button" in event && event.button !== 0) {
      return;
    }
    const nativeEvent = event.nativeEvent as MouseEvent | TouchEvent;
    const point = getPointer(nativeEvent);
    dragState.current = {
      dragging: true,
      moved: false,
      startX: point.x,
      startY: point.y,
      originX: position.x,
      originY: position.y
    };

    const handleMove = (moveEvent: MouseEvent | TouchEvent) => {
      const movePoint = getPointer(moveEvent);
      const dx = movePoint.x - dragState.current.startX;
      const dy = movePoint.y - dragState.current.startY;
      if (!dragState.current.moved && Math.hypot(dx, dy) > 4) {
        dragState.current.moved = true;
      }
      if (!dragState.current.dragging) {
        return;
      }
      setPosition({
        x: clamp(dragState.current.originX + dx, MARGIN, window.innerWidth - BUTTON_SIZE - MARGIN),
        y: clamp(dragState.current.originY + dy, MARGIN, window.innerHeight - BUTTON_SIZE - MARGIN)
      });
    };

    const handleUp = () => {
      const wasMoved = dragState.current.moved;
      dragState.current.dragging = false;
      window.removeEventListener("mousemove", handleMove as EventListener);
      window.removeEventListener("touchmove", handleMove as EventListener);
      window.removeEventListener("mouseup", handleUp);
      window.removeEventListener("touchend", handleUp);
      if (!wasMoved) {
        setIsOpen((prev) => !prev);
      }
    };

    window.addEventListener("mousemove", handleMove as EventListener);
    window.addEventListener("touchmove", handleMove as EventListener, { passive: false });
    window.addEventListener("mouseup", handleUp);
    window.addEventListener("touchend", handleUp);
  };

  const handleSend = async () => {
    const content = inputValue.trim();
    if (!content || disabled) {
      return;
    }
    setIsSending(true);
    setError(null);
    try {
      await onSend(content);
      setInputValue("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to send message.";
      setError(message);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="floating-chat">
      <button
        type="button"
        ref={buttonRef}
        className={`floating-chat-button ${isOpen ? "open" : ""}`}
        style={{ left: position.x, top: position.y }}
        onMouseDown={handlePointerDown}
        onTouchStart={handlePointerDown}
        aria-label="Open chat"
      >
        <span>Chat</span>
      </button>

      <div
        className={`floating-chat-window ${isOpen ? "open" : ""}`}
        style={{ left: windowPos.x, top: windowPos.y, width: windowSize.width, height: windowSize.height }}
        aria-hidden={!isOpen}
      >
        <div className="floating-chat-header">
          <div>
            <strong>{title}</strong>
            <span className="floating-chat-status">{statusText}</span>
          </div>
          <button type="button" onClick={() => setIsOpen(false)} aria-label="Close chat">
            ✕
          </button>
        </div>
        <div className="floating-chat-body">
          {messages.length ? (
            messages.map((message) => {
              const isSelf = currentUserId && message.sender_user_id === currentUserId;
              return (
                <div key={message.id} className={`floating-chat-message ${isSelf ? "self" : ""}`}>
                  <div className="floating-chat-meta">
                    <strong>{message.sender_role === "admin" ? "Admin" : message.sender_name}</strong>
                    <span>{formatLocalDateTime(message.created_at)}</span>
                  </div>
                  <p>{message.content}</p>
                </div>
              );
            })
          ) : (
            <p className="muted">No messages yet.</p>
          )}
          <div ref={chatEndRef} />
        </div>
        {error ? <p className="error floating-chat-error">{error}</p> : null}
        <div className="floating-chat-input">
          <input
            type="text"
            placeholder={disabled ? "Chat is unavailable" : "Type a message..."}
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleSend();
              }
            }}
            disabled={disabled}
          />
          <button type="button" onClick={handleSend} disabled={disabled || isSending}>
            {isSending ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default FloatingChat;
