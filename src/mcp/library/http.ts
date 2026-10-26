import { checkedUrl, LibraryError } from "./common.js";

export type FetchLike = (url: string, init: RequestInit) => Promise<Response>;

export interface HttpOptions {
  fetch: FetchLike;
  userAgent: string;
  timeoutMs: number;
  retries: number;
  backoffMs: number;
  sleep: (ms: number) => Promise<void>;
}

export interface Attempt {
  response: Response;
  url: URL;
  touch: () => void;
}

const MAX_REDIRECTS = 5;
const MAX_RETRY_AFTER_MS = 10_000;

class HttpStatus extends Error {
  constructor(
    readonly status: number,
    readonly retryAfterMs: number | undefined,
    message: string,
  ) {
    super(message);
  }
}

class IdleTimeout extends Error {}

function retryAfter(response: Response): number | undefined {
  const header = response.headers.get("retry-after");
  if (header === null) return undefined;
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds >= 0 ? Math.min(seconds * 1000, MAX_RETRY_AFTER_MS) : undefined;
}

function causeOf(error: unknown): string {
  if (error instanceof IdleTimeout) return "no data arrived within the timeout";
  if (!(error instanceof Error)) return String(error);
  const cause = (error as { cause?: unknown }).cause;
  if (cause instanceof Error) {
    const code = (cause as { code?: unknown }).code;
    return typeof code === "string" ? `${code}: ${cause.message}` : cause.message;
  }
  return error.message;
}

function retryable(error: unknown): boolean {
  if (error instanceof LibraryError) return false;
  if (error instanceof HttpStatus) return error.status === 429 || error.status >= 500;
  return true;
}

async function discard(response: Response): Promise<void> {
  await response.body?.cancel().catch(() => undefined);
}

export class Http {
  constructor(private readonly options: HttpOptions) {}

  async get<T>(raw: string, accept: string, consume: (attempt: Attempt) => Promise<T>): Promise<T> {
    const start = checkedUrl(raw);
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.options.retries; attempt += 1) {
      try {
        return await this.once(start, accept, consume);
      } catch (error) {
        lastError = error;
        if (!retryable(error) || attempt === this.options.retries) break;
        const wait = error instanceof HttpStatus && error.retryAfterMs !== undefined ? error.retryAfterMs : this.options.backoffMs * 2 ** attempt;
        await this.options.sleep(wait);
      }
    }
    throw this.explain(start, lastError);
  }

  private explain(url: URL, error: unknown): LibraryError {
    if (error instanceof LibraryError) return error;
    const tries = this.options.retries + 1;
    if (error instanceof HttpStatus) {
      if (error.status === 404) return new LibraryError("not_found", `Poly Haven has nothing at ${url.pathname} (HTTP 404)`);
      return new LibraryError("failed", `${error.message} for ${url.href}${retryable(error) ? ` after ${tries} attempts` : ""}`);
    }
    return new LibraryError("offline", `cannot reach ${url.hostname} after ${tries} attempts (${causeOf(error)})`);
  }

  private async once<T>(start: URL, accept: string, consume: (attempt: Attempt) => Promise<T>): Promise<T> {
    const controller = new AbortController();
    let timer: NodeJS.Timeout | undefined;
    let timedOut = false;
    const touch = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort(new IdleTimeout());
      }, this.options.timeoutMs);
    };
    touch();
    try {
      const { response, url } = await this.follow(start, accept, controller.signal);
      if (!response.ok) {
        await discard(response);
        throw new HttpStatus(response.status, retryAfter(response), `HTTP ${response.status}`);
      }
      return await consume({ response, url, touch });
    } catch (error) {
      if (timedOut && !(error instanceof LibraryError)) throw new IdleTimeout();
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  private async follow(start: URL, accept: string, signal: AbortSignal): Promise<{ response: Response; url: URL }> {
    let url = start;
    for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
      const response = await this.options.fetch(url.href, {
        method: "GET",
        headers: { "User-Agent": this.options.userAgent, Accept: accept },
        redirect: "manual",
        signal,
      });
      if (response.status < 300 || response.status >= 400) return { response, url };
      const location = response.headers.get("location");
      await discard(response);
      if (location === null) throw new LibraryError("failed", `${url.href} answered HTTP ${response.status} without a Location`);
      let next: URL;
      try {
        next = checkedUrl(location, url);
      } catch (error) {
        throw new LibraryError("refused", `refused a redirect from ${url.hostname} to ${location.slice(0, 200)}: ${error instanceof Error ? error.message : String(error)}`);
      }
      url = next;
    }
    throw new LibraryError("failed", `${start.href} redirected more than ${MAX_REDIRECTS} times`);
  }
}

export async function readCapped(attempt: Attempt, maxBytes: number, what: string): Promise<Buffer> {
  const declared = Number(attempt.response.headers.get("content-length") ?? "NaN");
  if (Number.isFinite(declared) && declared > maxBytes) {
    await discard(attempt.response);
    throw new LibraryError("refused", `${what} is ${declared} bytes, above the cap of ${maxBytes}`);
  }
  const body = attempt.response.body;
  if (body === null) return Buffer.alloc(0);
  const chunks: Buffer[] = [];
  let total = 0;
  const reader = body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    attempt.touch();
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel().catch(() => undefined);
      throw new LibraryError("refused", `${what} is larger than the cap of ${maxBytes} bytes`);
    }
    chunks.push(Buffer.from(value));
  }
  return Buffer.concat(chunks);
}
