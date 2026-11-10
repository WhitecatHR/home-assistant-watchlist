"""Experimental read-only page adapters. No streaming API credentials or DRM access."""
import re
import unicodedata
import math
from urllib.parse import urlparse

SPECS = {
    "netflix": {"name":"Netflix", "login":"https://www.netflix.com/login", "watchlist":"https://www.netflix.com/browse/my-list", "history":"https://www.netflix.com/viewingactivity",
        "navigation":["netflix.com"], "resources":["netflix.com","netflix.net","nflxext.com","nflxso.net","nflximg.net","nflximg.com","nflxvideo.net","nflxsearch.net","onetrust.com","cookielaw.org"]},
    "prime": {"name":"Prime Video", "login":"https://www.primevideo.com/", "watchlist":"https://www.primevideo.com/mystuff/watchlist", "history":"https://www.primevideo.com/settings/watch-history",
        "navigation":["primevideo.com","amazon.de","amazon.com"], "resources":["primevideo.com","amazon.de","amazon.com","amazonvideo.com","media-amazon.com","ssl-images-amazon.com","images-amazon.com","aiv-cdn.net","amazon-adsystem.com"]},
    "disney": {"name":"Disney+", "login":"https://www.disneyplus.com/", "watchlist":"https://www.disneyplus.com/watchlist", "history":None,
        "navigation":["disneyplus.com","disney.com","disneyaccount.com","go.com"], "resources":["disneyplus.com","disney.com","disneyaccount.com","go.com","bamgrid.com","dssott.com","disney-plus.net","onetrust.com","cookielaw.org"]},
    "crunchyroll": {"name":"Crunchyroll", "login":"https://www.crunchyroll.com/", "watchlist":"https://www.crunchyroll.com/watchlist", "history":"https://www.crunchyroll.com/history",
        "navigation":["crunchyroll.com"], "resources":["crunchyroll.com","crunchyrollcdn.com","crunchyrollstatic.com","crunchyrollassets.com","cloudflare.com","hcaptcha.com","gstatic.com","google.com","onetrust.com","cookielaw.org"]},
}


def allowed_url(provider, url, navigation=False):
    try:
        parsed=urlparse(url)
        valid=parsed.scheme=="https" and not parsed.username and not parsed.password and parsed.port in (None,443)
    except ValueError:
        return False
    if not valid:
        return False
    host=(parsed.hostname or "").lower().rstrip(".")
    domains=SPECS[provider]["navigation" if navigation else "resources"]
    return any(host==d or host.endswith("."+d) for d in domains)


def episode_numbers(text):
    for pattern in [r"\bS(?:taffel\s*)?(\d+)[\s:.,/·\-–]*(?:E(?:pisode)?|F(?:olge)?)\s*(\d+)\b",
                    r"\b(?:Staffel|Season)\s*(\d+)[\s:.,/·\-–]*(?:Folge|Episode|Ep\.?|E)\s*(\d+)\b"]:
        m=re.search(pattern,text,re.I)
        if m:
            return int(m[1]),int(m[2])
    return None,None


def series_title(title):
    """Keep real title punctuation; remove labelled season/episode suffixes only."""
    title=re.sub(r"\s+"," ",unicodedata.normalize("NFKC",title or "")).strip()
    title=re.sub(r"\s*(?:\[(?:dt\.?|OV|OmU|Original[^\]]*)[^\]]*\]|\((?:OV|OmU|dt\.?/OV)\))\s*$","",title,flags=re.I)
    title=re.split(r"\s*[:|–—-]\s*(?=(?:Staffel|Season|Saison)\s*\d+\b)",title,maxsplit=1,flags=re.I)[0]
    title=re.sub(r"\s+(?:Staffel|Season|Saison)\s*\d+(?:\s*[/&–-]\s*\d+)?\s*$","",title,flags=re.I)
    return title.strip(" -–—:|") or title


def title_key(title):
    key=re.sub(r"[^\w]+"," ",series_title(title).casefold()).strip()
    return "house" if key in {"dr house","doctor house"} else key


def search_title(title):
    title=series_title(title)
    return "House" if title_key(title)=="house" else title


