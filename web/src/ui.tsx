import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Icon } from "./components";
import { spring } from "./motion";

/* Toasts: one quiet confirmation at a time, bottom right, 2.4 s. */
const ToastCtx = createContext<(msg: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([]);
  const push = useCallback((msg: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-2), { id, msg }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 2400);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} className="toast" layout initial={{ opacity: 0, y: 16, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 30, transition: { duration: 0.2 } }} transition={spring}><Icon name="check" />{t.msg}</motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

/** Copy with visible feedback; says so when the clipboard is unavailable (plain http). */
export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const toast = useToast();
  const [done, setDone] = useState(false);
  const copy = () => {
    const p = navigator.clipboard?.writeText(text);
    if (!p) { toast("Copying isn't available here. Select the text instead."); return; }
    p.then(() => { setDone(true); toast(`${label} copied`); setTimeout(() => setDone(false), 1400); },
      () => toast("Couldn't copy. Select the text instead."));
  };
  return (
    <button type="button" className={`icon-btn${done ? " done" : ""}`} onClick={copy} aria-label={`Copy ${label.toLowerCase()}`} data-tip={`Copy ${label.toLowerCase()}`}>
      <Icon name={done ? "check" : "copy"} size={14} />
    </button>
  );
}

/** Native <dialog>: the browser traps focus and closes on Escape; focus returns to the opener. */
function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current; if (!d) return;
    if (open && !d.open) d.showModal(); else if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => {
    const d = ref.current; if (!d) return;
    const c = () => onClose(); d.addEventListener("close", c); return () => d.removeEventListener("close", c);
  }, [onClose]);
  return ref;
}

export function Modal({ open, onClose, title, children, actions }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; actions: React.ReactNode }) {
  const ref = useDialog(open, onClose);
  return (
    <dialog ref={ref} className="modal" aria-labelledby="modal-title" onClick={(e) => e.target === ref.current && onClose()}>
      <div className="dialog-body"><h2 id="modal-title">{title}</h2>{children}</div>
      <div className="dialog-foot">{actions}</div>
    </dialog>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  const ref = useDialog(open, onClose);
  return (
    <dialog ref={ref} className="drawer" aria-labelledby="drawer-title" onClick={(e) => e.target === ref.current && onClose()}>
      <div className="drawer-head"><h2 id="drawer-title">{title}</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close" data-tip="Close (Esc)"><Icon name="x" /></button></div>
      <div className="drawer-body">{children}</div>
    </dialog>
  );
}
