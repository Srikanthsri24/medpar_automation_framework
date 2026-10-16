"""Verify all compact HTML screens/routes without opening client data in a browser."""
import argparse
import base64
import gzip
import json
import posixpath
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit


def verify(root):
    root=Path(root)
    wrappers=list(root.rglob('*.html'))
    if len(wrappers)!=6:raise ValueError(f'Expected six HTML wrappers, found {len(wrappers)}')
    routes=None;seen=set();missing=set();checked=0
    for wrapper in wrappers:
        text=wrapper.read_text(encoding='utf-8')
        if routes is None:
            encoded=re.search(r'type="application/octet-stream">([^<]+)</script>',text).group(1)
            routes=json.loads(gzip.decompress(base64.b64decode(encoded)))['routes']
        for encoded in re.findall(r'id="block-\d+" type="application/octet-stream">([^<]+)</script>',text):
            for screen,body in json.loads(gzip.decompress(base64.b64decode(encoded))).items():
                seen.add(screen)
                for href in re.findall(r'href=["\']([^"\']+)',body):
                    link=urlsplit(href)
                    if link.scheme or link.netloc or not link.path.endswith('.html'):continue
                    target=posixpath.normpath(posixpath.join(posixpath.dirname(screen),unquote(link.path)))
                    checked+=1
                    if target not in routes and not (root/target).is_file():missing.add((screen,href,target))
    result={'html_wrappers':len(wrappers),'evidence_screens':len(seen),'html_links_checked':checked,
            'unresolved_html_links':len(missing),'all_routes_have_screens':seen==set(routes),
            'unresolved_examples':sorted(missing)[:10],
            'scope':'Static compact screen and HTML target verification; not a browser execution or business acceptance test.'}
    if missing or seen!=set(routes):raise ValueError(json.dumps(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_root',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify(args.report_root)
    text=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
