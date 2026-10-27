export interface WeightedField {
  tokens: string[];
  weight: number;
}

export interface Bm25Options {
  k1: number;
  b: number;
}

export interface Ranked {
  key: string;
  score: number;
}

export const DEFAULT_BM25: Bm25Options = { k1: 1.2, b: 0.5 };

interface Document {
  key: string;
  frequencies: Map<string, number>;
  length: number;
}

export class Bm25Index {
  private readonly documents: Document[] = [];
  private readonly documentFrequency = new Map<string, number>();
  private averageLength = 0;

  constructor(private readonly options: Bm25Options = DEFAULT_BM25) {}

  add(key: string, fields: WeightedField[]): void {
    const frequencies = new Map<string, number>();
    let length = 0;
    for (const field of fields) {
      for (const token of field.tokens) {
        frequencies.set(token, (frequencies.get(token) ?? 0) + field.weight);
        length += field.weight;
      }
    }
    for (const token of frequencies.keys()) this.documentFrequency.set(token, (this.documentFrequency.get(token) ?? 0) + 1);
    this.documents.push({ key, frequencies, length });
    this.averageLength = this.documents.reduce((sum, document) => sum + document.length, 0) / this.documents.length;
  }

  get size(): number {
    return this.documents.length;
  }

  idf(token: string): number {
    const count = this.documentFrequency.get(token) ?? 0;
    return Math.log(1 + (this.documents.length - count + 0.5) / (count + 0.5));
  }

  score(query: Map<string, number>, keep: (key: string) => boolean = () => true): Ranked[] {
    const { k1, b } = this.options;
    const ranked: Ranked[] = [];
    for (const document of this.documents) {
      if (!keep(document.key)) continue;
      let score = 0;
      for (const [token, weight] of query) {
        const frequency = document.frequencies.get(token);
        if (frequency === undefined) continue;
        const norm = frequency + k1 * (1 - b + (b * document.length) / this.averageLength);
        score += weight * this.idf(token) * ((frequency * (k1 + 1)) / norm);
      }
      if (score > 0) ranked.push({ key: document.key, score });
    }
    return ranked.sort((left, right) => right.score - left.score || left.key.localeCompare(right.key));
  }
}

export function bagOf(tokens: string[], weight = 1): Map<string, number> {
  const bag = new Map<string, number>();
  for (const token of tokens) bag.set(token, Math.max(bag.get(token) ?? 0, weight));
  return bag;
}
