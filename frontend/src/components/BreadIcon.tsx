import { useId } from 'react'

// A tiny loaf of bread, drawn to sit beside lucide icons (24-unit grid,
// stroke-current, round caps): a domed loaf on a board with two score marks.
// The breadcrumb economy's own mark — a wheat stalk said "field", this says
// "kitchen".
export function BreadIcon({
  className = '',
  strokeWidth = 2,
}: {
  className?: string
  strokeWidth?: number
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {/* the loaf: flat base, domed top */}
      <path d="M4 17v-4a8 5.5 0 0 1 16 0v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z" />
      {/* score marks across the crust */}
      <path d="M9 8.6v2.4" />
      <path d="M13.5 8.2v2.4" />
    </svg>
  )
}

// The brand loaf for the Home masthead: the same filled dome that sits inside
// the login badge, lifted out to stand alone beside the wordmark. The score
// marks are cut through to the background (like they cut to the navy tile on
// the badge), so one currentColor fill carries it and it adapts to the theme
// exactly like the old line mark did.
export function LoafMark({ className = '' }: { className?: string }) {
  const id = useId()
  const loaf =
    'M256 168c92 0 156 52 156 116 0 32-24 52-60 52H160c-36 0-60-20-60-52 0-64 64-116 156-116z'
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden>
      <mask id={id}>
        <path d={loaf} fill="#fff" />
        <g stroke="#000" strokeWidth={16} strokeLinecap="round">
          <line x1="196" y1="208" x2="174" y2="254" />
          <line x1="268" y1="196" x2="246" y2="242" />
          <line x1="338" y1="210" x2="316" y2="256" />
        </g>
      </mask>
      <path d={loaf} fill="currentColor" mask={`url(#${id})`} />
    </svg>
  )
}

// The bread token: the shiny coin designed in Canva, shown wherever
// breadcrumbs are counted (the +N float, profile and Breadcrumbs tallies, the
// Inbox crumb row, the You crumbs entry, the welcome tour). It is full-colour
// and self-lit, so unlike BreadIcon it ignores currentColor and any tint
// class. The light and dark artwork live in public/; the root data-theme
// attribute swaps them in CSS (see .db-coin in index.css). Sized by the
// className the caller passes (h-3 w-3, etc.), same as the icons it replaces.
export function Coin({ className = '' }: { className?: string }) {
  return <span className={`db-coin ${className}`} role="img" aria-hidden="true" />
}
