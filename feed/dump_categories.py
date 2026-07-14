"""
Regenerates data/categories.json by extracting the catalogTree from the Vinted home page.

Usage:
  .venv/bin/python dump_categories.py
"""

import asyncio

from dotenv import load_dotenv

from vinted_meta import VintedMeta, CATEGORIES_FILE

load_dotenv()


async def main():
  meta = VintedMeta()
  print('Extracting catalogTree from Vinted...')
  ok = await meta.refresh_categories()
  await meta.close()
  if ok:
    n = len(meta.categories)
    print(f'OK: {n} top-level categories saved to {CATEGORIES_FILE}')
  else:
    print('FAILED: categories not updated (see error above)')
    raise SystemExit(1)


if __name__ == '__main__':
  asyncio.run(main())
