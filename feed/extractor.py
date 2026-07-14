from dotenv import load_dotenv
from random import randint, uniform
from time import time
from os import getenv
from curl_cffi.requests import AsyncSession
from asyncio import Event, sleep

load_dotenv()

# Pause between one catalog request and the next. The real bottleneck is the
# proxy latency (~2s/request), so by default NO pause: maximum responsiveness.
# It can be raised via env if Vinted starts rate-limiting. 0 = no pause.
FETCH_INTERVAL = float(getenv('FEED_FETCH_INTERVAL', '0'))


class _Extractor:
  """A single scraping session with its own cookies.
  Each extractor has a limit of between 10/15 requests
  (Used by ExtractorFactory)."""

  def __init__(self):
    self.proxy = getenv('PROXY')
    if not self.proxy:
      raise ValueError('PROXY env not found')

    self.cookies_url = getenv('C_URL')
    if not self.cookies_url:
      raise ValueError('C_URL env not found')

    # Counter of requests made
    self.used = 0

    # Each extractor has a different limit
    self.max_uses = randint(10, 15)

    # For checks only, no meaning in the code
    self.created_at = time()

    # Used only for checks, has no meaning in itself in the code
    # There could be collisions between ids but it doesn't matter much
    self.id = randint(1,1000) + randint(1,100)

    # HTTP session with Chrome's TLS fingerprint, through the proxy.
    self.session = AsyncSession(impersonate='chrome', proxy=self.proxy)

  def age(self):
    #For checks only, no meaning in the code
    return time() - self.created_at

  async def get_cookies(self):
    """Initialize the session by grabbing the cookies. Does NOT download the page
    body (~2 MB of Vinted homepage) that we don't use: the cookies are in the
    HEADERS → stream + close without reading the body. Huge saving on proxy
    traffic. Returns the status code."""

    print(f'get-cookies: Creating extractor n{self.id}')
    async with self.session.stream('GET', self.cookies_url, timeout=20) as c_res:
      return c_res.status_code

  async def fetch_data(self, url: str):
    """Make a request to the target page and increment the counter."""

    self.used += 1
    res = await self.session.get(url, timeout=2)
    print(f'Request from: {self.id} request number: {self.used} of {self.max_uses}, lifetime: {self.age()}')
    return res


class ExtractorFactory:
  """Manages two loops with two concurrent methods.
    One in charge of creating new extractors to add to the pool
    One in charge of handling the data extraction in rotation"""

  def __init__(self, broadcast, client_connected):

    # Event signaling the presence of at least one connected client.
    # Used to suspend the fetch loop when there's no one listening.
    self.client_connected = client_connected

    self.extractors: list[_Extractor] = []

    # Signals that extractors need to be created
    self.pool_has_space = Event()

    #Signals that there are enough extractors to fetch
    self.pool_ready = Event()

    # At the start the pool is empty
    self.pool_has_space.set()

    # Function to send the messages to all connected ws clients
    self.broadcast = broadcast

  def _upgrade_events(self):
    # Update the events based on the pool state

    if len(self.extractors) <= 8:
      self.pool_has_space.set()
    else:
      self.pool_has_space.clear()

    if len(self.extractors) >= 3:
      self.pool_ready.set()
    else:
      self.pool_ready.clear()

  async def _remove_ext(self, ext):
    # Close the ext connection and remove it from the pool, updating the events

    await ext.session.close()

    if ext in self.extractors:
      self.extractors.remove(ext)

    self._upgrade_events()


  async def get_cookies_loop(self):
    while True:
      await self.client_connected.wait()
      await self.pool_has_space.wait()

      ext = _Extractor()

      try:
        res_cookies = await ext.get_cookies()
        if res_cookies == 200:

          print(f'get_cookies for n{ext.id} CREATED SUCCESSFULLY')

          self.extractors.append(ext)
          self._upgrade_events()
        else:
          await ext.session.close()

      except Exception as e:
        await ext.session.close()

        print(f'Error: get_cookies error: {e}')

      # Rate limit: wait before creating the next one,
      # both on success and on error

      await sleep(uniform(1, 2))


  async def fetch_data_loop(self, p_url):
    while True:
      await self.client_connected.wait()
      await self.pool_ready.wait()

      # Fetch data
      for ext in self.extractors[:]:
        if ext.used >= ext.max_uses:
          print(f'Limit {ext.max_uses} reached. Removing extractor')

          await self._remove_ext(ext)
          continue

        print(f'Extractors: {len(self.extractors)}')

        try:
          res = await ext.fetch_data(p_url)
          if res.status_code != 200:
            # Non-OK response → extractor probably banned/invalid

            print(f'Fetch fail from {ext.id}, nr {ext.used} of {ext.max_uses}, life time: {ext.age()}')
            print(res.status_code)

            await self._remove_ext(ext)
          else:
            # Success → send the data to all WebSocket clients

            await self.broadcast(res.text)
            self._upgrade_events()

            # Optional pause between requests (0 = none). See FETCH_INTERVAL.
            if FETCH_INTERVAL:
              await sleep(FETCH_INTERVAL)
        except Exception as e:
          # Network/connection error → extractor unusable

          print(f'Error fetch from {ext.id}, nr {ext.used} of {ext.max_uses}, life time: {ext.age()}: {e}')

          await self._remove_ext(ext)
