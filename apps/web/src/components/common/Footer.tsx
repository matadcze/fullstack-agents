/**
 * Footer component - shown on all pages.
 */

import { APP_NAME, APP_VERSION } from "@/config/constants";

export function Footer() {
  return (
    <footer className="border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            {APP_NAME} v{APP_VERSION}
          </div>
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            Powered by{" "}
            <a
              href="https://www.anthropic.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-900 dark:text-white hover:underline"
            >
              Anthropic Claude
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
