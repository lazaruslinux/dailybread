import {
  BookOpen,
  CircleUser,
  HeartPulse,
  House,
  Palette,
  ScanBarcode,
  ShoppingBasket,
  Trees,
  Users,
  Utensils,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { applyTheme, THEMES, type Theme } from '../lib/theme'
import { Coin } from './BreadIcon'
import { AuthShell, Brand, Button } from './ui'

// The feature tour (his copy, 2026-07-12). Shown to invite arrivals before
// they name their family (signup), and replayable anytime from You -> Repeat
// welcome tutorial (replay). The deck bends to its reader: adults get every
// card plus one about kid accounts; a kid replaying it gets only their three
// tabs, with bodies rewritten for what THEY can do (adultOnly + kidBody
// below). The verses card carries the one interactive choice: at signup it
// parks the answer in sessionStorage (there is no family to save onto yet;
// CreateFamily applies it right after founding), on replay it reads and
// saves the real setting directly.

export const VERSES_OPTIN_KEY = 'db-verses-optin'
// Signup has no account to save onto yet; the theme choice parks here and
// CreateFamily applies it right after founding (same pattern as the verses opt-in).
export const THEME_CHOICE_KEY = 'db-theme-choice'

const TOUR: {
  title: string
  Icon: LucideIcon
  iconClass?: string
  body: string
  note?: string
  // Cards about surfaces minors don't have; dropped from a kid's deck.
  adultOnly?: boolean
  // A kid-voiced body that replaces the adult one in a kid's deck.
  kidBody?: string
  versesChoice?: boolean
  themeChoice?: boolean
}[] = [
  {
    title: 'Choose your app theme',
    Icon: Palette,
    body: '',
    themeChoice: true,
  },
  {
    title: 'Home',
    Icon: House,
    body: "Your family's local hub. Routines, tasks, activities and appointments live on a shared family board. Filter family members, change from list to timeline or calendar view, and discover new Bible verses if you choose to enable them.",
    kidBody:
      "Your family's board, with your own routines and tasks on it. Check a card off when it's done; a parent gives it the thumbs-up and your breadcrumb lands.",
  },
  {
    title: 'Kitchen',
    Icon: ShoppingBasket,
    body: "Your family's meal plan in one place. Scan barcodes for nutrition and additive information, save recipes with nutrition facts baked-in, keep a per-store grocery list, plan family dinners, and more. Share recipes with other families if you enable it.",
    kidBody:
      "See what's for dinner and cast your vote for the night: homemade, go out, delivery, or self-serve. A parent makes the final call, but your vote is right there on the board. The family's recipes and grocery list live here too.",
  },
  {
    title: 'Health',
    Icon: HeartPulse,
    iconClass: 'text-red-400',
    body: "Your private, personal hub for tracking every metric of your Apple or Android health data. Steps, workouts with route maps, and weigh-ins sync straight from your phone to your family's own server, and only you can see them.",
    note: 'Android support is new and still being field-tested.',
    adultOnly: true,
  },
  {
    title: 'Nutrition',
    Icon: Utensils,
    body: 'A private, personal food diary that sets your calorie target from your health profile and auto-adjusts as you weigh in. Scan barcodes for immediate entry, save foods you eat often, log exercise to earn back calories, and lock in a finished day. Not even admins can see it.',
    adultOnly: true,
  },
  {
    title: 'Health check any food',
    Icon: ScanBarcode,
    body: 'The little "Scan a food" button at the top of every screen. Point it at a barcode and get an honest read of the label: seed oils, dyes, sweeteners, preservatives, and added sugar, summed up in one verdict. From there you can log it to your diary, save it, or drop it into a recipe.',
    adultOnly: true,
  },
  {
    title: 'Villages',
    Icon: Trees,
    body: 'Link your family with other families you trust to form a village. Inside it you can privately share recipes from your kitchen and share activities and appointments from your board, so families can RSVP and plan get-togethers. Each family keeps its own copy and RSVPs for its own people.',
    adultOnly: true,
  },
  {
    title: 'Kids on dailybread',
    Icon: Users,
    body: "Kid accounts get Home, Kitchen, and You. Their check-offs wait for a parent's approval, their dinner votes count but a parent locks the night in, and their journals stay visible to parents while they're a kid. Kids get no notifications, no health or nutrition areas, and nothing about them ever leaves the family.",
    adultOnly: true,
  },
  {
    title: 'You',
    Icon: CircleUser,
    body: 'Your profile page and main preferences hub. Upload an avatar, update your status and mood, set up your health profile, and configure all of your dailybread preferences mentioned in this tour.',
    kidBody:
      'Your own page. Set your mood and status for the family to see, write in your journal, and watch your breadcrumbs and level climb.',
  },
  {
    title: 'Earn Breadcrumbs',
    Icon: Coin as unknown as LucideIcon,
    iconClass: 'text-gold',
    body: 'Completing things in dailybread earns breadcrumbs, or XP for the gamers. The whole family can climb the ladder together. More information is available in You.',
    kidBody:
      'Checking off your cards and reading the daily verses earns breadcrumbs, or XP for the gamers. The whole family climbs the ladder together. More information is available in You.',
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
  const { user } = useAuth()
  // Signup arrivals are always parents founding a household, so the kid
  // deck only ever appears on a kid's replay from You.
  const isMinor = user?.is_minor ?? false
  const deck = TOUR.filter((c) => !(isMinor && c.adultOnly))
  const [step, setStep] = useState(0)
  const [wantVerses, setWantVerses] = useState(false)
  const [theme, setThemeChoice] = useState<Theme>(() =>
    document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light',
  )
  const last = step === deck.length - 1
  const replay = context === 'replay'

  // Apply the pick live so they see it before moving on. On replay it saves to
  // the account now; at signup it parks until CreateFamily has a family to save
  // onto. A miss is harmless — the You page has the same choice.
  function pickTheme(t: Theme) {
    setThemeChoice(t)
    applyTheme(t)
    if (replay) {
      api.updateMyProfile({ theme: t }).catch(() => {})
    } else {
      sessionStorage.setItem(THEME_CHOICE_KEY, t)
    }
  }

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
              const StepIcon = deck[step].Icon
              return <StepIcon className={`h-5 w-5 ${deck[step].iconClass ?? 'text-accent-bright'}`} strokeWidth={2.2} />
            })()}
            {deck[step].title}
          </h2>
          {deck[step].body && (
            <p className="text-sm leading-relaxed text-fg/60">
              {isMinor && deck[step].kidBody ? deck[step].kidBody : deck[step].body}
            </p>
          )}
          {deck[step].note && (
            <p className="mt-2 text-xs italic leading-relaxed text-fg/40">{deck[step].note}</p>
          )}
          {deck[step].themeChoice && (
            <div className="mt-1 grid grid-cols-2 gap-2">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => pickTheme(t.id)}
                  aria-pressed={theme === t.id}
                  className={`rounded-xl border p-3 text-sm font-semibold transition-colors ${
                    theme === t.id
                      ? 'border-accent-bright/60 bg-accent-bright/15 text-fg/90'
                      : 'border-fg/10 bg-fg/5 text-fg/70 hover:bg-fg/10'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}
          {deck[step].versesChoice && (
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
          {deck.map((_, i) => (
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
