import { motion } from 'framer-motion'
import { HealthBadge } from './components/HealthBadge'
import { NotificationCard } from './components/NotificationCard'
import { SAMPLE_FEED } from './data/mock'

function todayLabel(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

function App() {
  return (
    <div className="mx-auto min-h-screen w-full max-w-md px-5 py-8">
      <header className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-sm text-white/50">{todayLabel()}</p>
          <h1 className="text-3xl font-bold tracking-tight">Good morning</h1>
        </div>
        <HealthBadge />
      </header>

      {/* Skeleton note — remove once real data lands. */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mb-4 text-xs text-white/40"
      >
        Showing sample data — backend wiring comes next.
      </motion.p>

      <main className="flex flex-col gap-3">
        {SAMPLE_FEED.map((card, i) => (
          <NotificationCard key={card.id} card={card} index={i} />
        ))}
      </main>

      <footer className="mt-10 text-center text-xs text-white/30">dailybread · v0.0.1</footer>
    </div>
  )
}

export default App
