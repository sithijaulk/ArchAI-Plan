import React, { useState } from 'react'

// Very simple toast implementation for demonstration
// A real app would use Radix Toast or sonner

let toastCounter = 0;
type ToastProps = { id: number, title?: string, description?: string, variant?: 'default' | 'destructive' };
let addToastFn: (toast: Omit<ToastProps, 'id'>) => void = () => {};

export function Toaster() {
  const [toasts, setToasts] = useState<ToastProps[]>([]);

  React.useEffect(() => {
    addToastFn = (toast) => {
      const id = ++toastCounter;
      setToasts((t) => [...t, { ...toast, id }]);
      setTimeout(() => {
        setToasts((t) => t.filter((x) => x.id !== id));
      }, 3000);
    };
  }, []);

  return (
    <div className="fixed top-0 right-0 p-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div key={t.id} className={`rounded-md border p-4 shadow-lg ${t.variant === 'destructive' ? 'bg-destructive text-destructive-foreground' : 'bg-card text-foreground'}`}>
          {t.title && <h3 className="font-semibold text-sm">{t.title}</h3>}
          {t.description && <p className="text-sm opacity-90">{t.description}</p>}
        </div>
      ))}
    </div>
  )
}

export const useToast = () => {
  return {
    toast: (props: Omit<ToastProps, 'id'>) => {
      addToastFn(props);
    }
  }
}
