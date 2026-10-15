"""Compact row evidence controls and explicitly scoped reconciliation summaries."""
import html
import json


def row_browser(number, rows, cards):
    """Keep only ten row evidence cards in the live DOM; filter before pagination."""
    payload=[dict(row=r['row'],decision=r['decision'],status=r['validation_status'],comparison=r['comparison_status'],card=c) for r,c in zip(rows,cards)]
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    return f'''<section class="row-browser" id="rows-{number}"><p>Row evidence — ten rows per page. Search and filters cover all processed rows in this file.</p>
<label>Physical row number <input class="row-search" type="number" min="1" placeholder="All rows"></label>
<label>Decision <select class="row-decision"><option value="">All decisions</option><option>KEEP</option><option>DROP</option><option>STOPPED</option></select></label>
<label>Validation <select class="row-status"><option value="">All results</option><option>PASS</option><option>FAIL</option><option>BLOCKED</option></select></label>
<label>Output comparison <select class="row-comparison"><option value="">All comparisons</option><option>PASS</option><option>FAIL</option><option>BLOCKED</option><option>NOT PROVIDED</option></select></label>
<p class="row-range" aria-live="polite"></p><button class="row-prev" type="button">Previous 10</button> <button class="row-next" type="button">View next 10</button><div class="row-cards"></div><script type="application/json" class="row-data">{encoded}</script></section>'''


BROWSER_SCRIPT='''<script>
document.querySelectorAll('.row-browser').forEach(box=>{
 let ready=false;function activate(){if(ready)return;ready=true;
 const data=JSON.parse(box.querySelector('.row-data').textContent);let offset=0;
 const controls=['search','decision','status','comparison'].map(n=>box.querySelector('.row-'+n));
 function draw(){const [row,decision,status,comparison]=controls.map(c=>c.value);
 const found=data.filter(r=>(!row||String(r.row)===row)&&(!decision||r.decision===decision)&&(!status||r.status===status)&&(!comparison||r.comparison===comparison));
 offset=Math.min(offset,Math.max(0,Math.floor((found.length-1)/10)*10));
 box.querySelector('.row-cards').innerHTML=found.slice(offset,offset+10).map(r=>r.card).join('');
 box.querySelector('.row-range').textContent=found.length?'Showing '+(offset+1)+'–'+Math.min(offset+10,found.length)+' of '+found.length+' matching processed rows':'No matching processed rows';
 box.querySelector('.row-prev').disabled=offset===0;box.querySelector('.row-next').disabled=offset+10>=found.length;}
 controls.forEach(c=>c.addEventListener('input',()=>{offset=0;draw()}));
 box.querySelector('.row-prev').onclick=()=>{offset=Math.max(0,offset-10);draw()};box.querySelector('.row-next').onclick=()=>{offset+=10;draw()};draw();}
 const parent=box.closest('details');if(!parent||parent.open)activate();else parent.addEventListener('toggle',()=>{if(parent.open)activate()});
});</script>'''


def bars(title,counts):
    colors=['#237a4b','#bd3535','#a77412','#566176']
    total=sum(counts.values())
    segments=''.join(f'<span style="display:block;width:{100*n/max(total,1):.4f}%;background:{colors[i%4]};height:22px" title="{html.escape(k)}: {n}"></span>' for i,(k,n) in enumerate(counts.items()) if n)
    legend=' · '.join(html.escape(k)+': '+f'{n:,}' for k,n in counts.items())
    return f'<section><h3>{html.escape(title)}</h3><div role="img" aria-label="{legend}" style="display:flex;border-radius:6px;overflow:hidden;background:#eee">{segments}</div><p>{legend}</p></section>'


def render_overview(data):
    decisions=data['decision_counts'];scoped=data['scoped_output_rows']
    rows=''.join(f'<tr><td>{role.title()}</td><td>{decisions.get(role.upper(),0):,}</td><td>{scoped[role]:,}</td><td>{data["comparison_rows"][role] if data["comparison_rows"][role] is not None else "Not supplied"}</td></tr>' for role in ('keep','drop'))
    return (bars('Calculated decisions — processed source rows',decisions)+bars('Comparison results — processed source rows',data['comparison_outcomes'])+
        '<section id="output-comparison"><h3>Calculated decision versus supplied outputs</h3><p>Validate original rows → calculate KEEP / DROP → locate the same identity in the supplied outputs → compare field values. A row count match alone does not prove a data match.</p><table><tr><th>Output</th><th>Calculated source-row decisions</th><th>Supplied output rows matching processed identities</th><th>All supplied output rows</th></tr>'+rows+'</table><p>Stopped rows have no approved keep/drop decision. Sample results apply only to selected rows. Stages that merge or derive records can have different source and output row counts; use identity and field evidence below.</p></section>')


def unmapped_leaves(data,resolver,prefix=''):
    """Include source fields outside the alias catalog in unchanged-row comparisons."""
    from medpar_qa.normalization.fields import _key_form
    known={_key_form(p) for canonical,aliases in resolver.aliases.items() for p in [canonical,*aliases]}
    def walk(value,path):
        if isinstance(value,dict):
            for key,child in value.items():yield from walk(child,f'{path}.{key}' if path else key)
        elif _key_form(path) not in known:
            yield path,value
    return list(walk(data,prefix))


def render_file_flow(data):
    """A numbered file-to-rows inventory with decisions and reconciliation in one place."""
    from pathlib import Path
    rows=[]
    for i,item in enumerate(data['files'],1):
        decisions=item.get('decisions',{});comparison=item.get('comparison_outcomes',{})
        def cell(value):return '<td><a href="#rows-'+str(i)+'">'+html.escape(str(value))+'</a></td>'
        stopped=sum(v for k,v in decisions.items() if k not in ('KEEP','DROP'))
        conclusion='Not selected for processing' if not item['processed_rows'] else 'FAIL' if comparison.get('FAIL') else 'BLOCKED' if comparison.get('BLOCKED') else 'PASS' if comparison.get('PASS') else 'Comparison not supplied'
        rows.append('<tr><td>'+str(i)+'</td><td title="'+html.escape(item['file'],quote=True)+'"><a href="#rows-'+str(i)+'">'+html.escape(Path(item['file']).name)+'</a><details><summary>Full source path</summary>'+html.escape(item['file'])+'</details></td>'+''.join(cell(v) for v in (item['total_rows'],item['processed_rows'],decisions.get('KEEP',0),decisions.get('DROP',0),stopped))+'<td>'+html.escape(conclusion)+'</td></tr>')
    return '<section><h2>File → selected rows → decisions → output comparison</h2><ol><li>Discover every original input file; count its top-level claim rows.</li><li>Select only the configured number of rows from each file. No additional rows are included.</li><li>Apply stage rules. KEEP continues, DROP is removed by a business rule, STOPPED includes exceptions and unmet prerequisites.</li><li>Cross-check each processed row against supplied keep/drop membership and field values. Inspect full-population balance separately.</li><li>Conclude from the decision, validation evidence and comparison result. A KEEP decision is not proof that the supplied output matched.</li></ol><p>Click a number or filename to open that file’s paginated row evidence. A limited sample does not assess unselected rows.</p><table><tr>'+''.join('<th>'+h+'</th>' for h in ('No.','Original input file','Total rows','Selected rows','KEEP rows','DROP rows','STOPPED rows','Processed-row comparison'))+'</tr>'+''.join(rows)+'</table></section>'
