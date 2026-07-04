import { LogOut, Users } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { Profile } from './Profile'

// The Me tab: your own profile (bio + mood) plus account-level actions that
// used to crowd the header. Admin entry lives here now.
export function Me({ onOpenAdmin }: { onOpenAdmin: () => void }) {
  const { user, logout } = useAuth()
  if (!user) return null

  return (
    <div className="flex flex-col gap-4">
      <Profile userId={user.id} />

      <div className="flex flex-col gap-2">
        {user.is_admin && (
          <button
            onClick={onOpenAdmin}
            className="glass flex items-center gap-3 p-4 text-left font-semibold text-white/80 transition-colors hover:text-white"
          >
            <Users className="h-4 w-4 text-indigo-300" /> Family members
          </button>
        )}
        <button
          onClick={logout}
          className="glass flex items-center gap-3 p-4 text-left font-semibold text-white/80 transition-colors hover:text-white"
        >
          <LogOut className="h-4 w-4 text-rose-300" /> Sign out
        </button>
      </div>

      {/* Thomas Nelson's gratis quotation policy requires this notice in any
          work that quotes the NKJV (the daily verse card). */}
      <p className="px-3 pt-1 text-center text-[10px] leading-relaxed text-white/30">
        Scripture taken from the New King James Version&reg;. Copyright &copy; 1982 by Thomas
        Nelson. Used by permission. All rights reserved.
      </p>
    </div>
  )
}
