"""Nested stage/file/row decision and supplied-output comparison tables."""
from collections import Counter,defaultdict
from pathlib import Path
import os
from .status_navigation import e
from .path_utils import relative_link


def file_rows(master,sources,moved_reports):
    rows=[];serial=0
    sources=sorted(sources,key=lambda pair:pair[0].get('input_kind')!='supplied_original')
    for audit,path in sources:
        by_file=defaultdict(list)
        for row in audit.get('rows',[]):by_file[row.get('file')].append(row)
        kind='Supplied original' if audit.get('input_kind')=='supplied_original' else 'Generated from previous stage'
        for number,item in enumerate(audit.get('files',[]),1):
            serial+=1;records=by_file[item['file']]
            decisions=item.get('decisions') or Counter(r.get('decision') for r in records)
            continued=sum(r.get('decision')=='KEEP' and any(str(Path(c['event_id'].split('#check-')[0]).resolve()) in moved_reports for c in r.get('checks',[]) if '#check-' in c.get('event_id','')) for r in records)
            target=relative_link(master,path)+'#rows-'+str(number)
            def cell(value):return '<td><a href="'+e(target)+'">'+e(value)+'</a></td>'
            stopped=sum(v for k,v in decisions.items() if k not in ('KEEP','DROP'))
            name=item.get('origin',item['file'])
            rows.append('<tr><td>'+str(serial)+'</td><td>'+e(kind)+'</td><td><a href="'+e(target)+'">'+e(Path(name).name)+'</a><details><summary>Source path</summary>'+e(name)+'</details></td>'+''.join(cell(v) for v in (item['total_rows'],item.get('processed_rows',item.get('selected_rows',0)+item.get('context_rows',0)),decisions.get('KEEP',0),decisions.get('DROP',0),stopped,continued))+'</tr>')
    supplied=sum(len(a.get('files',[])) for a,_ in sources if a.get('input_kind')=='supplied_original')
    generated=serial-supplied
    headings=('No.','Input origin','File — open row evidence','Total rows','Selected rows','KEEP','DROP','STOPPED / exceptions','Kept source rows continued*')
    return '<details><summary>Input files and their row results — '+str(supplied)+' supplied files; '+str(generated)+' generated input containers</summary><p>Supplied files are the configured originals. Generated input containers carry rows received from the previous stage and are listed separately by origin; they do not increase Started here’s supplied-file count.</p><p>*Continued counts kept source rows whose group output was actually read by the next stage. A merged output may represent multiple source rows; this column is not the number of generated output rows. See the next-stage handoff table for generated row counts. Unselected files remain listed with zero processed decisions.</p><div style="overflow-x:auto"><table><tr>'+''.join('<th>'+h+'</th>' for h in headings)+'</tr>'+''.join(rows)+'</table></div></details>'


def comparisons(master,sources):
    sections=[]
    for audit,path in sources:
        if audit.get('input_kind')!='supplied_original':continue
        link=relative_link(master,path);rows=[]
        for role in ('keep','drop'):
            chosen=[r for r in audit.get('rows',[]) if r.get('decision')==role.upper()]
            counts=Counter(r.get('comparison_status','NOT PROVIDED') for r in chosen)
            refs=audit.get('comparison_files',{}).get(role,[])
            status='NOT PROVIDED' if not refs else 'NOT ASSESSED — no '+role.upper()+' decisions in this sample' if not chosen else 'FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] else 'PASS' if counts['PASS']==len(chosen) else 'NOT ASSESSED'
            paths=[f.get('origin',f['file']) for f in refs]
            common=paths[0] if len(paths)==1 else os.path.commonprefix(paths).rsplit('/',1)[0] if paths else 'No reference supplied'
            locations='<details><summary>Resolved reference paths (first 10)</summary><ol>'+''.join('<li>'+e(p)+'</li>' for p in paths[:10])+'</ol><a href="'+e(link)+'#population-proof">Full inventory and count proof</a></details>' if refs else ''
            results=' · '.join(f'{counts[s]} {s}' for s in ('PASS','FAIL','BLOCKED') if counts[s]) or 'No rows assessed'
            rows.append('<tr><td>Calculated '+role.upper()+' versus supplied '+role.upper()+'</td><td>'+str(len(chosen))+'</td><td>'+str(len(refs))+' files · '+e(audit.get('comparison_rows',{}).get(role) if refs else 'Not supplied')+' rows in whole reference dataset<br>'+e(common)+locations+'</td><td>'+e(results)+'</td><td>'+e(status)+'</td><td><a href="'+e(link)+'#output-comparison">Membership, field values and row evidence</a></td></tr>')
        sections.append('<p><strong>Supplied-original comparison conclusion: '+e(audit.get('comparison_status','NOT PROVIDED'))+'</strong>. The two rows below cover processed source decisions; whole-dataset count balance and output overlap are assessed separately. Exceptions and stopped rows are not silently counted as KEEP or DROP.</p><table><tr>'+''.join('<th>'+h+'</th>' for h in ('Comparison','Calculated source rows','Supplied reference','Processed-row results','Conclusion','Evidence'))+'</tr>'+''.join(rows)+'</table><p><a href="'+e(link)+'#population-proof">Whole-dataset count reconciliation and reference-population evidence</a></p>')
    received=sum(len(a.get('rows',[])) for a,_ in sources if a.get('input_kind')!='supplied_original')
    if received:sections.append('<p>'+str(received)+' received/generated rows are outside these supplied-original reference comparisons. Their decisions remain in the stage totals and their own row evidence. No independent matching reference population is assumed for them.</p>')
    return '<details><summary>KEEP and DROP comparison with supplied paths</summary>'+(''.join(sections) or '<p>No independent supplied keep/drop reference is attached to these forwarded inputs. Open their row evidence for generated-output checks.</p>')+'</details>'


def stage_subrows(master,sources,moved_reports):
    return '<tr><td colspan="7">'+file_rows(master,sources,moved_reports)+'</td></tr><tr><td colspan="7">'+comparisons(master,sources)+'</td></tr>'
