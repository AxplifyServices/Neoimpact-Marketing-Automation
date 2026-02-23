import { useState, useEffect } from 'react'

export type ToastVariant = 'default' | 'destructive' | 'success'

export type Toast = {
  id: string
  title: string
  description?: string
  variant?: ToastVariant
}

type ToasterToast = Toast & {
  onOpenChange?: (open: boolean) => void
}

const listeners: Array<(toasts: ToasterToast[]) => void> = []

let memoryState: ToasterToast[] = []

function genId() {
  return Math.random().toString(36).substring(2, 9)
}

function dispatch(toasts: ToasterToast[]) {
  memoryState = toasts
  listeners.forEach((listener) => {
    listener(toasts)
  })
}

export function toast({ title, description, variant = 'default' }: Omit<Toast, 'id'>) {
  const id = genId()
  const newToast: ToasterToast = {
    id,
    title,
    description,
    variant,
  }

  dispatch([...memoryState, newToast])

  // Auto dismiss after 5 seconds
  setTimeout(() => {
    dismiss(id)
  }, 5000)

  return {
    id,
    dismiss: () => dismiss(id),
  }
}

function dismiss(toastId: string) {
  dispatch(memoryState.filter((t) => t.id !== toastId))
}

export function useToast() {
  const [toasts, setToasts] = useState<ToasterToast[]>([])

  useEffect(() => {
    listeners.push(setToasts)
    return () => {
      const index = listeners.indexOf(setToasts)
      if (index > -1) {
        listeners.splice(index, 1)
      }
    }
  }, [])

  return {
    toasts,
    toast,
    dismiss,
  }
}
