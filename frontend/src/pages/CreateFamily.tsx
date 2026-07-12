import { useState, type FormEvent } from 'react'
import { ApiError, setVerseSettings } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'

// A short feature tour for accounts that just arrived via an invite code
// (the sessionStorage flag is set at redeem time). Static on purpose: five
// ideas, then straight into naming the family. The verses step carries the
// one interactive choice; it's remembered here and applied right after the
// family is founded (the setting needs a family to save onto).
const VERSES_OPTIN_KEY = 'db-verses-optin'

const TOUR: { title: string; body: string; versesChoice?: boolean }[] = [
  {
    title: 'Your day, one board',
    body: "Routines, tasks, and appointments live on a shared family board that knows what time it is. Check things off as you go, and turn on notifications to get a nudge on your phone shortly before anything with a time.",
  },
  {
    title: 'The Kitchen',
    body: 'Save recipes with real nutrition computed per serving, keep a grocery list per store, and plan the week of dinners. One tap sends a recipe onto a shopping list.',
  },
  {
    title: 'Nutrition, if you want it',
    body: "A personal food diary with your own calorie budget, weigh-ins, and auto-adjusting targets. It's private to each member; nobody else can see it, not even an admin.",
  },
  {
    title: 'Yours, together',
    body: 'Every member gets their own sign-in, a daily mood, and a private journal. Later, villages can link your family with another one to share recipes, and nothing more, unless you choose it.',
  },
  {
    title: 'Breadcrumbs',
    body: "Little things earn breadcrumbs: showing up, reading, moving, logging your meals. Crumbs become your level, worn in a small circle beside your name, and the whole family climbs the same ladder from Slice to Breadmaster. The full recipe lives in You, under Breadcrumbs & Levels.",
  },
  {
    title: 'Daily bread, if you want it',
    body: "Three short verses, chosen for the day, can wait at the bottom of your board. Opting in includes the streak: read all three each day and it grows, earning breadcrumbs and bonuses along the way. Change your mind anytime in You.",
    versesChoice: true,
  },
]

function WelcomeTour({ firstName, onDone }: { firstName: string; onDone: () => void }) {
  const [step, setStep] = useState(0)
  const [wantVerses, setWantVerses] = useState(false)
  const last = step === TOUR.length - 1

  function toggleVerses() {
    const next = !wantVerses
    setWantVerses(next)
    if (next) sessionStorage.setItem(VERSES_OPTIN_KEY, '1')
    else sessionStorage.removeItem(VERSES_OPTIN_KEY)
  }

  return (
    <AuthShell>
      <Brand subtitle={step === 0 ? `Welcome aboard, ${firstName}. A quick look around:` : ''} />
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="mb-2 text-lg font-bold">{TOUR[step].title}</h2>
          <p className="text-sm leading-relaxed text-fg/60">{TOUR[step].body}</p>
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
          {last ? 'Set up my family' : 'Next'}
        </Button>
        {!last && (
          <button
            type="button"
            onClick={onDone}
            className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
          >
            Skip the tour
          </button>
        )}
      </div>
    </AuthShell>
  )
}

// Shown to a fresh new-household account: they are signed in but have no family
// yet. Naming their household founds it and makes them its parent + admin, and
// from there they add their own members. This is the far side of the "Invite
// to dailybread" action in the server admin's dashboard.
export function CreateFamily() {
  const { user, createFamily, logout } = useAuth()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [touring, setTouring] = useState(
    () => sessionStorage.getItem('db-invite-tour') === '1',
  )

  const firstName = user?.display_name.split(/\s+/)[0] ?? ''

  if (touring) {
    return (
      <WelcomeTour
        firstName={firstName}
        onDone={() => {
          sessionStorage.removeItem('db-invite-tour')
          setTouring(false)
        }}
      />
    )
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await createFamily(name)
      // The tour's verses opt-in couldn't save until a family existed; apply
      // it now. A miss is harmless — the You page has the same switch.
      if (sessionStorage.getItem(VERSES_OPTIN_KEY) === '1') {
        sessionStorage.removeItem(VERSES_OPTIN_KEY)
        setVerseSettings({ enabled: true }).catch(() => {})
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <AuthShell>
      <Brand subtitle={`Welcome, ${firstName}. Let's set up your household.`} />
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Field
            label="Family name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="The Breakfast Club"
            maxLength={80}
            autoFocus
            required
          />
          <p className="mt-1.5 text-xs leading-relaxed text-fg/40">
            Lots of families share a last name. A fun, custom name keeps yours recognizable
            when villages link families together. You can change it later.
          </p>
        </div>
        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="mt-1">
          {busy ? 'Creating' : 'Create our family'}
        </Button>
        <p className="text-center text-xs leading-relaxed text-fg/40">
          You'll be the head of this household. Add the rest of your family from the admin
          dashboard once you're in.
        </p>
        <button
          type="button"
          onClick={logout}
          className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
        >
          Sign out
        </button>
      </form>
    </AuthShell>
  )
}
