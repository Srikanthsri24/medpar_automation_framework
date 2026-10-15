"""Package existing report screens into six compressed, navigable HTML pages."""
from __future__ import annotations
import base64
import gzip
import json
import re
import tempfile
from pathlib import Path

STAGES=('final_action','split','stay','intermediate','final_medpar')


def read_html(path: Path) -> tuple[str,str]:
    """Decode legacy Windows reports without replacing or dropping characters."""
    raw=path.read_bytes()
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):return raw.decode('utf-16'),'utf-16'
    try:return raw.decode('utf-8-sig'),'utf-8'
    except UnicodeDecodeError:pass
    declared=re.search(br'charset\s*=\s*["\']?([A-Za-z0-9_-]+)',raw[:4096],re.I)
    candidates=([declared.group(1).decode('ascii')] if declared else [])+['cp1252','latin-1']
    for encoding in candidates:
        try:return raw.decode(encoding),encoding
        except (UnicodeDecodeError,LookupError):continue
    raise ValueError(f'Cannot decode report HTML: {path}')


def compact_reports(root: Path) -> Path:
    """Keep original screens and raw evidence, replacing HTML sprawl with lazy screens."""
    root=Path(root).resolve()
    if (root/'compact_report.json').exists():return root/'master/index.html'
    files=sorted(root.rglob('*.html'))
    if not files:return root/'master/index.html'
    def category(path):
        parts=path.relative_to(root).parts
        for stage in STAGES:
            if path.name.startswith(stage+'_'):return stage
        for part in reversed(parts[:-1]):
            if part in STAGES:return part
        return 'master'
    routes={p.relative_to(root).as_posix():category(p) for p in files}
    before=sum(p.stat().st_size for p in files)
    legacy_encodings=[]
    groups={name:[] for name in ('master',*STAGES)}
    for path in files:groups[category(path)].append(path)
    with tempfile.TemporaryDirectory(prefix='medpar-report-') as temp:
        for name,paths in groups.items():
            blocks=[];screen_blocks={};batch={};size=0
            def flush():
                nonlocal batch,size
                if not batch:return
                for key in batch:screen_blocks[key]=len(blocks)
                archive=Path(temp)/(name+str(len(blocks))+'.gz')
                with gzip.open(archive,'wt',encoding='utf-8',compresslevel=9) as out:json.dump(batch,out,separators=(',',':'))
                blocks.append(archive);batch={};size=0
            for path in paths:
                if size>=4_000_000:flush()
                text,encoding=read_html(path)
                key=path.relative_to(root).as_posix()
                batch[key]=text;size+=path.stat().st_size
                if encoding!='utf-8':legacy_encodings.append({'file':key,'encoding':encoding})
            if not paths:
                batch[name+'/index.html']='<html><body><h1>'+name.replace('_',' ').title()+'</h1><p>No stage inputs were executed in this run.</p><a href="../master/index.html">Master report</a></body></html>'
            flush()
            default=name+'/index.html'
            if default not in screen_blocks:default=next(iter(screen_blocks))
            metadata=gzip.compress(json.dumps({'routes':routes,'blocks':screen_blocks},separators=(',',':')).encode(),compresslevel=9)
            output=Path(temp)/(name+'.html')
            with output.open('w',encoding='utf-8') as out:
                out.write('<!doctype html><html><head><meta charset="utf-8"><title>MEDPAR '+name.replace('_',' ').title()+'</title><style>html,body{margin:0;height:100%;font:16px system-ui}iframe{width:100%;height:100%;border:0}#loading{padding:24px}</style></head><body><div id="loading">Opening report evidence…</div><iframe title="MEDPAR report" hidden></iframe><script id="archive" type="application/octet-stream">'+base64.b64encode(metadata).decode('ascii')+'</script>')
                for number,archive in enumerate(blocks):
                    out.write('<script id="block-'+str(number)+'" type="application/octet-stream">'+base64.b64encode(archive.read_bytes()).decode('ascii')+'</script>')
                out.write('<script>const defaultScreen='+json.dumps(default)+';'+SCRIPT+'</script></body></html>')
        # All replacements exist before removing the source pages.
        for path in files:path.unlink()
        for name in groups:
            (root/name).mkdir(exist_ok=True)
            (Path(temp)/(name+'.html')).replace(root/name/'index.html')
    after=sum(p.stat().st_size for p in root.rglob('*.html'))
    (root/'compact_report.json').write_text(json.dumps({'legacy_html_encodings':legacy_encodings,'html_files_before':len(files),'html_files_after':6,'html_bytes_before':before,'html_bytes_after':after,'count_basis':'Processed input rows, generated output rows and verified next-stage reads' if (root/'master/row_flow.json').exists() else 'Original-source lineage remains unchanged','navigation':'One master and one page per stage; screen routes open existing rule/file evidence inside the page'},indent=2), encoding="utf-8")
    return root/'master/index.html'


