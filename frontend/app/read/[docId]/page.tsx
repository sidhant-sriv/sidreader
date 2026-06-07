"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useParams, useRouter } from "next/navigation";
import {
  type Chunk,
  type DocumentRow,
  fileUrl,
  getCards,
  getDocument,
  savePosition,
} from "@/lib/api";

type Mode = "cards" | "pdf";

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

export default function ReaderPage() {
  const router = useRouter();
  const params = useParams<{ docId: string }>();
  const docId = params.docId;

  const [doc, setDoc] = useState<DocumentRow | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState<Mode>("cards");
  const [startPage, setStartPage] = useState(1);
  const [endPage, setEndPage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [peekOpen, setPeekOpen] = useState(false);
  const indexRef = useRef(index);
  indexRef.current = index;

  // Initial load: fetch document metadata, then cards.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const d = await getDocument(docId);
        if (cancelled) return;
        setDoc(d);
        setEndPage(d.page_count);
        const res = await getCards(docId, {
          startPage: 1,
          endPage: d.page_count,
        });
        if (cancelled) return;
        setChunks(res.chunks);
        setIndex(clamp(d.current_card_index, 0, Math.max(0, res.chunks.length - 1)));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docId]);

  const total = chunks.length;
  const card = chunks[index];
  const progressPct = useMemo(
    () => (total === 0 ? 0 : ((index + 1) / total) * 100),
    [index, total]
  );

  const persist = useCallback(
    (next: number) => {
      void savePosition(docId, next).catch(() => {});
    },
    [docId]
  );

  const jumpTo = useCallback(
    (target: number) => {
      setIndex((i) => {
        const next = clamp(target, 0, Math.max(0, total - 1));
        if (next !== i) persist(next);
        return next;
      });
    },
    [persist, total]
  );

  const go = useCallback(
    (delta: number) => {
      setIndex((i) => {
        const next = clamp(i + delta, 0, Math.max(0, total - 1));
        if (next !== i) persist(next);
        return next;
      });
    },
    [persist, total]
  );

  // Inline "jump to N" input state
  const [jumpDraft, setJumpDraft] = useState<string | null>(null);
  function commitJump() {
    if (jumpDraft === null) return;
    const n = parseInt(jumpDraft, 10);
    if (!Number.isNaN(n)) jumpTo(n - 1);
    setJumpDraft(null);
  }

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tgt = e.target as HTMLElement | null;
      if (tgt && /^(INPUT|TEXTAREA|SELECT)$/.test(tgt.tagName)) return;
      if (e.key === "Escape") {
        router.push("/");
        return;
      }
      if (mode !== "cards") return;
      if (
        e.key === " " ||
        e.key === "ArrowRight" ||
        e.key === "ArrowDown" ||
        e.key === "PageDown"
      ) {
        e.preventDefault();
        go(1);
      } else if (
        e.key === "ArrowLeft" ||
        e.key === "ArrowUp" ||
        e.key === "PageUp"
      ) {
        e.preventDefault();
        go(-1);
      } else if (e.key === "Home") {
        e.preventDefault();
        jumpTo(0);
      } else if (e.key === "End") {
        e.preventDefault();
        jumpTo(total - 1);
      } else if (e.key === "g" || e.key === "G") {
        e.preventDefault();
        setJumpDraft(String(indexRef.current + 1));
      } else if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        setPeekOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, jumpTo, mode, router, total]);

  async function applyRange() {
    if (!doc) return;
    setLoading(true);
    setError(null);
    try {
      const sp = clamp(startPage, 1, doc.page_count);
      const ep = clamp(endPage ?? doc.page_count, sp, doc.page_count);
      const res = await getCards(docId, { startPage: sp, endPage: ep });
      setChunks(res.chunks);
      setIndex(0);
      persist(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply range");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen">
      {/* Progress bar */}
      <div
        className="fixed top-0 left-0 h-[2px] bg-[var(--ink)] transition-[width] duration-150 z-20"
        style={{ width: `${progressPct}%` }}
      />

      {/* Top bar */}
      <header className="fixed top-0 left-0 right-0 z-10 border-b border-[var(--rule)] bg-[var(--paper)]">
        <div className="flex items-center gap-4 px-5 py-3 text-sm">
          <button
            onClick={() => router.push("/")}
            className="text-base hover:opacity-60 transition-opacity"
            title="back to library (Esc)"
          >
            ←
          </button>

          <div className="flex border border-[var(--rule)] rounded-sm overflow-hidden">
            <button
              onClick={() => setMode("cards")}
              className={`px-3 py-1 ${
                mode === "cards" ? "bg-[var(--ink)] text-[var(--paper)]" : ""
              }`}
            >
              cards
            </button>
            <button
              onClick={() => setMode("pdf")}
              className={`px-3 py-1 ${
                mode === "pdf" ? "bg-[var(--ink)] text-[var(--paper)]" : ""
              }`}
            >
              pdf
            </button>
          </div>

          <div className="flex items-center gap-2 italic">
            <span className="opacity-60">pages</span>
            <input
              type="number"
              min={1}
              max={doc?.page_count ?? undefined}
              value={startPage}
              onChange={(e) => setStartPage(Number(e.target.value) || 1)}
              className="w-14 bg-transparent border border-[var(--rule)] focus:border-[var(--ink)] outline-none px-2 py-1 rounded-sm not-italic"
            />
            <span className="opacity-60">–</span>
            <input
              type="number"
              min={1}
              max={doc?.page_count ?? undefined}
              value={endPage ?? ""}
              onChange={(e) =>
                setEndPage(e.target.value === "" ? null : Number(e.target.value))
              }
              className="w-14 bg-transparent border border-[var(--rule)] focus:border-[var(--ink)] outline-none px-2 py-1 rounded-sm not-italic"
            />
            <button
              onClick={applyRange}
              className="border border-[var(--rule)] hover:border-[var(--ink)] px-3 py-1 rounded-sm"
            >
              apply
            </button>
          </div>

          <span className="ml-auto truncate opacity-60 italic">
            {doc?.filename}
          </span>

          {mode === "cards" && (
            <button
              onClick={() => setPeekOpen((v) => !v)}
              className={`border border-[var(--rule)] hover:border-[var(--ink)] px-3 py-1 rounded-sm ${
                peekOpen ? "bg-[var(--ink)] text-[var(--paper)] border-[var(--ink)]" : ""
              }`}
              title="toggle PDF side view (P)"
            >
              {peekOpen ? "hide page" : "peek page"}
            </button>
          )}
        </div>
      </header>

      {/* Card pane */}
      {mode === "cards" && (
        <section
          className={`min-h-screen flex items-center justify-center px-6 py-32 transition-[margin] duration-200 ${
            peekOpen ? "mr-[42vw]" : "mr-0"
          }`}
        >
          {loading ? (
            <p className="opacity-50 italic">loading…</p>
          ) : error ? (
            <p className="opacity-70 italic">{error}</p>
          ) : total === 0 ? (
            <p className="opacity-60 italic">No cards in this range.</p>
          ) : (
            <article
              className="max-w-[680px] text-[1.2rem] leading-[1.75]"
              key={index}
            >
              {card?.text}
            </article>
          )}
        </section>
      )}

      {/* Side peek: PDF page mirroring the current chunk */}
      {mode === "cards" && (
        <aside
          className={`fixed top-[3.25rem] right-0 bottom-0 w-[42vw] border-l border-[var(--rule)] bg-[var(--paper)] transition-transform duration-200 z-10 ${
            peekOpen ? "translate-x-0" : "translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--rule)] text-xs uppercase tracking-[0.15em]">
            <span className="opacity-60 italic">
              page {card?.page_number ?? "—"}
            </span>
            <button
              onClick={() => setPeekOpen(false)}
              className="opacity-60 hover:opacity-100"
              title="collapse (P)"
            >
              close ✕
            </button>
          </div>
          {card?.page_number != null && peekOpen && (
            <iframe
              key={card.page_number}
              title="PDF page peek"
              src={fileUrl(docId, card.page_number)}
              className="w-full h-[calc(100%-2.25rem)] bg-[var(--paper)]"
            />
          )}
        </aside>
      )}

      {/* PDF pane */}
      {mode === "pdf" && (
        <section className="fixed inset-0 top-[3.25rem]">
          <iframe
            title="PDF viewer"
            src={fileUrl(docId, startPage)}
            className="w-full h-full bg-[var(--paper)]"
          />
        </section>
      )}

      {/* Edge nav buttons */}
      {mode === "cards" && total > 0 && (
        <>
          <button
            onClick={() => go(-1)}
            disabled={index === 0}
            aria-label="previous card"
            className="fixed left-0 top-1/2 -translate-y-1/2 px-6 py-12 text-2xl opacity-30 hover:opacity-100 disabled:opacity-10 disabled:cursor-not-allowed transition-opacity"
          >
            ←
          </button>
          <button
            onClick={() => go(1)}
            disabled={index >= total - 1}
            aria-label="next card"
            className="fixed right-0 top-1/2 -translate-y-1/2 px-6 py-12 text-2xl opacity-30 hover:opacity-100 disabled:opacity-10 disabled:cursor-not-allowed transition-opacity"
          >
            →
          </button>
        </>
      )}

      {/* Bottom nav bar */}
      {mode === "cards" && total > 0 && (
        <div className="fixed bottom-0 left-0 right-0 flex items-center justify-center gap-6 py-5 text-xs uppercase tracking-[0.18em]">
          <button
            onClick={() => jumpTo(0)}
            disabled={index === 0}
            className="opacity-50 hover:opacity-100 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity"
            title="first card (Home)"
          >
            ⇤ first
          </button>
          <button
            onClick={() => go(-1)}
            disabled={index === 0}
            className="opacity-50 hover:opacity-100 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity"
            title="previous (←)"
          >
            ← prev
          </button>

          <span className="opacity-60 flex items-baseline gap-1">
            {jumpDraft !== null ? (
              <input
                autoFocus
                type="text"
                inputMode="numeric"
                value={jumpDraft}
                onChange={(e) =>
                  setJumpDraft(e.target.value.replace(/[^0-9]/g, ""))
                }
                onBlur={commitJump}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    commitJump();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    setJumpDraft(null);
                  }
                }}
                className="w-12 bg-transparent border-b border-[var(--ink)] outline-none text-center not-italic tracking-normal"
              />
            ) : (
              <button
                onClick={() => setJumpDraft(String(index + 1))}
                className="underline decoration-dotted underline-offset-4 hover:opacity-100"
                title="jump to card (G)"
              >
                {index + 1}
              </button>
            )}
            <span>/ {total}</span>
            {card?.page_number != null && (
              <span className="ml-2 opacity-70">· p{card.page_number}</span>
            )}
          </span>

          <button
            onClick={() => go(1)}
            disabled={index >= total - 1}
            className="opacity-50 hover:opacity-100 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity"
            title="next (→ or space)"
          >
            next →
          </button>
          <button
            onClick={() => jumpTo(total - 1)}
            disabled={index >= total - 1}
            className="opacity-50 hover:opacity-100 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity"
            title="last card (End)"
          >
            last ⇥
          </button>
        </div>
      )}
    </div>
  );
}
