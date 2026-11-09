import re
import httpx


def plain(text):
    from html import unescape
    return unescape(re.sub(r"<[^>]*>","",text or ""))


class Catalog:
    def __init__(self):
        self.client=httpx.AsyncClient(base_url="https://api.tvmaze.com",timeout=20,follow_redirects=False)

    async def close(self):
        await self.client.aclose()

    async def search(self, query):
        r=await self.client.get("/search/shows",params={"q":query})
        r.raise_for_status()
        return [self.clean(x["show"]) for x in r.json()[:16]]

    def clean(self, show):
        copy=dict(show)
        copy["summary"]=plain(show.get("summary"))
        return copy

    async def show(self, show_id):
        r=await self.client.get(f"/shows/{show_id}")
        r.raise_for_status()
        e=await self.client.get(f"/shows/{show_id}/episodes",params={"specials":1})
        e.raise_for_status()
        return self.clean(r.json()),e.json()