def image_allowed(url):
    try:
        p=urlparse(url or "")
        if p.scheme!="https" or p.username or p.password or p.port not in (None,443):return False
        host=p.hostname or ""
    except ValueError:return False
    domains=["tvmaze.com","nflximg.net","nflximg.com","nflxso.net","media-amazon.com","images-amazon.com","ssl-images-amazon.com","disneyplus.com","bamgrid.com","dssott.com","crunchyroll.com","crunchyrollcdn.com","metahub.space"]
    return any(host==d or host.endswith('.'+d) for d in domains)


def page_is_section(provider,section,url):
    if not allowed_url(provider,url,True):return False
    path=urlparse(url).path.lower()
    if provider=="netflix":return ("/browse/my-list" in path) if section=="watchlist" else ("viewingactivity" in path or "/settings/viewed" in path)
    if provider=="prime":return bool(re.search(r"/(?:mystuff/watchlist|watchlist)(?:/|$)",path)) if section=="watchlist" else "watch-history" in path
    return bool(re.search(r"/"+section+r"(?:/|$)",path))


def percentage(bookmark,duration):
    if isinstance(bookmark,bool) or isinstance(duration,bool) or not isinstance(bookmark,(int,float)) or not isinstance(duration,(int,float)):
        return None
    if not math.isfinite(bookmark) or not math.isfinite(duration) or bookmark<0 or duration<=0:return None
    return math.floor(min(100,100*bookmark/duration)*100)/100


def netflix_history_rows(data):
    """Read only the viewing-activity object, never a general catalog JSON graph."""
    items=data.get("viewedItems")
    if items is None:items=data.get("jsonGraph",{}).get("aui",{}).get("viewingActivity",{}).get("value",{}).get("viewedItems")
    if not isinstance(items,list):return []
    result=[]
    for item in items[:2000]:
        ident=item.get("movieID")
        if not isinstance(ident,int) or ident<=0:continue
        duration=item.get("duration");bookmark=item.get("bookmark")
        pct=percentage(bookmark,duration)
        title=item.get("seriesTitle") or item.get("title")
        if not isinstance(title,str) or not title.strip():continue
        match=re.search(r"(?:Staffel|Season)\s*(\d+)",str(item.get("seasonDescriptor","")),re.I)
        season=int(match[1]) if match else None
        result.append({"provider_id":f"/watch/{ident}","url":f"https://www.netflix.com/watch/{ident}","title":title,
            "series_title":series_title(title),"episode_title":str(item.get("episodeTitle") or "")[:300],
            "series_id":item.get("series"),"season":season,"episode":None,"completion":pct,
            "activity_at":item.get("date"),"media_type":"series" if item.get("series") else "movie","parser_version":2})
    return result


def enrich_netflix(rows,video):
    if not isinstance(video,dict):return
    for row in rows:
        ident=row.get("series_id") or int(row["provider_id"].rsplit('/',1)[-1])
        if video.get("id")!=ident:continue
        row["media_type"]="series" if video.get("type")=="show" else "movie" if video.get("type")=="movie" else row.get("media_type","unknown")
        if video.get("title"):row["series_title"]=series_title(video["title"])
        if video.get('type')=='movie':
            fresh=percentage((video.get('bookmark') or {}).get('offset'),video.get('runtime'))
            if fresh is not None:row['completion']=fresh
        images=video.get("artwork") or []
        if images and image_allowed(images[0].get("url")):row["image"]=images[0]["url"]
        for season in video.get("seasons") or []:
            for ep in season.get("episodes") or []:
                if str(ep.get("id"))!=row["provider_id"].rsplit('/',1)[-1]:continue
                row["episode_title"]=ep.get("title") or row.get("episode_title","")
                fresh=percentage((ep.get('bookmark') or {}).get('offset'),ep.get('runtime'))
                if fresh is not None:row['completion']=fresh
                if not video.get("hiddenEpisodeNumbers",False):
                    row["season"]=season.get("seq");row["episode"]=ep.get("seq")


def normalize_row(provider, row):
    url=row.get("url","")
    if not allowed_url(provider,url,navigation=True):
        return None
    title=re.sub(r"\s+"," ",str(row.get("title", ""))).strip()[:300]
    if not title:
        return None
    season,episode=episode_numbers(row.get("text", ""))
    pct=row.get("completion")
    if isinstance(pct,bool) or not isinstance(pct,(float,int)) or not 0<=pct<=100:
        pct=None
    media=str(row.get("media_type") or '').casefold()
    media={'tv show':'series','tvseries':'series','show':'series','film':'movie','tvseason':'series'}.get(media,media)
    if media not in {"movie","series"}:media="series" if re.search(r"\b(?:Staffel|Season|Saison)\s*\d+",title,re.I) or season is not None else "unknown"
    return {"provider_id":urlparse(url).path.rstrip("/"), "url":url.split("?")[0], "title":title,
            "series_title":series_title(title),"season":season,"episode":episode,"completion":pct,
            "image":row.get("image") if image_allowed(row.get("image")) else None,"media_type":media,
            "parser_version":2,"text":row.get("text","")[:1200]}


