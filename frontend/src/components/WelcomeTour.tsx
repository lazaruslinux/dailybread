import {
  BookOpen,
  CircleUser,
  HeartPulse,
  House,
  ShoppingBasket,
  Trees,
  Utensils,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { BreadIcon } from './BreadIcon'
import { AuthShell, Brand, Button } from './ui'

// The eight-card feature tour (his copy, 2026-07-12). Shown to invite
// arrivals before they name their family (signup), and replayable anytime
// from You -> Repeat welcome tutorial (replay). The verses card carries the
// one interactive choice: at signup it parks the answer in sessionStorage
// (there is no family to save onto yet; CreateFamily applies it right after
// founding), on replay it reads and saves the real setting directly.

export const VERSES_OPTIN_KEY = 'db-verses-optin'

const TOUR: { title: string; Icon: LucideIcon; iconClass?: string; body: string; note?: string; versesChoice?: boolean }[] = [
  {
    title: 'Home',
    Icon: House,
    body: "Your family's local hub. Routines, tasks, activities and appointments live on a shared family board. Filter family members, change from list to timeline or calendar view, and discover new Bible verses if you choose to enable them.",
  },
  {
    title: 'Kitchen',
    Icon: ShoppingBasket,
    body: "Your family's meal plan in one place. Scan barcodes for nutrition and additive information, save recipes with nutrition facts baked-in, keep a per-store grocery list, plan family dinners, and more. Share recipes with other families if you enable it.",
  },
  {
    title: 'Health',
    Icon: HeartPulse,
    iconClass: 'text-red-400',
    body: "Your private, personal hub for tracking every metric of your Apple or Android health data. Steps, workouts with route maps, and weigh-ins sync straight from your phone to your family's own server, and only you can see them.",
    note: 'Android support is new and still being field-tested.',
  },
  {
    title: 'Nutrition',
    Icon: Utensils,
    body: 'A private, personal food diary that sets your calorie target from your health profile and auto-adjusts as you weigh in. Scan barcodes for immediate entry, save foods you eat often, log exercise to earn back calories, and lock in a finished day. Not even admins can see it.',
  },
  {
    title: 'Villages',
    Icon: Trees,
    body: 'Link your family with another to join a village; a group of families that can privately share events, recipes and more. (This feature is in active development)',
  },
  {
    title: 'You',
    Icon: CircleUser,
    body: 'Your profile page and main preferences hub. Upload an avatar, update your status and mood, set up your health profile, and configure all of your dailybread preferences mentioned in this tour.',
  },
  {
    title: 'Earn Breadcrumbs',
    Icon: BreadIcon as unknown as LucideIcon,
    iconClass: 'text-gold',
    body: 'Completing things in dailybread earns breadcrumbs, or XP for the gamers. The whole family can climb the ladder together. More information is available in You.',
  },
  {
    title: 'Your Daily Bread',
    Icon: BookOpen,
    iconClass: 'text-gold',
    body: 'Three comforting verses from scripture, waiting quietly at the bottom of your schedule to read each day. Every family gets a different 3 each day, and reading streaks earn breadcrumbs.',
    versesChoice: true,
  },
]

export function WelcomeTour({
  firstName,
  context,
  onDone,
}: {
  firstName: string
  context: 'signup' | 'replay'
  onDone: () => void
}) {
  const [step, setStep] = useState(0)
  const [wantVerses, setWantVerses] = useState(false)
  const last = step === TOUR.length - 1
  const replay = context === 'replay'

  // On replay the toggle is the live setting, not a parked wish.
  useEffect(() => {
    if (!replay) return
    api.getVerses().then((v) => setWantVerses(v.enabled)).catch(() => {})
  }, [replay])

  function toggleVerses() {
    const next = !wantVerses
    setWantVerses(next)
    if (replay) {
      api.setVerseSettings({ enabled: next }).catch(() => setWantVerses(!next))
    } else if (next) {
      sessionStorage.setItem(VERSES_OPTIN_KEY, '1')
    } else {
      sessionStorage.removeItem(VERSES_OPTIN_KEY)
    }
  }

  return (
    <AuthShell>
      <Brand
        subtitle={step === 0 ? `Welcome to dailybread, ${firstName}! Here is a simple tour:` : ''}
      />
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="mb-2 flex items-center gap-2 text-lg font-bold">
            {(() => {
              const StepIcon = TOUR[step].Icon
              return <StepIcon className={`h-5 w-5 ${TOUR[step].iconClass ?? 'text-accent-bright'}`} strokeWidth={2.2} />
            })()}
            {TOUR[step].title}
          </h2>
          <p className="text-sm leading-relaxed text-fg/60">{TOUR[step].body}</p>
          {TOUR[step].note && (
            <p className="mt-2 text-xs italic leading-relaxed text-fg/40">{TOUR[step].note}</p>
          )}
          {TOUR[step].versesChoice && (
            <button
              type="button"
              role="switch"
              aria-checked={wantVerses}
              onClick={toggleVerses}
              className="mt-3 flex w-full items-center justify-between gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
            >
              <span className="text-sm font-semibold text-fg/85">Opt-in to daily Bible verses</span>
              <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${wantVerses ? 'bg-accent' : 'bg-fg/15'}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${wantVerses ? 'left-[1.125rem]' : 'left-0.5'}`} />
              </span>
            </button>
          )}
        </div>
        <div className="flex items-center justify-center gap-1.5">
          {TOUR.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === step ? 'w-5 bg-accent-bright' : 'w-1.5 bg-fg/20'
              }`}
            />
          ))}
        </div>
        <Button type="button" onClick={() => (last ? onDone() : setStep(step + 1))}>
          {last ? (replay ? 'Done' : 'Set up my family') : 'Next'}
        </Button>
        {!last && (
          <button
            type="button"
            onClick={onDone}
            className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
          >
            {replay ? 'Close' : 'Skip the tour'}
          </button>
        )}
      </div>
    </AuthShell>
  )
}
