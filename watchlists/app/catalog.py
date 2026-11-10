import re
import httpx
from .providers import search_title,image_allowed
from urllib.parse import quote


def plain(text):
    from html import unescape
    return unescape(re.sub(r"<[^>]*>","",text or ""))


class Catalog:
    def __init__(self):
        self.client=httpx.AsyncClient(base_url="https://api.tvmaze.com",timeout=20,follow_redirects=False)

    async def close(self):
        await self.client.aclose()

    async def search(self, query,kind='series'):
        query=search_title(query)
        if kind=='movie':
            r=await self.client.get('https://v3-cinemeta.strem.io/catalog/movie/top/search='+quote(query,safe='')+'.json')
            r.raise_for_status()
            return [self.movie(m) for m in r.json().get('metas',[])[:16] if re.fullmatch(r'tt\d{7,12}',m.get('id',''))]
        r=await self.client.get("/search/shows",params={"q":query})
        r.raise_for_status()
        return [self.clean(x["show"]) for x in r.json()[:16]]

    def clean(self, show):
        copy=dict(show)
        copy["summary"]=plain(show.get("summary"))
        return copy

    async def show(self, show_id):
        if show_id<=-1_000_000_000:
            imdb='tt'+str(-show_id-1_000_000_000).zfill(7)
            r=await self.client.get(f'https://v3-cinemeta.strem.io/meta/movie/{imdb}.json')
            r.raise_for_status()
            movie=r.json().get('meta') or {}
            if movie.get('id')!=imdb:raise ValueError('Film nicht gefunden')
            return self.movie(movie),[]
        if show_id<=0:raise ValueError('Ungültige Katalog-ID')
        r=await self.client.get(f"/shows/{show_id}")
        r.raise_for_status()
        e=await self.client.get(f"/shows/{show_id}/episodes",params={"specials":1})
        e.raise_for_status()
        return self.clean(r.json()),e.json()

    def movie(self,m):
        year=re.search(r'\b(\d{4})\b',str(m.get('releaseInfo') or m.get('year') or ''))
        poster=m.get('poster')
        return {'id':-1_000_000_000-int(m['id'][2:]),'name':m['name'],'summary':plain(m.get('description')),
            'image':{'medium':poster} if image_allowed(poster) else None,'url':f"https://www.imdb.com/title/{m['id']}/",
            'premiered':year[1]+'-01-01' if year else None,'status':'Ended','media_type':'movie','type':'Film','catalog':'cinemeta'}
