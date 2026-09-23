/**
 * Persistance des personnages derrière une interface minimale : aujourd'hui le navigateur
 * (`LocalCharacterStore`, `localStorage`) et le fichier téléchargé ; demain une API du serveur
 * (`HttpCharacterStore` à écrire : mêmes méthodes, le compte en plus), sans toucher à l'écran.
 */
import { DESCRIPTOR_KIND, serialize, type CharacterDescriptor } from './descriptor';

export type StoredCharacter = { id: string; descriptor: CharacterDescriptor; savedAt: string };

export interface CharacterStore {
  list(): Promise<StoredCharacter[]>;
  get(id: string): Promise<StoredCharacter | null>;
  /** Crée (sans `id`) ou remplace le personnage ; renvoie la version enregistrée. */
  save(descriptor: CharacterDescriptor, id?: string): Promise<StoredCharacter>;
  remove(id: string): Promise<void>;
}

export const LOCAL_KEY = 'allodex:characters';

function newId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c?.randomUUID) return c.randomUUID();
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Personnages du navigateur : une liste JSON sous `allodex:characters`. */
export class LocalCharacterStore implements CharacterStore {
  private storage: Storage | null;
  private key: string;

  constructor(storage: Storage | null = typeof window !== 'undefined' ? window.localStorage : null, key = LOCAL_KEY) {
    this.storage = storage;
    this.key = key;
  }

  private read(): StoredCharacter[] {
    try {
      const raw = this.storage?.getItem(this.key);
      const list = raw ? JSON.parse(raw) as StoredCharacter[] : [];
      return Array.isArray(list) ? list.filter(c => c?.descriptor?.kind === DESCRIPTOR_KIND) : [];
    } catch {
      return [];
    }
  }

  private write(list: StoredCharacter[]): void {
    this.storage?.setItem(this.key, JSON.stringify(list));
  }

  async list(): Promise<StoredCharacter[]> {
    return this.read();
  }

  async get(id: string): Promise<StoredCharacter | null> {
    return this.read().find(c => c.id === id) ?? null;
  }

  async save(descriptor: CharacterDescriptor, id?: string): Promise<StoredCharacter> {
    const list = this.read();
    const now = new Date().toISOString();
    const entry: StoredCharacter = {
      id: id ?? newId(),
      descriptor: { ...descriptor, createdAt: descriptor.createdAt ?? now, updatedAt: now },
      savedAt: now,
    };
    const at = list.findIndex(c => c.id === entry.id);
    if (at >= 0) list[at] = entry; else list.push(entry);
    this.write(list);
    return entry;
  }

  async remove(id: string): Promise<void> {
    this.write(this.read().filter(c => c.id !== id));
  }
}

/** Télécharge le descripteur (`<nom>.allodex.json`). */
export function downloadDescriptor(d: CharacterDescriptor): void {
  const blob = new Blob([serialize(d)], { type: 'application/json' });
  downloadBlob(blob, `${d.name || d.race}.allodex.json`);
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
