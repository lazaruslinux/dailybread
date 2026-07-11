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
