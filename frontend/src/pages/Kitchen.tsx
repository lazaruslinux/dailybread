import { GroceryPanel } from '../components/Grocery'

// The Kitchen tab: groceries now, dinner planning and meals later.
export function Kitchen() {
  return (
    <div className="flex flex-col gap-4">
      <GroceryPanel />
      <section className="glass p-5 text-center">
        <p className="text-sm text-fg/50">Put dinner planning here.</p>
        <p className="mt-1 text-xs text-fg/35">Tonight's meal card and the week strip land in this spot.</p>
      </section>
    </div>
  )
}