SCRIPT=r'''
(async()=>{
try {
 async function unpack(id){
  const bytes=Uint8Array.from(atob(document.getElementById(id).textContent),c=>c.charCodeAt(0));
  return JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
 }
 const data=await unpack('archive');
 let cachedBlock=-1,cachedScreens={},version=0;
 document.getElementById('archive').remove();
 const root=new URL('../',location.href),frame=document.querySelector('iframe');
 async function display(){
  const request=++version;
  const args=new URLSearchParams(location.hash.slice(1));
  const screen=args.get('screen')||defaultScreen;
  const block=data.blocks[screen];
  if(block===undefined)throw Error('Report screen unavailable: '+screen);
  if(cachedBlock!==block){cachedScreens=await unpack('block-'+block);cachedBlock=block;}
  if(request!==version)return;
  const doc=new DOMParser().parseFromString(cachedScreens[screen],'text/html');
  const base=doc.createElement('base');base.href=new URL(screen,root).href;doc.head.prepend(base);
  doc.querySelectorAll('a[href]').forEach(a=>{
   const target=new URL(a.getAttribute('href'),base.href);
   const relative=decodeURIComponent(target.pathname.slice(root.pathname.length));
   if(target.origin===root.origin&&target.pathname.startsWith(root.pathname)&&data.routes[relative]){
    const route=new URL(data.routes[relative]+'/index.html',root);
    route.hash='screen='+encodeURIComponent(relative)+'&anchor='+encodeURIComponent(target.hash.slice(1));
    a.href=route.href;a.target='_top';
   }
  });
  frame.onload=()=>{
   frame.hidden=false;document.getElementById('loading').hidden=true;
   // Paginated evidence inserts links after initial screen parsing.
   frame.contentDocument.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');if(!link)return;
    const target=new URL(link.getAttribute('href'),base.href);
    if(target.hash.startsWith('#screen='))return;
    const relative=decodeURIComponent(target.pathname.slice(root.pathname.length));
    if(target.origin===root.origin&&target.pathname.startsWith(root.pathname)&&data.routes[relative]){
     event.preventDefault();const route=new URL(data.routes[relative]+'/index.html',root);
     route.hash='screen='+encodeURIComponent(relative)+'&anchor='+encodeURIComponent(target.hash.slice(1));location.href=route.href;
    }
   });
   const anchor=args.get('anchor');
   if(anchor){const node=frame.contentDocument.getElementById(anchor);if(node){for(let parent=node.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;node.scrollIntoView();}}
  };
  frame.srcdoc='<!doctype html>'+doc.documentElement.outerHTML;
 }
 window.addEventListener('hashchange',()=>display().catch(error=>{document.getElementById('loading').hidden=false;document.getElementById('loading').textContent=error.message;}));await display();
} catch(error){document.getElementById('loading').textContent='Unable to open report: '+error.message;}
})();
'''
