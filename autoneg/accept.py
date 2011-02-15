__all__ = ['negotiate']

from itertools import chain
import re
_q_re = re.compile("^(?P<ct>[^;]+)[ \t]*(;[ \t]*q=(?P<q>[0-9.]+)){0,1}$")

def parseAccept(header):
    parsed = {}
    for p in [x.strip() for x in header.split(",")]:
        m = _q_re.match(p)
        if m is not None:
            d = m.groupdict()
            if not d.get("q"): d["q"] = "1.0"
            ct, q = d["ct"], float(d["q"])
            parsed.setdefault(q, []).append(ct)
    qs = parsed.keys()
    qs.sort(lambda x,y: cmp(y,x))
    return chain.from_iterable(parsed[q] for q in qs)

def matchAccept(cfg, req, strict=False):
    seen = set()
    for ct in req:
        req_type, req_subtype = ct.split("/", 1)
        for cfg_type, cfg_subtype, exts in cfg:
            matched = False
            if req_type == cfg_type and req_subtype == cfg_subtype:
                matched = True
            elif not strict and req_type == "*" and req_subtype == cfg_subtype:
                matched = True
            elif not strict and req_type == cfg_type and req_subtype == "*":
                matched = True
            elif not strict and req_type == "*" and req_subtype == "*":
                matched = True
            if matched:
                content_type = "%s/%s" % (cfg_type, cfg_subtype)
                if content_type not in seen:
                    seen.add(content_type)
                    yield content_type, exts

def negotiate(cfg, accept_header, strict=False):
    req = parseAccept(accept_header)
    candidates = matchAccept(cfg, req, strict=strict)
    return candidates
