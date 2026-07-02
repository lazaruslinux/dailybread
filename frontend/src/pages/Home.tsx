import { AnimatePresence, motion } from 'framer-motion'
import { Plus } from 'lucide-react'
import { Fragment, useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { FamilyStrip } from '../components/FamilyStrip'
import { ItemCard, NowDivider } from '../components/ItemCard'
import { ItemSheet } from '../components/ItemSheet'
import { FormError } from '../components/ui'

// Where does the "Now" line sit? After the last timed card that's already
// passed. Returns -1 when it shouldn't render (nothing timed yet to compare).
function nowIndex(items: api.FeedItem[], clock: Date): number {
  const nowHm = `${String(clock.getHours()).padStart(2, '0')}:${String(clock.getMinutes()).padStart(2, '0')}:00`
  let idx = -1
  items.forEach((item, i) => {
    if (item.time_of_day && item.time_of_day <= nowHm) idx = i
  })
  return idx
}

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="mb-2 mt-6 text-xs font-semibold uppercase tracking-widest text-white/40">
      {children}
    </p>
  )
}

function upcomingLabel(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

export function Home({ onOpenProfile }: { onOpenProfile: (id: number) => void }) {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'

  const [feed, setFeed] = useState<api.Feed | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState<{ open: boolean; item: api.FeedItem | null }>({ open: false, item: null })
  // Re-rendering once a minute keeps the Now line honest without any polling.
  const [clock, setClock] = useState(() => new Date())

  const refresh = useCallback(async () => {
    try {
      const [f, fam] = await Promise.all([api.getFeed(), api.getFamily()])
      setFeed(f)
      setFamily(fam)
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the board.')
    }
  }, [])

  useEffect(() => {
    refresh()
    const tick = setInterval(() => setClock(new Date()), 60_000)
    // Coming back to the app (phone unlock, tab focus) refetches the board.
    const onVisible = () => document.visibilityState === 'visible' && refresh()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(tick)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh])

  async function toggle(item: api.FeedItem) {
    try {
      if (item.completed) await api.uncompleteItem(item.id)
      else await api.completeItem(item.id)
      refresh()
    } catch (err) {
      // Most likely a 403 on someone else's card; surface it briefly.
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  function canCheck(item: api.FeedItem): boolean {
    if (!user) return false
    if (user.role === 'parent') return true
    return item.assignee === null || item.assignee.id === user.id
  }

  const divider = feed ? nowIndex(feed.today, clock) : -1

  return (
    <div>
      <FamilyStrip members={family} onOpen={onOpenProfile} />
      <FormError message={error} />

      {feed && feed.today.length === 0 && feed.anytime.length === 0 && (
        <p className="glass p-6 text-center text-sm text-white/50">
          Nothing on the board today. Enjoy it.
        </p>
      )}

      <div className="flex flex-col gap-3">
        <AnimatePresence>
          {feed?.today.map((item, i) => (
            <Fragment key={item.id}>
              <ItemCard
                item={item}
                index={i}
                canCheck={canCheck(item)}
                onToggle={() => toggle(item)}
                onEdit={isParent ? () => setSheet({ open: true, item }) : undefined}
              />
              {i === divider && <NowDivider />}
            </Fragment>
          ))}
        </AnimatePresence>
      </div>

      {feed && feed.anytime.length > 0 && (
        <>
          <SectionLabel>Anytime</SectionLabel>
          <div className="flex flex-col gap-3">
            <AnimatePresence>
              {feed.anytime.map((item, i) => (
                <ItemCard
                  key={item.id}
                  item={item}
                  index={i}
                  canCheck={canCheck(item)}
                  onToggle={() => toggle(item)}
                  onEdit={isParent ? () => setSheet({ open: true, item }) : undefined}
                />
              ))}
            </AnimatePresence>
          </div>
        </>
      )}

      {feed && feed.upcoming.length > 0 && (
        <>
          <SectionLabel>Coming up</SectionLabel>
          <div className="flex flex-col gap-3">
            {feed.upcoming.map((item, i) => (
              <div key={item.id}>
                <p className="mb-1 pl-1 text-[11px] font-medium text-white/35">
                  {item.date_for ? upcomingLabel(item.date_for) : ''}
                </p>
                <ItemCard
                  item={item}
                  index={i}
                  canCheck={false}
                  onEdit={isParent ? () => setSheet({ open: true, item }) : undefined}
                />
              </div>
            ))}
          </div>
        </>
      )}

      {isParent && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          whileTap={{ scale: 0.9 }}
          onClick={() => setSheet({ open: true, item: null })}
          aria-label="Add to the board"
          className="fixed bottom-6 right-1/2 z-30 flex h-14 w-14 translate-x-[calc(min(50vw,14rem)-2rem)] items-center justify-center rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 shadow-xl shadow-indigo-500/30"
        >
          <Plus className="h-6 w-6" strokeWidth={2.5} />
        </motion.button>
      )}

      <AnimatePresence>
        {sheet.open && (
          <ItemSheet
            item={sheet.item}
            family={family}
            onClose={() => setSheet({ open: false, item: null })}
            onSaved={() => {
              setSheet({ open: false, item: null })
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
