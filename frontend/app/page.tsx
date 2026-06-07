"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  type DocumentRow,
  listDocuments,
  uploadDocument,
} from "@/lib/api";

function formatDate(iso: string): string {
  const d = new Date(iso.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function LibraryPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [docs, setDocs] = useState<DocumentRow[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listDocuments();
      setDocs(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load library");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const row = await uploadDocument(file);
      router.push(`/read/${row.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="text-4xl font-medium tracking-tight mb-12 italic">library</h1>

      {docs === null ? (
        <p className="opacity-50 italic">loading…</p>
      ) : docs.length === 0 ? (
        <p className="opacity-60 italic mb-8">
          No documents yet. Upload one to start reading.
        </p>
      ) : (
        <ul className="mb-12">
          {docs.map((d) => (
            <li key={d.id} className="border-b border-[var(--rule)]">
              <Link
                href={`/read/${d.id}`}
                className="flex justify-between items-baseline py-5 gap-4 hover:opacity-70 transition-opacity"
              >
                <span className="truncate">{d.filename}</span>
                <span className="text-xs uppercase tracking-widest opacity-50 shrink-0">
                  {formatDate(d.last_opened_at)} · {d.page_count}p
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <label className="inline-block cursor-pointer border-b border-[var(--ink)] pb-1 italic hover:opacity-70 transition-opacity">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={onFile}
          disabled={uploading}
        />
        {uploading ? "uploading…" : "+ upload PDF"}
      </label>

      {error && (
        <p className="mt-6 text-sm italic opacity-70">
          {error}
        </p>
      )}
    </main>
  );
}