# Heuristics intentionally return observations for review. Selectors require live-account validation.
EXTRACT_JS = r"""({provider, section}) => {
  const patterns = {
    netflix: /\/(title|watch)\/\d+|[?&]jbv=\d+/,
    prime: /\/(detail|dp)\/[A-Z0-9]+/i,
    disney: /\/(series|movies|browse\/entity|video)[\/-]/i,
    crunchyroll: /\/(series|watch)\/[A-Z0-9]+/i
  };
  const selectors = {
    netflix: {watchlist:'.my-list-gallery, [data-uia="my-list-gallery"], [data-uia="my-list-page"], .galleryContent', history:'.retable, [data-uia="viewing-activity"], [data-uia="viewing-activity-table"]'},
    prime: {watchlist:'[data-testid="watchlist"], [data-automation-id="watchlist"], #watchlist, .tst-watchlist, [data-testid="watchlist-grid"]',history:'[data-testid="watch-history"], [data-automation-id="watch-history"], #watch-history'},
    disney: {watchlist:'[data-testid="watchlist"], [data-gv2elementkey="watchlist"], [aria-label="Watchlist"]'},
    crunchyroll: {watchlist:'.erc-watchlist, [data-t="watchlist"], [data-testid="watchlist"]',history:'.erc-watch-history, [data-t="watch-history"]'}
  };
  const excludedSelector='[data-list-context="similars"], [data-testid*="recommend"], [data-uia*="recommend"], [aria-label*="recommend" i], [aria-label*="empfehl" i], .recommendations, nav, footer, aside';
  const recommendationLabel=/^(?:empfehlungen|für dich empfohlen|das könnte dir (?:auch )?gefallen|ähnliche titel|more like this|recommend(?:ations|ed for you)|you might also like|suggestions for you|weiterschauen|continue watching)\b/i;
  const recommendationRegions=[...document.querySelectorAll('section,[role="region"],[role="list"],[role="grid"]')].filter(e=>recommendationLabel.test((e.getAttribute('aria-label') || e.querySelector('h1,h2,h3,[role="heading"]')?.textContent || '').trim()));
  const excluded=a=>!!a.closest(excludedSelector) || recommendationRegions.some(e=>e.contains(a));
  const titleLinks=element=>[...element.querySelectorAll('a[href]')].filter(a=>patterns[provider].test(a.href) && !excluded(a));
  let root=document.querySelector(selectors[provider]?.[section] || 'watchlists-no-such-element');
  let headingScope=false;
  const netflixHeadings=provider==='netflix' && section==='watchlist' ? [...document.querySelectorAll('h1,h2,h3,[role="heading"],[data-uia="my-list-title"],.sub-header .title')].filter(h=>/^(meine liste|my list)$/i.test(h.textContent.replace(/\s+/g,' ').trim()) && !excluded(h)) : [];
  // The browser also checks this route before extraction. Never use all page links as a list.
  if (!root && netflixHeadings.length && /^\/browse\/my-list\/?$/i.test(location.pathname)) {
    for (const heading of netflixHeadings) {
      let candidate=heading.parentElement;
      for (let depth=0;candidate && candidate!==document.body && candidate!==document.documentElement && depth<7;depth++,candidate=candidate.parentElement) {
        if (titleLinks(candidate).length) {root=candidate;break;}
      }
      // A labelled, empty semantic list is valid; an unlabelled page remains unrecognized.
      if (!root) root=heading.closest('main,[role="main"],section,[role="region"]');
      if (root) {headingScope=true;break;}
    }
  }
  if (!root && provider==='prime') {
    const main=document.querySelector('main, [role="main"]');
    const heading=[...(main?.querySelectorAll('h1,h2,h3')||[])].find(h=>section==='watchlist'?/watchlist|merkliste/i.test(h.textContent):/watch history|wiedergabeverlauf|wiedergabe-verlauf/i.test(h.textContent));
    if (heading) root=heading.closest('section,[role="tabpanel"]') || main;
  }
  const diagnostics={title_links:[...document.querySelectorAll('a[href]')].filter(a=>patterns[provider].test(a.href)).length,
    galleries:document.querySelectorAll('.galleryContent,.my-list-gallery').length,history_rows:document.querySelectorAll('.retableRow').length,
    my_list_headings:netflixHeadings.length,main_regions:document.querySelectorAll('main,[role="main"]').length,heading_scope:headingScope,
    containers:[...new Set([...document.querySelectorAll('[class]')].map(e=>typeof e.className==='string'?e.className:'').filter(s=>/watchlist|history|gallery/i.test(s)))].slice(0,15).map(s=>s.slice(0,100))};
  if (!root) return {recognized:false,rows:[],reason:'Listenbereich nicht erkannt',diagnostics};
  const result = [];
  const seen = new Set();
  for (const a of root.querySelectorAll('a[href]')) {
    if (!patterns[provider].test(a.href)) continue;
    if(excluded(a)) continue;
    let card = a.closest('article, li, tr, [role="listitem"], .title-card, .retableRow, [data-uia="title-card"], [data-uia="title-card-container"], [data-testid*="card"], [class*="erc-watch-history"], [class*="erc-watchlist-card"]');
    if (!card || !root.contains(card)) {
      card=a;
      // Modern Netflix cards may have generated classes. Keep the poster and controls
      // together, stopping before a parent contains posters belonging to other titles.
      if (provider==='netflix') for (let candidate=a.parentElement,depth=0;candidate && candidate!==root && root.contains(candidate) && depth<4;depth++,candidate=candidate.parentElement) {
        const images=candidate.querySelectorAll('img[alt]');
        if (images.length>1 || titleLinks(candidate).length>4) break;
        if (images.length===1) card=candidate;
      }
    }
    const img = card.querySelector('img[alt]');
    const heading = card.querySelector('h2,h3,h4,[data-testid*="title"]');
    const title = heading?.textContent?.trim() || card.querySelector('.fallback-text')?.textContent?.trim() || img?.alt?.trim() || a.getAttribute('aria-label') || a.textContent.trim();
    const url = new URL(a.href);
    if(provider==='netflix') {
      const more=card.querySelector('a[href*="jbv="]');
      const titleId=new URL(more?.href || a.href).searchParams.get('jbv') || (section==='watchlist' ? card.querySelector('a[href*="/title/"]')?.href.match(/\/title\/(\d+)/)?.[1] || url.pathname.match(/\/(?:title|watch)\/(\d+)/)?.[1] : null);
      if(titleId && /^\d+$/.test(titleId))url.pathname='/title/'+titleId;
    }
    url.search=''; url.hash='';
    if (!title || seen.has(url.href)) continue;
    seen.add(url.href);
    const p = card.querySelector('progress,[role="progressbar"][aria-valuenow]');
    let completion = null;
    if (p?.tagName === 'PROGRESS' && Number(p.max) > 0) completion=100*Number(p.value)/Number(p.max);
    else if (p?.hasAttribute('aria-valuenow')) {
      const max=Number(p.getAttribute('aria-valuemax') || '100');
      const min=Number(p.getAttribute('aria-valuemin') || '0');
      if (max>min) completion=100*(Number(p.getAttribute('aria-valuenow'))-min)/(max-min);
    }
    result.push({title:title.slice(0,300),url:url.href,text:(card.textContent || '').slice(0,1200),completion,image:img?.currentSrc || img?.src || null,media_type:card.getAttribute('data-content-type') || card.getAttribute('data-entity-type')});
  }
  return {recognized:true,rows:result.slice(0,2000),selector:(headingScope?'My List heading · ':'')+root.tagName+'.'+root.className,diagnostics};
}"""

PAGE_STATUS_JS = r"""() => {
  const text=(document.body?.innerText || document.body?.textContent || '').slice(0,12000);
  const blocked=!!document.querySelector('#challenge-form, #cf-challenge-running, #cf-error-details, iframe[src*="challenges.cloudflare.com"], iframe[src*="hcaptcha"]') || /verify you are human|checking your browser|sicherheitsüberprüfung|bestätigen.{0,20}mensch|just a moment|sorry.{0,3}you have been blocked/i.test(text);
  const profile=window.netflix?.reactContext?.models?.userInfo?.data?.name;
  return {blocked,profile:typeof profile==='string'?profile:null};
}"""
