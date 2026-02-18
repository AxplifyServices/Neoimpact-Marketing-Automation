import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  label?: string
}

const sizeClasses = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-4',
  lg: 'h-12 w-12 border-4',
  xl: 'h-16 w-16 border-4',
}

/**
 * Accessible loading spinner component
 * Includes proper ARIA attributes for screen readers
 */
export function LoadingSpinner({
  size = 'md',
  className,
  label = 'Loading...'
}: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className="inline-flex items-center justify-center"
    >
      <div
        className={cn(
          'animate-spin rounded-full border-solid border-current border-r-transparent',
          sizeClasses[size],
          className
        )}
      />
      <span className="sr-only">{label}</span>
    </div>
  )
}

/**
 * Full-page loading spinner with centered layout
 */
export function LoadingSpinnerPage({
  label = 'Loading...',
  message
}: {
  label?: string
  message?: string
}) {
  return (
    <div className='flex h-screen items-center justify-center'>
      <div className='text-center'>
        <LoadingSpinner size="lg" label={label} />
        {message && (
          <p className='mt-4 text-sm text-muted-foreground'>{message}</p>
        )}
      </div>
    </div>
  )
}
