"use client";
import {createContext, useCallback, useContext, useRef, useState, type Dispatch, type ReactNode, type SetStateAction} from 'react';

// Only retain browsing choices in this signed-in app instance. Nothing is
// written to disk; the provider is remounted when the account changes.
const PageMemory = createContext<Map<string, unknown> | null>(null);
export function PageMemoryProvider({children}: {children: ReactNode}) {
  const [memory] = useState(() => new Map<string, unknown>());
  return <PageMemory.Provider value={memory}>{children}</PageMemory.Provider>;
}
export function usePageState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const memory = useContext(PageMemory);
  const [value, update] = useState<T>(() => memory?.has(key) ? memory.get(key) as T : initial);
  const current = useRef(value);
  const setValue = useCallback<Dispatch<SetStateAction<T>>>(next => {
    const resolved = typeof next === 'function' ? (next as (previous: T) => T)(current.current) : next;
    current.current = resolved;
    memory?.set(key, resolved);
    update(resolved);
  }, [key, memory]);
  return [value, setValue];
}
