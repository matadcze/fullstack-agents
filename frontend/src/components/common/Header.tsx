/**
 * Header component - shown on all pages.
 *
 * This is a common component that should be reused across pages.
 */

import Link from "next/link";
import { APP_NAME } from "@/config/constants";

export function Header() {
  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <h1 className="text-3xl text-display font-ultra-bold text-zinc-900 dark:text-white tracking-tight">
            {APP_NAME}
          </h1>
        </Link>

        <nav className="flex items-center gap-8">
          <Link
            href="/"
            className="text-sm font-light text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-white transition-colors tracking-wide"
          >
            Home
          </Link>
          <Link
            href="/docs"
            className="text-sm font-light text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-white transition-colors tracking-wide"
          >
            Docs
          </Link>
        </nav>
      </div>
    </header>
  );
}
