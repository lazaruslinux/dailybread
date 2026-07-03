import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

// Small shared building blocks so every form and button in the app looks the
// same without repeating Tailwind class strings everywhere.

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  // iOS date/time inputs have no native way to empty them once set; passing
  // onClear renders an x button whenever the field has a value.
  onClear?: () => void
}

export function Field({ label, id, onClear, ...rest }: FieldProps) {
  const inputId = id ?? `field-${label.toLowerCase().replace(/\s+/g, '-')}`
  const clearable = onClear && Boolean(rest.value)
  return (
    // min-w-0 lets the field shrink inside grid/flex rows; without it the
    // browser holds the input at its intrinsic width and it overflows.
    <label htmlFor={inputId} className="block min-w-0">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-white/50">
        {label}
      </span>
      <div className="relative">
        <input id={inputId} className={`field ${clearable ? 'pr-9' : ''}`} {...rest} />
        {clearable && (
          <button
            type="button"
            onClick={onClear}
            aria-label={`Clear ${label.toLowerCase()}`}
            className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full bg-white/10 p-1 text-white/60 hover:bg-white/20 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </label>
  )
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger'
  children: ReactNode
}

const VARIANT_CLASS: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary:
    'bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/25 hover:from-indigo-400 hover:to-violet-400',
  ghost: 'bg-white/10 text-white/85 hover:bg-white/15 border border-white/10',
  danger: 'bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 border border-rose-400/20',
}

export function Button({ variant = 'primary', children, className = '', ...rest }: ButtonProps) {
  return (
    <button
      className={`rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

// Inline error line for forms. Animated in so it draws the eye without a jolt.
export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <motion.p
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="text-sm font-medium text-rose-300"
      role="alert"
    >
      {message}
    </motion.p>
  )
}

// Centered glass panel used by the login and first-run screens.
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh items-center justify-center px-5 py-10">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 24 }}
        className="glass w-full max-w-sm p-8"
      >
        {children}
      </motion.div>
    </div>
  )
}

// Wordmark shown on the auth screens.
export function Brand({ subtitle }: { subtitle: string }) {
  return (
    <div className="mb-7 text-center">
      <h1 className="text-3xl font-bold tracking-tight">
        daily<span className="bg-gradient-to-r from-indigo-300 to-violet-300 bg-clip-text text-transparent">bread</span>
      </h1>
      <p className="mt-1.5 text-sm text-white/55">{subtitle}</p>
    </div>
  )
}
