"""Experimental read-only page adapters. No streaming API credentials or DRM access."""
import re
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
    for pattern in [r"\bS(?:taffel\s*)?(\d+)\s*[:.,\-–]?\s*(?:E(?:pisode)?|F(?:olge)?)\s*(\d+)\b",
                    r"\b(?:Staffel|Season)\s*(\d+)\s*[,.:\-–]?\s*(?:Folge|Episode|Ep\.?|E)\s*(\d+)\b"]:
        m=re.search(pattern,text,re.I)
        if m:
            return int(m[1]),int(m[2])
    return None,None


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
    return {"provider_id":urlparse(url).path.rstrip("/"), "url":url.split("?")[0], "title":title,
            "season":season,"episode":episode,"completion":pct,"text":row.get("text","")[:1200]}


# Heuristics intentionally return observations for review. Selectors require live-account validation.
EXTRACT_JS = r"""({provider, section}) => {
  const patterns = {
    netflix: /\/(title|watch)\/\d+/,
    prime: /\/(detail|dp)\/[A-Z0-9]+/i,
    disney: /\/(series|movies|browse\/entity|video)[\/-]/i,
    crunchyroll: /\/(series|watch)\/[A-Z0-9]+/i
  };
  const result = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    if (!patterns[provider].test(a.href)) continue;
    const card = a.closest('article, li, tr, .title-card, .retableRow, [data-testid*="card"], [class*="erc-watch-history"], [class*="erc-watchlist-card"]') || a;
    const img = card.querySelector('img[alt]');
    const heading = card.querySelector('h2,h3,h4,[data-testid*="title"]');
    const title = img?.alt?.trim() || heading?.textContent?.trim() || a.getAttribute('aria-label') || a.textContent.trim();
    const url = new URL(a.href); url.search=''; url.hash='';
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
    result.push({title:title.slice(0,300),url:url.href,text:(card.textContent || '').slice(0,1200),completion});
  }
  return result.slice(0,2000);
}"""
