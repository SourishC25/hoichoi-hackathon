"""Stage G — standards output: IAB VMAP 1.0 with inline VAST 3.0 ads.

Media/tracking URLs are written with a {BASE} placeholder that the server replaces with its own
origin when the manifest is served, so the downloaded file contains absolute URLs any VMAP-capable
player (IMA, JW, Video.js-vast) can consume."""
from __future__ import annotations

from xml.sax.saxutils import escape


def ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def _url(u: str) -> str:
    return u if u.startswith("http") else "{BASE}/" + u.lstrip("/")


def build_vmap(video_id: str, breaks: list[dict]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<vmap:VMAP xmlns:vmap="http://www.iab.net/videosuite/vmap" version="1.0">']
    for i, b in enumerate(breaks, 1):
        bid = f"midroll-{i}"
        cr = b["creative"]
        track = f"{{BASE}}/api/track?video={video_id}&amp;break={bid}&amp;creative={cr['id']}&amp;ev="
        ext = (f"<Brand>{escape(b['brand_id'])}</Brand><BreakScore>{b['quality']:.3f}</BreakScore>"
               f"<Relevance>{b['relevance']:.3f}</Relevance><DominantActivity>{escape(b.get('dominant_activity', ''))}</DominantActivity>"
               f"<Reason>{escape(b.get('reason', ''))}</Reason>")
        out.append(f"""  <vmap:AdBreak timeOffset="{ts(b['t'])}" breakType="linear" breakId="{bid}">
    <vmap:AdSource id="{bid}-src" allowMultipleAds="false" followRedirects="true">
      <vmap:VASTAdData>
        <VAST version="3.0">
          <Ad id="{b['brand_id']}-{cr['id']}" sequence="1">
            <InLine>
              <AdSystem version="1.0">hoichoi-contextual-adbreak</AdSystem>
              <AdTitle>{escape(b['brand_name'])} — {escape(cr['id'])}</AdTitle>
              <Impression id="imp"><![CDATA[{track.replace('&amp;', '&')}impression]]></Impression>
              <Creatives>
                <Creative id="{escape(cr['id'])}" sequence="1">
                  <Linear>
                    <Duration>{ts(cr['duration_sec'])}</Duration>
                    <TrackingEvents>
                      <Tracking event="start"><![CDATA[{track.replace('&amp;', '&')}start]]></Tracking>
                      <Tracking event="complete"><![CDATA[{track.replace('&amp;', '&')}complete]]></Tracking>
                    </TrackingEvents>
                    <MediaFiles>
                      <MediaFile id="{escape(cr['id'])}-mp4" delivery="progressive" type="video/mp4" width="854" height="480"><![CDATA[{_url(cr['url'])}]]></MediaFile>
                    </MediaFiles>
                  </Linear>
                </Creative>
              </Creatives>
              <Extensions>
                <Extension type="contextual-targeting">{ext}</Extension>
              </Extensions>
            </InLine>
          </Ad>
        </VAST>
      </vmap:VASTAdData>
    </vmap:AdSource>
    <vmap:TrackingEvents>
      <vmap:Tracking event="breakStart"><![CDATA[{track.replace('&amp;', '&')}breakStart]]></vmap:Tracking>
      <vmap:Tracking event="breakEnd"><![CDATA[{track.replace('&amp;', '&')}breakEnd]]></vmap:Tracking>
    </vmap:TrackingEvents>
  </vmap:AdBreak>""")
    out.append("</vmap:VMAP>")
    return "\n".join(out) + "\n"
