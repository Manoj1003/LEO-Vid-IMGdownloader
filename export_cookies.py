"""Export a browser's saved login into cookies.txt, so the downloader can use it
even when the browser itself is locked/open. Run this once per site you need.

Usage:
    python export_cookies.py firefox instagram.com
    python export_cookies.py chrome  x.com
"""
import http.cookiejar
import sys

import browser_cookie3 as bc3

BROWSERS = {
    "firefox": bc3.firefox, "chrome": bc3.chrome, "edge": bc3.edge,
    "brave": bc3.brave, "opera": bc3.opera, "safari": getattr(bc3, "safari", None),
}


def main():
    if len(sys.argv) < 3:
        print("Usage: python export_cookies.py <firefox|chrome|edge|brave|opera|safari> <site domain, e.g. instagram.com>")
        return
    browser, domain = sys.argv[1].lower(), sys.argv[2].lower()
    loader = BROWSERS.get(browser)
    if not loader:
        print(f"Unknown browser '{browser}'. Choose one of: {', '.join(BROWSERS)}")
        return

    print(f"Reading {browser}'s saved login for {domain} ...")
    print("If this fails, fully close that browser first (all its windows) and run this again.")
    try:
        cookies = loader(domain_name=domain)
    except Exception as e:
        print(f"\nCouldn't read {browser}: {e}")
        print("Close that browser completely and try again, or try a different browser.")
        return

    jar = http.cookiejar.MozillaCookieJar("cookies.txt")
    count = 0
    for c in cookies:
        jar.set_cookie(c)
        count += 1

    if not count:
        print(f"\nNo saved login for {domain} was found in {browser}. Make sure you're logged into "
              f"{domain} in {browser}, then run this again.")
        return

    jar.save(ignore_discard=True, ignore_expires=True)
    print(f"\nSaved {count} cookies to cookies.txt in this folder. You can now paste {domain} links into the app.")


if __name__ == "__main__":
    main()
