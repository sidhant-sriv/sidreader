export type DocumentRow = {
  id: string;
  filename: string;
  path: string;
  page_count: number;
  current_card_index: number;
  created_at: string;
  last_opened_at: string;
};

export type Chunk = {
  page_number: number;
  text: string;
};

export type Pagination = {
  total: number;
  offset: number;
  limit: number;
  returned: number;
  has_more: boolean;
};

export type CardsResponse = {
  document: DocumentRow;
  pagination: Pagination;
  chunks: Chunk[];
};

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export async function listDocuments(): Promise<DocumentRow[]> {
  return asJson(await fetch("/documents", { cache: "no-store" }));
}

export async function getDocument(id: string): Promise<DocumentRow> {
  return asJson(await fetch(`/documents/${id}`, { cache: "no-store" }));
}

export async function getCards(
  id: string,
  opts: { startPage?: number; endPage?: number; limit?: number } = {}
): Promise<CardsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 5000));
  if (opts.startPage != null) params.set("start_page", String(opts.startPage));
  if (opts.endPage != null) params.set("end_page", String(opts.endPage));
  return asJson(
    await fetch(`/documents/${id}/cards?${params.toString()}`, {
      cache: "no-store",
    })
  );
}

export async function savePosition(id: string, cardIndex: number): Promise<void> {
  await fetch(`/documents/${id}/position`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ card_index: cardIndex }),
  });
}

export async function uploadDocument(file: File): Promise<DocumentRow> {
  const fd = new FormData();
  fd.append("file", file);
  return asJson(await fetch("/documents", { method: "POST", body: fd }));
}

export function fileUrl(id: string, page?: number): string {
  return page ? `/documents/${id}/file#page=${page}` : `/documents/${id}/file`;
}
