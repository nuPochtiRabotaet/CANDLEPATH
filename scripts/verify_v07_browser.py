"""Existing QA entry point extended to run v0.7.1; original in verify_v07_browser_legacy.py."""
try:
    from .verify_v071_browser import main
except ImportError:
    from verify_v071_browser import main

if __name__ == '__main__':
    main()
