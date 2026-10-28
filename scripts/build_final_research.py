"""Build the paper and figures from pinned, sanitized results; no inference/network."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

from update_final_prospective import METHODS, verify_bundle

ROOT=Path(__file__).resolve().parents[1]
FINAL=ROOT/'reports/final_research'
NAMES={'direct':'Direct LLM','leap_v1_raw':'LEAP v1 raw','leap_v1_conservative':'LEAP v1 conservative',
       'leap_v2_raw':'LEAP v2 raw','leap_v2_conservative':'LEAP v2 conservative','kalshi':'Kalshi midpoint','constant_50':'Constant 50%'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def verify_sources():
    m=read(FINAL/'source_manifest.json')
    for path,h in m['files_sha256'].items():
        if sha(ROOT/path)!=h:raise ValueError('Pinned research source changed: '+path)
    for directory in ('heldout_150','leap_nba_v2_development_50'):
        base=ROOT/'reports'/directory
        for path,h in read(base/'manifest.json').items():
            if sha(base/path)!=h:raise ValueError('Original report manifest mismatch')
    return m


def md(headers, rows):
    def fmt(x):return f'{x:.6f}' if isinstance(x,float) else str(x)
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |',
                      *['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows]])


def csv_file(path, rows):
    rows=list(rows)
    if not rows:raise ValueError('Empty table schema')
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    path.write_text(s.getvalue())


def assemble(update):
    verify_sources();held=read(ROOT/'reports/heldout_150/summary.json');dev=read(ROOT/'reports/leap_nba_v2_development_50/summary.json')
    boot=read(ROOT/'reports/heldout_150/bootstrap.json');diag=read(ROOT/'reports/heldout_150/diagnostics.json')
    bundles=[('Development A',dev['comparisons']['A_v2_development']),('Development B',dev['comparisons']['B_seven_method']),
             ('Held-out primary',held['cohorts']['primary']),('Held-out A',held['cohorts']['A_v2_market']),('Held-out B',held['cohorts']['B_seven_method'])]
    tables={};scores=[];cal=[];groups=[];removals=[]
    for name,c in bundles:
        rows=[]
        for m in METHODS:
            if m not in c['scores']:continue
            s=c['scores'][m];rows.append([NAMES[m],s['n'],s['brier_score'],s['log_loss'],s['mean_home_probability'],f"{s['extreme_count']}/{s['n']}"])
            scores.append({'cohort':name,'method':m,**s})
            for b in c['calibration'][m]:cal.append({'cohort':name,'method':m,**b})
        tables[name]=md(['Method','Paired n','Brier','Log loss','Mean home p','Extreme p'],rows)
        for m,gs in c['leave_one_group_out'].items():
            for g,v in gs.items():removals.append({'cohort':name,'method':m,'removed_group':g,'n':v['n'],'brier_without':v['brier_score'],'log_loss_without':v['log_loss'],
               'brier_omission_minus_full':v['omission_minus_full']['brier_score'],'log_loss_omission_minus_full':v['omission_minus_full']['log_loss']})
    intervals=[]
    for cohort,b in boot.items():
        for pair,values in b['comparisons'].items():intervals.append({'cohort':cohort,'comparison':pair,'n':b['n'],'seed':b['seed'],'resamples':b['replicates'],**values})
    for version,gs in diag['groups'].items():
        for g,v in gs.items():
            lr=v['likelihood_ratios_success_only'];q=lr['quantiles'];directions=v['directions_success_only'];status=v['status_counts']
            groups.append({'version':version,'group':g,'success_n':status.get('success',0),'source_skip':status.get('skipped_missing',0),'failed':status.get('failed',0),'insufficient':status.get('insufficient',0),
                'home':directions.get('home',0),'away':directions.get('away',0),'neutral':directions.get('neither',0),'min_lr':q.get('0.0'),'median_lr':q.get('0.5'),'max_lr':q.get('1.0'),
                'mean_log_lr':v['log_lr_success_only']['mean'],'mean_absolute_log_lr':v['absolute_log_lr_success_only']['mean']})
    prospective=read(update/'summary.json');obs=verify_bundle(update)
    # Keep paired denominators in machine-readable tables and the paper.
    pros_rows=[]
    for stratum,v in prospective.items():
        for name,c in v['comparisons'].items():
            for m,s in c['methods'].items():pros_rows.append({'cohort':stratum,'comparison':name,'method':m,'n':c['n'],'brier_score':s['brier_score'],'log_loss':s['log_loss']})
    current=[]
    for r in obs['rows']:
        current.append([r['game_id'],r['primary_eligible'],r['outcome'] if r['outcome'] is not None else 'pending' if r['primary_eligible'] else 'excluded',r.get('exclusion_reason') or '—'])
    return {'scores':scores,'calibration':cal,'intervals':intervals,'groups':groups,'removals':removals,'tables':tables,'prospective':pros_rows,
            'prospective_inventory':md(['Game ID','Eligible primary capture','Outcome / state','Exclusion reason'],current),
            'prospective_counts':{'enrolled':len(obs['rows']),'eligible':sum(r['primary_eligible'] for r in obs['rows']),
              'scored':sum(r['primary_eligible'] and r['outcome'] is not None for r in obs['rows'])},
            'update_manifest_sha256':sha(update/'manifest.json')}


def figures(output,data):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'nba-final-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'nba-final-research-v1','font.family':'DejaVu Sans'})
    colors={'direct':'#245677','leap_v1_raw':'#B65C24','leap_v1_conservative':'#D99A62','leap_v2_raw':'#357A52','leap_v2_conservative':'#78A98A','kalshi':'#685184','constant_50':'#818181'}
    def save(fig,name):
        svg=output/(name+'.svg')
        fig.savefig(svg,bbox_inches='tight',metadata={'Date':None})
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        fig.savefig(output/(name+'.png'),bbox_inches='tight',dpi=200,metadata={'Software':'matplotlib 3.10.8'})
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.1),layout='constrained')
    for ax,cohort in zip(axes,('Held-out A','Held-out B')):
        rows=[r for r in data['scores'] if r['cohort']==cohort]
        ax.barh([NAMES[r['method']] for r in rows],[r['brier_score'] for r in rows],color=[colors[r['method']] for r in rows])
        ax.invert_yaxis();ax.set_xlim(0,.28);ax.set_xlabel('Mean Brier loss (lower is better)');ax.set_title(f"{cohort}: paired n={rows[0]['n']}")
        for i,r in enumerate(rows):ax.text(r['brier_score']+.003,i,f"{r['brier_score']:.3f}",va='center',fontsize=9)
    save(fig,'heldout_brier')
    fig,ax=plt.subplots(figsize=(8,4.2),layout='constrained')
    selected=[r for r in data['intervals'] if r['cohort']=='A_v2_market']
    for i,r in enumerate(selected):
        mean=r['mean_brier_difference'];ax.errorbar(mean,i,xerr=[[mean-r['lower_95']],[r['upper_95']-mean]],fmt='o',color='#245677',capsize=3)
    ax.set_yticks(range(len(selected)),[r['comparison'].replace('leap_v2','v2').replace('_minus_',' − ').replace('_',' ') for r in selected]);ax.axvline(0,color='gray',linestyle='--')
    ax.set_xlabel('Paired mean Brier difference; descriptive 95% bootstrap interval');ax.set_title('Held-out A: n=143, 10,000 paired resamples');save(fig,'paired_intervals')
    fig,axes=plt.subplots(2,3,figsize=(11,6.8),layout='constrained')
    for ax,m in zip(axes.flat,('direct','leap_v1_raw','kalshi','leap_v2_raw','leap_v2_conservative','leap_v1_conservative')):
        rows=[r for r in data['calibration'] if r['cohort']=='Held-out B' and r['method']==m and r['count']]
        ax.plot([r['mean_probability'] for r in rows],[r['home_win_frequency'] for r in rows],marker='o',color=colors[m])
        for r in rows:ax.annotate(str(r['count']),(r['mean_probability'],r['home_win_frequency']),xytext=(2,3),textcoords='offset points',fontsize=7)
        ax.plot([0,1],[0,1],':',color='gray');ax.set(xlim=(0,1),ylim=(0,1.04),xlabel='Mean forecast',ylabel='Observed home-win fraction',title=NAMES[m])
    fig.suptitle('Held-out B calibration, n=139; labels are bucket counts');save(fig,'calibration')
    fig,ax=plt.subplots(figsize=(7,4),layout='constrained')
    for m in ('direct','leap_v2_raw','kalshi'):
        rs=[next(r for r in data['scores'] if r['cohort']==c and r['method']==m) for c in ('Development A','Held-out A')]
        ax.plot([0,1],[r['brier_score'] for r in rs],marker='o',label=NAMES[m],color=colors[m])
    ax.set_xticks([0,1],['Development A (n=50)','Held-out A (n=143)']);ax.set_ylabel('Mean Brier loss');ax.set_title('Distinct game sets: descriptive comparison, not a paired change');ax.legend();save(fig,'development_heldout')


def build(output=FINAL,update=None,draw=True):
    output=Path(output);update=Path(update or FINAL/'prospective_update_2026_10_28');data=assemble(update)
    (output/'tables').mkdir(parents=True,exist_ok=True);(output/'figures').mkdir(exist_ok=True)
    for name in ('scores','calibration','intervals','groups','removals','prospective'):
        csv_file(output/'tables'/(name+'.csv'),data[name])
    for source,name in [('reports/heldout_150/results.csv','heldout_per_game.csv'),('reports/leap_nba_v2_development_50/results.csv','development_per_game.csv')]:shutil.copyfile(ROOT/source,output/'tables'/name)
    values={k.replace(' ','_'):v for k,v in data['tables'].items()}
    values['Intervals']=md(['Comparison / cohort','Paired n','Mean Brier difference','95% descriptive interval'],
      [[r['comparison'].replace('_',' ')+' / '+r['cohort'],r['n'],r['mean_brier_difference'],f"[{r['lower_95']:.6f}, {r['upper_95']:.6f}]"] for r in data['intervals']])
    values['Groups']=md(['Version/group','Usable n','Source skip','Failed/insufficient','Home/away/neutral','LR min/median/max'],
      [[r['version']+'/'+r['group'],r['success_n'],r['source_skip'],f"{r['failed']}/{r['insufficient']}",f"{r['home']}/{r['away']}/{r['neutral']}",'/'.join('—' if r[k] is None else f'{r[k]:.3f}' for k in ('min_lr','median_lr','max_lr'))] for r in data['groups']])
    values['Prospective_inventory']=data['prospective_inventory']
    values['Prospective_counts']=f"{data['prospective_counts']['eligible']} eligible primary capture(s), {data['prospective_counts']['scored']} verified outcome(s) scored, among {data['prospective_counts']['enrolled']} inventoried job(s)"
    values['Prospective_scores']=md(['Evidence-policy stratum / comparison','Method','Paired n','Brier','Log loss'],
      [[r['cohort']+' / '+r['comparison'],NAMES[r['method']],r['n'],r['brier_score'] if r['brier_score'] is not None else 'pending',r['log_loss'] if r['log_loss'] is not None else 'pending'] for r in data['prospective']])
    template=(FINAL/'paper_template.md').read_text()
    (output/'paper.md').write_text(re.sub(r'\$\{([^}]+)\}',lambda m:values[m[1]],template))
    if draw:figures(output/'figures',data)
    (output/'build.json').write_text(json.dumps({'schema_version':1,'input_manifest_sha256':sha(FINAL/'source_manifest.json'),
      'prospective_manifest_sha256':data['update_manifest_sha256'],'builder_sha256':sha(__file__),
      'template_sha256':sha(FINAL/'paper_template.md'),'reporting_protocol_sha256':sha(FINAL/'update_protocol.json'),
      'figures_generated':draw,'network_calls':0,'inference_calls':0},indent=2)+'\n')
    files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and
           (p.parent.name in ('figures','tables') or p.name in ('paper.md','build.json'))}
    (output/'generated_manifest.json').write_text(json.dumps(files,indent=2,sort_keys=True)+'\n')
    return data


def verify_generated(folder):
    verify_sources()
    folder=Path(folder)
    build=read(folder/'build.json')
    if any(build[k]!=h for k,h in {'input_manifest_sha256':sha(FINAL/'source_manifest.json'),
           'builder_sha256':sha(__file__),'template_sha256':sha(FINAL/'paper_template.md'),
           'reporting_protocol_sha256':sha(FINAL/'update_protocol.json')}.items()):raise ValueError('Paper build inputs changed')
    for name,h in read(folder/'generated_manifest.json').items():
        if sha(folder/name)!=h:raise ValueError('Generated artifact changed: '+name)
    return {'verified':True,'source_manifest_sha256':sha(FINAL/'source_manifest.json')}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--update',type=Path)
    p.add_argument('--no-figures',action='store_true');p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:result=verify_generated(a.verify)
    else:
        data=build(a.output,a.update,not a.no_figures);result={'built':str(a.output),'prospective':data['prospective_counts']}
    print(json.dumps(result))


if __name__=='__main__':main()
